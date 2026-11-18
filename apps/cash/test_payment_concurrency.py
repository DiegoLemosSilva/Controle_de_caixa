"""Testes de concorrência dos pagamentos no PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from apps.businesses.models import Business
from apps.cash.models import CashCountAdjustment
from apps.cash.services import (
    close_cash_session, latest_adjustments_for_date, open_cash_session,
    register_cash_count, register_cash_counts_batch,
)
from apps.customers.models import Customer
from apps.payables.models import Payable
from apps.payables.services import register_payment as pay_payable
from apps.receivables.models import Receivable
from apps.receivables.services import register_customer_payment, register_payment
from apps.sales.models import Sale
from apps.sales.services import create_sale


@skipUnlessDBFeature('has_select_for_update')
class PaymentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa de teste')
        self.user = get_user_model().objects.create_user(username='teste-concorrencia')
        self.customer = Customer.objects.create(business=self.business, name='Cliente teste')
        self.now = timezone.now()
        self.today = timezone.localdate(self.now)
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))
        self.sale = Sale.objects.create(
            business=self.business, customer=self.customer, total_amount=Decimal('100.00'),
            sold_at=self.now, created_by=self.user,
        )
        self.receivable = Receivable.objects.create(
            business=self.business, customer=self.customer, sale=self.sale,
            original_amount=Decimal('100.00'),
        )
        self.payable = Payable.objects.create(
            business=self.business, description='Conta de teste',
            original_amount=Decimal('100.00'), due_date=self.today, created_by=self.user,
        )

    def run_concurrently(self, operations):
        barrier = Barrier(2, timeout=30)

        def run(operation):
            close_old_connections()
            try:
                barrier.wait()
                try:
                    operation()
                    return 'ok'
                except ValidationError:
                    return 'rejected'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, operations))
        self.assertCountEqual(results, ['ok', 'rejected'])

    def test_concurrent_payable_payments_do_not_exceed_balance(self):
        def operation():
            payable = Payable.objects.get(pk=self.payable.pk)
            user = get_user_model().objects.get(pk=self.user.pk)
            pay_payable(payable, user, Decimal('70.00'), self.now)

        self.run_concurrently((operation, operation))
        self.assertEqual(self.payable.balance, Decimal('30.00'))

    def test_individual_and_fifo_receipts_do_not_exceed_balance(self):
        def individual():
            receivable = Receivable.objects.get(pk=self.receivable.pk)
            user = get_user_model().objects.get(pk=self.user.pk)
            register_payment(receivable, user, Decimal('70.00'), 'dinheiro', self.now)

        def fifo():
            customer = Customer.objects.get(pk=self.customer.pk)
            user = get_user_model().objects.get(pk=self.user.pk)
            register_customer_payment(customer, user, Decimal('70.00'), 'dinheiro', self.now)

        self.run_concurrently((individual, fifo))
        self.assertEqual(self.receivable.balance, Decimal('30.00'))

    def assert_operation_rejected_after_concurrent_closure(self, operation):
        for method in ('dinheiro', 'pix', 'debito', 'credito', 'outro'):
            register_cash_count(self.business, self.user, self.today, method, Decimal('0.00'), '')

        closing = Event()
        attempted = Event()
        release = Event()

        def close_day():
            close_old_connections()
            try:
                with transaction.atomic():
                    business = Business.objects.get(pk=self.business.pk)
                    user = get_user_model().objects.get(pk=self.user.pk)
                    close_cash_session(business, user, self.today)
                    closing.set()
                    if not release.wait(30):
                        raise TimeoutError('Fechamento não foi liberado')
            finally:
                connections.close_all()

        def run_operation():
            close_old_connections()
            try:
                if not closing.wait(30):
                    raise TimeoutError('Fechamento não iniciou')
                business = Business.objects.get(pk=self.business.pk)
                user = get_user_model().objects.get(pk=self.user.pk)
                attempted.set()
                try:
                    operation(business, user)
                    return 'accepted'
                except ValidationError:
                    return 'rejected'
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            closure = executor.submit(close_day)
            attempt = executor.submit(run_operation)
            try:
                self.assertTrue(attempted.wait(30))
            finally:
                release.set()
            closure.result(timeout=45)
            self.assertEqual(attempt.result(timeout=45), 'rejected')

    def test_sale_after_concurrent_closure_is_rejected(self):
        def operation(business, user):
            create_sale(
                business, user, Decimal('10.00'),
                [{'method': 'dinheiro', 'amount': Decimal('10.00')}],
                sold_at=self.now,
            )

        self.assert_operation_rejected_after_concurrent_closure(operation)
        self.assertEqual(Sale.objects.filter(business=self.business).count(), 1)

    def test_cash_count_after_concurrent_closure_is_rejected(self):
        def operation(business, user):
            register_cash_count(business, user, self.today, 'dinheiro', Decimal('0.00'), '')

        self.assert_operation_rejected_after_concurrent_closure(operation)
        self.assertEqual(
            CashCountAdjustment.objects.filter(business=self.business, date=self.today).count(), 5
        )

    def test_batch_count_after_concurrent_closure_is_rejected(self):
        def operation(business, user):
            items = latest_adjustments_for_date(business, self.today)
            entries = {
                item['payment_method']: {
                    'counted': Decimal('0.00'),
                    'expected': item['expected_amount'],
                    'revision': item['revision'],
                }
                for item in items
            }
            register_cash_counts_batch(business, user, self.today, entries)

        self.assert_operation_rejected_after_concurrent_closure(operation)
        self.assertEqual(
            CashCountAdjustment.objects.filter(business=self.business, date=self.today).count(), 5
        )

    def test_payment_waiting_for_closure_is_rejected(self):
        for method in ('dinheiro', 'pix', 'debito', 'credito', 'outro'):
            register_cash_count(self.business, self.user, self.today, method, Decimal('0.00'), '')

        closing = Event()
        proceed = Event()

        def close_day():
            close_old_connections()
            try:
                with transaction.atomic():
                    business = Business.objects.get(pk=self.business.pk)
                    user = get_user_model().objects.get(pk=self.user.pk)
                    close_cash_session(business, user, self.today)
                    closing.set()
                    if not proceed.wait(30):
                        raise TimeoutError('Pagamento não iniciou a tempo')
            finally:
                connections.close_all()

        def payment():
            close_old_connections()
            try:
                if not closing.wait(30):
                    raise TimeoutError('Fechamento não iniciou a tempo')
                payable = Payable.objects.get(pk=self.payable.pk)
                user = get_user_model().objects.get(pk=self.user.pk)
                proceed.set()
                try:
                    pay_payable(payable, user, Decimal('10.00'), self.now)
                    return 'paid'
                except ValidationError:
                    return 'rejected'
            finally:
                proceed.set()
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            closure = executor.submit(close_day)
            attempt = executor.submit(payment)
            closure.result(timeout=45)
            self.assertEqual(attempt.result(timeout=45), 'rejected')
        self.assertEqual(self.payable.balance, Decimal('100.00'))
