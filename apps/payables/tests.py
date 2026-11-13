from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.services import open_cash_session

from .models import Payable
from .services import mark_payable_as_paid, register_payment, reopen_payable

User = get_user_model()


class PayablePaymentTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.payable = Payable.objects.create(
            business=self.business,
            description='Fornecedor X',
            original_amount=Decimal('200.00'),
            due_date=timezone.localdate(),
            created_by=self.user,
        )

    def test_payable_creation_does_not_count_as_cash_outflow(self):
        """A criação da conta não gera nenhum pagamento (saída de caixa)."""
        self.assertEqual(self.payable.paid_amount, Decimal('0.00'))
        self.assertEqual(self.payable.status, Payable.STATUS_PENDING)

    def test_partial_payment_updates_status(self):
        register_payment(self.payable, self.user, Decimal('50.00'), timezone.now())
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.balance, Decimal('150.00'))
        self.assertEqual(self.payable.status, Payable.STATUS_PARTIALLY_PAID)

    def test_full_payment_marks_as_paid(self):
        register_payment(self.payable, self.user, Decimal('200.00'), timezone.now())
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.balance, Decimal('0.00'))
        self.assertEqual(self.payable.status, Payable.STATUS_PAID)

    def test_payment_above_balance_is_rejected(self):
        with self.assertRaises(ValidationError):
            register_payment(self.payable, self.user, Decimal('500.00'), timezone.now())

    def test_payment_rechecks_status_of_stale_object(self):
        Payable.objects.filter(pk=self.payable.pk).update(status=Payable.STATUS_CANCELLED)

        with self.assertRaises(ValidationError):
            register_payment(self.payable, self.user, Decimal('10.00'), timezone.now())

        self.assertFalse(self.payable.payments.exists())


class PayableQuickActionsTests(TestCase):
    """
    Garante o fluxo das ações rápidas da listagem: marcar como paga
    registra automaticamente um pagamento pelo saldo total, sem exigir
    forma de pagamento; marcar como aberta cancela os pagamentos ativos
    preservando o histórico.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.payable = Payable.objects.create(
            business=self.business,
            description='Fornecedor X',
            original_amount=Decimal('200.00'),
            due_date=timezone.localdate(),
            created_by=self.user,
        )

    def test_mark_as_paid_registers_full_payment_without_method(self):
        mark_payable_as_paid(self.payable, self.user)
        self.payable.refresh_from_db()

        self.assertEqual(self.payable.status, Payable.STATUS_PAID)
        self.assertEqual(self.payable.balance, Decimal('0.00'))
        payment = self.payable.payments.get()
        self.assertEqual(payment.amount, Decimal('200.00'))

    def test_mark_as_paid_twice_is_rejected(self):
        mark_payable_as_paid(self.payable, self.user)
        with self.assertRaises(ValidationError):
            mark_payable_as_paid(self.payable, self.user)

    def test_reopen_cancels_active_payments_and_preserves_history(self):
        mark_payable_as_paid(self.payable, self.user)
        payment = self.payable.payments.get()

        reopen_payable(self.payable)
        self.payable.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(self.payable.status, Payable.STATUS_PENDING)
        self.assertEqual(self.payable.balance, Decimal('200.00'))
        # O pagamento permanece no histórico, apenas cancelado.
        self.assertEqual(payment.status, payment.STATUS_CANCELLED)
        self.assertEqual(self.payable.payments.count(), 1)

    def test_reopen_cancels_multiple_partial_payments(self):
        register_payment(self.payable, self.user, Decimal('80.00'), timezone.now())
        register_payment(self.payable, self.user, Decimal('120.00'), timezone.now())
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.status, Payable.STATUS_PAID)

        reopen_payable(self.payable)
        self.payable.refresh_from_db()

        self.assertEqual(self.payable.status, Payable.STATUS_PENDING)
        self.assertEqual(self.payable.balance, Decimal('200.00'))
        self.assertEqual(self.payable.payments.count(), 2)
