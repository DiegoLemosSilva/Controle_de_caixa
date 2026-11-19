"""
Testes das séries recorrentes de contas a pagar (Fixa, Semanal e
Parcelada), incluindo geração de ocorrências, edição individual vs
em massa e cancelamento (AGENTS.md: regras de negócio no backend,
histórico preservado).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner

from .models import Payable, PayableSeries
from .series_services import (
    cancel_future_occurrences,
    create_series,
    ensure_series_occurrences,
    generate_fixed_occurrences,
    generate_weekly_occurrences,
    mark_detached_if_diverges,
    update_series_and_future_occurrences,
)

User = get_user_model()


class InstallmentSeriesTests(TestCase):
    """Série parcelada: todas as parcelas são geradas de uma vez."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='op', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

    def test_creates_all_installments_at_once(self):
        series = create_series(
            business=self.business,
            user=self.user,
            kind=PayableSeries.KIND_INSTALLMENT,
            description='Empréstimo',
            supplier_name='',
            amount=Decimal('600.00'),
            start_date=timezone.localdate(),
            total_installments=6,
        )
        occurrences = Payable.objects.filter(series=series).order_by('installment_number')
        self.assertEqual(occurrences.count(), 6)
        self.assertEqual(
            [o.installment_number for o in occurrences], [1, 2, 3, 4, 5, 6]
        )

    def test_installment_amounts_sum_exactly_to_total(self):
        series = create_series(
            business=self.business,
            user=self.user,
            kind=PayableSeries.KIND_INSTALLMENT,
            description='Empréstimo',
            supplier_name='',
            amount=Decimal('100.00'),
            start_date=timezone.localdate(),
            total_installments=3,
        )
        total = sum(
            p.original_amount for p in Payable.objects.filter(series=series)
        )
        self.assertEqual(total, Decimal('100.00'))

    def test_installment_dates_are_monthly(self):
        start = timezone.localdate().replace(day=15)
        series = create_series(
            business=self.business,
            user=self.user,
            kind=PayableSeries.KIND_INSTALLMENT,
            description='Empréstimo',
            supplier_name='',
            amount=Decimal('300.00'),
            start_date=start,
            total_installments=3,
        )
        dates = list(
            Payable.objects.filter(series=series).order_by('installment_number')
            .values_list('due_date', flat=True)
        )
        self.assertEqual(dates[0].day, 15)
        self.assertEqual(dates[1].month, (start.month % 12) + 1 if start.month < 12 else 1)


