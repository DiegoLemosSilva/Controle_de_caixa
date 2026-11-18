"""Testes do fluxo de conferência conjunta."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.models import CashCountAdjustment
from apps.sales.services import create_sale

from apps.cash.services import (
    close_cash_session,
    latest_adjustments_for_date,
    open_cash_session,
    register_cash_count,
)


class CashCountBatchTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa A')
        self.user = get_user_model().objects.create_user(username='operador', password='senha')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.day = timezone.localdate()
        open_cash_session(self.business, self.user, self.day, Decimal('0.00'))
        self.client.force_login(self.user)
        self.url = reverse('cash:cash_count') + '?date=' + self.day.isoformat()

    def payload(self):
        data = {'date': self.day.isoformat()}
        for item in latest_adjustments_for_date(self.business, self.day):
            method = item['payment_method']
            data[f'counted_{method}'] = str(item['counted_amount'] if item['checked'] else Decimal('0.00'))
            data[f'expected_{method}'] = str(item['expected_amount'])
            data[f'revision_{method}'] = str(item['revision'])
        return data

    def test_saves_all_and_allows_divergence_without_reason(self):
        data = self.payload()
        data['counted_dinheiro'] = '10.00'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CashCountAdjustment.objects.filter(business=self.business).count(), 5)
        adjustment = CashCountAdjustment.objects.get(business=self.business, payment_method='dinheiro')
        self.assertEqual(adjustment.difference, Decimal('10.00'))
        self.assertEqual(adjustment.reason, '')

    def test_invalid_value_saves_nothing_and_keeps_input(self):
        data = self.payload()
        data['counted_dinheiro'] = '12.00'
        data['counted_pix'] = '-1'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhuma conferência foi salva')
        self.assertContains(response, 'value="12.00"')
        self.assertFalse(CashCountAdjustment.objects.filter(business=self.business).exists())

    def test_stale_revision_saves_nothing_and_preserves_history(self):
        data = self.payload()
        old = register_cash_count(self.business, self.user, self.day, 'pix', Decimal('1.00'), 'Motivo antigo')
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Os valores ou conferências mudaram')
        self.assertEqual(CashCountAdjustment.objects.filter(business=self.business).count(), 1)
        old.refresh_from_db()
        self.assertEqual(old.reason, 'Motivo antigo')

    def test_changed_expected_amount_rejects_entire_batch(self):
        data = self.payload()
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('10.00'),
            payments=[{'method': 'pix', 'amount': Decimal('10.00')}],
        )
        response = self.client.post(self.url, data)
        self.assertContains(response, 'Os valores ou conferências mudaram')
        self.assertFalse(CashCountAdjustment.objects.filter(business=self.business).exists())

    def test_unmodified_counts_are_not_duplicated(self):
        self.client.post(self.url, self.payload())
        data = self.payload()
        self.client.post(self.url, data)
        self.assertEqual(CashCountAdjustment.objects.filter(business=self.business).count(), 5)
        data['counted_pix'] = '2.00'
        self.client.post(self.url, data)
        self.assertEqual(CashCountAdjustment.objects.filter(business=self.business).count(), 6)

    def test_closed_cash_rejects_batch(self):
        self.client.post(self.url, self.payload())
        data = self.payload()
        close_cash_session(self.business, self.user, self.day)
        data['counted_pix'] = '5.00'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhuma conferência foi salva')
        self.assertContains(response, 'Valor digitado não salvo: 5.00')
        self.assertEqual(CashCountAdjustment.objects.filter(business=self.business).count(), 5)

    def test_atomic_rollback_on_late_failure(self):
        data = self.payload()
        from apps.cash.services import register_cash_count as real_register
        calls = []

        def fail_later(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise ValidationError('Falha simulada')
            return real_register(*args, **kwargs)

        with patch('apps.cash.services.register_cash_count', side_effect=fail_later):
            response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CashCountAdjustment.objects.filter(business=self.business).exists())

    def test_rejects_mismatched_date(self):
        data = self.payload()
        data['date'] = (self.day - timezone.timedelta(days=1)).isoformat()
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CashCountAdjustment.objects.filter(business=self.business).exists())

    def test_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.payload()).status_code, 403)
        self.assertFalse(CashCountAdjustment.objects.filter(business=self.business).exists())

    def test_cross_company_never_changes_other_business(self):
        other = Business.objects.create(name='Empresa B')
        other_user = get_user_model().objects.create_user(username='outro', password='senha')
        BusinessOwner.objects.create(user=other_user, business=other)
        open_cash_session(other, other_user, self.day, Decimal('0.00'))
        register_cash_count(other, other_user, self.day, 'pix', Decimal('9.00'), 'Anterior')
        self.client.post(self.url, self.payload())
        self.assertEqual(CashCountAdjustment.objects.filter(business=other).count(), 1)
        self.assertEqual(CashCountAdjustment.objects.get(business=other).reason, 'Anterior')
