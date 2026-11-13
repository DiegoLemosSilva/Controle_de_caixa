"""Testes da integridade de sessões de caixa."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from apps.businesses.models import Business
from apps.cash.models import CashSession
from apps.cash.services import open_cash_session


class CashSessionIntegrityTests(TransactionTestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa de teste')
        self.other_business = Business.objects.create(name='Outra empresa')
        self.user = get_user_model().objects.create_user(username='caixa-teste')
        self.today = timezone.localdate()

    def create_session(self, business, date, status):
        return CashSession.objects.create(
            business=business,
            date=date,
            status=status,
            opening_amount=Decimal('0.00'),
            opened_at=timezone.now(),
            opened_by=self.user,
        )

    def test_database_allows_only_one_open_session_per_business(self):
        self.create_session(self.business, self.today, CashSession.STATUS_OPEN)
        self.create_session(
            self.business, self.today + timedelta(days=1), CashSession.STATUS_CLOSED
        )
        self.create_session(self.other_business, self.today, CashSession.STATUS_OPEN)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_session(
                self.business, self.today + timedelta(days=2), CashSession.STATUS_OPEN
            )
        self.assertEqual(CashSession.objects.filter(business=self.business).count(), 2)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_openings_are_serialized(self):
        barrier = Barrier(2, timeout=15)
        business_id, user_id = self.business.pk, self.user.pk

        def open_on_day(offset):
            close_old_connections()
            try:
                business = Business.objects.get(pk=business_id)
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait()
                try:
                    open_cash_session(
                        business, user, self.today + timedelta(days=offset), Decimal('0.00')
                    )
                    return 'opened'
                except ValidationError:
                    return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(open_on_day, (0, 1)))
        self.assertCountEqual(results, ['opened', 'rejected'])
        self.assertEqual(
            CashSession.objects.filter(
                business=self.business, status=CashSession.STATUS_OPEN
            ).count(),
            1,
        )