class FixedSeriesGenerationTests(TestCase):
    """Série fixa mensal: geração lazy garante janela futura, sem duplicar."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='op', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

    def test_generates_occurrences_within_window(self):
        series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_FIXED,
            description='Aluguel', amount=Decimal('1000.00'),
            day_of_month=10, created_by=self.user,
        )
        created = generate_fixed_occurrences(series, self.user)
        self.assertGreaterEqual(len(created), 1)
        for payable in created:
            self.assertEqual(payable.series, series)
            self.assertEqual(payable.original_amount, Decimal('1000.00'))

    def test_generation_is_idempotent(self):
        series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_FIXED,
            description='Aluguel', amount=Decimal('1000.00'),
            day_of_month=10, created_by=self.user,
        )
        generate_fixed_occurrences(series, self.user)
        count_after_first = Payable.objects.filter(series=series).count()
        generate_fixed_occurrences(series, self.user)
        count_after_second = Payable.objects.filter(series=series).count()
        self.assertEqual(count_after_first, count_after_second)

    def test_inactive_series_does_not_generate(self):
        series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_FIXED,
            description='Aluguel', amount=Decimal('1000.00'),
            day_of_month=10, is_active=False, created_by=self.user,
        )
        created = generate_fixed_occurrences(series, self.user)
        self.assertEqual(created, [])


class WeeklySeriesGenerationTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='op', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

    def test_generates_occurrences_on_correct_weekday(self):
        series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_WEEKLY,
            description='Fornecedor de pão', amount=Decimal('50.00'),
            weekday=2, created_by=self.user,  # Quarta-feira
        )
        created = generate_weekly_occurrences(series, self.user)
        self.assertGreater(len(created), 0)
        for payable in created:
            self.assertEqual(payable.due_date.weekday(), 2)

    def test_generation_is_idempotent(self):
        series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_WEEKLY,
            description='Fornecedor de pão', amount=Decimal('50.00'),
            weekday=2, created_by=self.user,
        )
        generate_weekly_occurrences(series, self.user)
        first_count = Payable.objects.filter(series=series).count()
        generate_weekly_occurrences(series, self.user)
        second_count = Payable.objects.filter(series=series).count()
        self.assertEqual(first_count, second_count)


class SeriesEditTests(TestCase):
    """Edição individual (destacamento) vs edição em massa da série."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='op', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_FIXED,
            description='Internet', amount=Decimal('100.00'),
            day_of_month=5, created_by=self.user,
        )
        generate_fixed_occurrences(self.series, self.user)

    def test_update_series_applies_to_future_pending_occurrences(self):
        count = update_series_and_future_occurrences(
            self.series, 'Internet Fibra', 'Provedor X', Decimal('120.00')
        )
        self.assertGreater(count, 0)
        for payable in Payable.objects.filter(series=self.series):
            self.assertEqual(payable.description, 'Internet Fibra')
            self.assertEqual(payable.original_amount, Decimal('120.00'))

    def test_detached_occurrence_is_not_overwritten_by_series_update(self):
        payable = Payable.objects.filter(series=self.series).first()
        original_desc, original_amount, original_date = (
            payable.description, payable.original_amount, payable.due_date
        )
        payable.description = 'Internet (negociada)'
        payable.original_amount = Decimal('90.00')
        payable.save()

        mark_detached_if_diverges(payable, original_desc, original_amount, original_date)
        payable.refresh_from_db()
        self.assertTrue(payable.detached_from_series)

        update_series_and_future_occurrences(
            self.series, 'Internet Fibra', '', Decimal('120.00')
        )
        payable.refresh_from_db()
        self.assertEqual(payable.description, 'Internet (negociada)')
        self.assertEqual(payable.original_amount, Decimal('90.00'))

    def test_update_does_not_touch_paid_occurrence(self):
        from .services import mark_payable_as_paid

        payable = Payable.objects.filter(series=self.series).first()
        mark_payable_as_paid(payable, self.user)

        update_series_and_future_occurrences(
            self.series, 'Internet Fibra', '', Decimal('120.00')
        )
        payable.refresh_from_db()
        self.assertEqual(payable.original_amount, Decimal('100.00'))

    def test_installment_series_cannot_be_mass_updated(self):
        installment_series = create_series(
            business=self.business, user=self.user,
            kind=PayableSeries.KIND_INSTALLMENT,
            description='Empréstimo', supplier_name='',
            amount=Decimal('300.00'), start_date=timezone.localdate(),
            total_installments=3,
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            update_series_and_future_occurrences(
                installment_series, 'Novo nome', '', Decimal('999.00')
            )


class SeriesCancelTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='op', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.series = PayableSeries.objects.create(
            business=self.business, kind=PayableSeries.KIND_WEEKLY,
            description='Gás', amount=Decimal('80.00'),
            weekday=0, created_by=self.user,
        )
        generate_weekly_occurrences(self.series, self.user)

    def test_cancel_future_occurrences_pauses_series_and_cancels_pending(self):
        count = cancel_future_occurrences(self.series, self.user)
        self.assertGreater(count, 0)
        self.series.refresh_from_db()
        self.assertFalse(self.series.is_active)
        for payable in Payable.objects.filter(series=self.series):
            self.assertEqual(payable.status, Payable.STATUS_CANCELLED)

    def test_cancel_does_not_affect_paid_occurrences(self):
        from .services import mark_payable_as_paid

        payable = Payable.objects.filter(series=self.series).first()
        mark_payable_as_paid(payable, self.user)

        cancel_future_occurrences(self.series, self.user)
        payable.refresh_from_db()
        self.assertEqual(payable.status, Payable.STATUS_PAID)

    def test_cancelled_series_does_not_generate_new_occurrences(self):
        cancel_future_occurrences(self.series, self.user)
        count_before = Payable.objects.filter(series=self.series).count()
        ensure_series_occurrences(self.business, self.user)
        count_after = Payable.objects.filter(series=self.series).count()
        self.assertEqual(count_before, count_after)


class PayableSeriesViewTests(TestCase):
    """Fluxo via views: criação, edição individual e visualização de série."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='gerente', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.client = Client()
        self.client.login(username='gerente', password='senha12345')

    def test_create_single_payable_via_view(self):
        response = self.client.post(reverse('payables:payable_create'), {
            'mode': 'single',
            'description': 'Conta de luz',
            'supplier_name': '',
            'amount': '150.00',
            'due_date': timezone.localdate().isoformat(),
        })
        self.assertRedirects(response, reverse('payables:payable_list'))
        self.assertTrue(
            Payable.objects.filter(business=self.business, description='Conta de luz').exists()
        )
        payable = Payable.objects.get(business=self.business, description='Conta de luz')
        self.assertIsNone(payable.series)

    def test_create_fixed_series_via_view(self):
        response = self.client.post(reverse('payables:payable_create'), {
            'mode': 'fixed',
            'description': 'Aluguel',
            'supplier_name': '',
            'amount': '1200.00',
            'due_date': timezone.localdate().isoformat(),
            'day_of_month': '5',
        })
        self.assertRedirects(response, reverse('payables:payable_list'))
        self.assertTrue(PayableSeries.objects.filter(
            business=self.business, kind=PayableSeries.KIND_FIXED
        ).exists())

    def test_create_installment_series_via_view(self):
        response = self.client.post(reverse('payables:payable_create'), {
            'mode': 'installment',
            'description': 'Empréstimo',
            'supplier_name': '',
            'amount': '600.00',
            'due_date': timezone.localdate().isoformat(),
            'total_installments': '6',
        })
        self.assertRedirects(response, reverse('payables:payable_list'))
        series = PayableSeries.objects.get(
            business=self.business, kind=PayableSeries.KIND_INSTALLMENT
        )
        self.assertEqual(Payable.objects.filter(series=series).count(), 6)

    def test_edit_single_occurrence_marks_detached(self):
        series = create_series(
            business=self.business, user=self.user,
            kind=PayableSeries.KIND_FIXED, description='Internet',
            supplier_name='', amount=Decimal('100.00'),
            start_date=timezone.localdate(), day_of_month=5,
        )
        payable = Payable.objects.filter(series=series).first()

        response = self.client.post(
            reverse('payables:payable_update', args=[payable.pk]),
            {
                'description': 'Internet (editada)',
                'supplier_name': '',
                'due_date': payable.due_date.isoformat(),
            },
        )
        self.assertRedirects(response, reverse('payables:payable_list'))
        payable.refresh_from_db()
        self.assertTrue(payable.detached_from_series)

    def test_series_detail_view_lists_occurrences(self):
        series = create_series(
            business=self.business, user=self.user,
            kind=PayableSeries.KIND_WEEKLY, description='Gás',
            supplier_name='', amount=Decimal('80.00'),
            start_date=timezone.localdate(), weekday=0,
        )
        response = self.client.get(
            reverse('payables:payable_series_detail', args=[series.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('occurrences', response.context)
        self.assertGreater(len(response.context['occurrences']), 0)

    def test_series_update_view_applies_to_future_occurrences(self):
        series = create_series(
            business=self.business, user=self.user,
            kind=PayableSeries.KIND_FIXED, description='Internet',
            supplier_name='', amount=Decimal('100.00'),
            start_date=timezone.localdate(), day_of_month=5,
        )
        response = self.client.post(
            reverse('payables:payable_series_update', args=[series.pk]),
            {'description': 'Internet Fibra', 'supplier_name': '', 'amount': '130.00'},
        )
        self.assertRedirects(
            response, reverse('payables:payable_series_detail', args=[series.pk])
        )
        series.refresh_from_db()
        self.assertEqual(series.amount, Decimal('130.00'))

    def test_series_cancel_view_cancels_future_occurrences(self):
        series = create_series(
            business=self.business, user=self.user,
            kind=PayableSeries.KIND_WEEKLY, description='Gás',
            supplier_name='', amount=Decimal('80.00'),
            start_date=timezone.localdate(), weekday=0,
        )
        response = self.client.post(
            reverse('payables:payable_series_cancel', args=[series.pk])
        )
        self.assertRedirects(response, reverse('payables:payable_list'))
        series.refresh_from_db()
        self.assertFalse(series.is_active)

    def test_series_isolated_between_businesses(self):
        other_business = Business.objects.create(name='Outra Empresa')
        other_user = User.objects.create_user(username='outro', password='senha12345')
        BusinessOwner.objects.create(user=other_user, business=other_business)
        series = create_series(
            business=other_business, user=other_user,
            kind=PayableSeries.KIND_FIXED, description='Internet',
            supplier_name='', amount=Decimal('100.00'),
            start_date=timezone.localdate(), day_of_month=5,
        )
        response = self.client.get(
            reverse('payables:payable_series_detail', args=[series.pk])
        )
        self.assertEqual(response.status_code, 404)
