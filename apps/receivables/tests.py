from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.services import open_cash_session
from apps.customers.models import Customer
from apps.sales.services import create_sale

from .models import Receivable
from .services import register_payment

User = get_user_model()


class ReceivablePaymentTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('40.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('40.00'),
        )
        self.receivable = Receivable.objects.get(sale=self.sale)

    def test_partial_payment_reduces_balance(self):
        register_payment(self.receivable, self.user, Decimal('15.00'), 'dinheiro', timezone.now())
        self.receivable.refresh_from_db()
        self.assertEqual(self.receivable.balance, Decimal('25.00'))
        self.assertEqual(self.receivable.status, Receivable.STATUS_OPEN)

    def test_full_payment_marks_receivable_as_paid(self):
        register_payment(self.receivable, self.user, Decimal('40.00'), 'pix', timezone.now())
        self.receivable.refresh_from_db()
        self.assertEqual(self.receivable.balance, Decimal('0.00'))
        self.assertEqual(self.receivable.status, Receivable.STATUS_PAID)

    def test_payment_above_balance_is_rejected(self):
        with self.assertRaises(ValidationError):
            register_payment(
                self.receivable, self.user, Decimal('100.00'), 'dinheiro', timezone.now()
            )

    def test_payment_rechecks_status_of_stale_object(self):
        Receivable.objects.filter(pk=self.receivable.pk).update(status=Receivable.STATUS_CANCELLED)

        with self.assertRaises(ValidationError):
            register_payment(
                self.receivable, self.user, Decimal('10.00'), 'dinheiro', timezone.now()
            )

        self.assertFalse(self.receivable.payments.exists())

    def test_payment_does_not_create_new_sale(self):
        from apps.sales.models import Sale

        sales_before = Sale.objects.filter(business=self.business).count()
        register_payment(self.receivable, self.user, Decimal('10.00'), 'dinheiro', timezone.now())
        sales_after = Sale.objects.filter(business=self.business).count()
        self.assertEqual(sales_before, sales_after)
