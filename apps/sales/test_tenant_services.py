"""Isolamento de clientes nos serviços de vendas e comandas."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.businesses.models import Business
from apps.cash.services import open_cash_session
from apps.customers.models import Customer
from apps.sales.models import Comanda, ComandaPayment, Sale
from apps.sales.services import (
    add_comanda_item,
    create_sale,
    open_comanda,
    register_comanda_payment,
    update_comanda_payment,
)


class CustomerBusinessValidationTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa A')
        self.other_business = Business.objects.create(name='Empresa B')
        self.user = get_user_model().objects.create_user(username='tenant-test')
        self.customer = Customer.objects.create(business=self.business, name='Cliente A')
        self.other_customer = Customer.objects.create(
            business=self.other_business, name='Cliente B'
        )
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

    def test_sale_rejects_customer_from_another_business(self):
        with self.assertRaises(ValidationError):
            create_sale(
                self.business, self.user, Decimal('10.00'), [],
                customer=self.other_customer, fiado_amount=Decimal('10.00'),
            )
        self.assertFalse(Sale.objects.exists())

    def test_negative_fiado_cannot_offset_excess_payment(self):
        for fiado, paid in ((Decimal('-10.00'), Decimal('20.00')),
                            (Decimal('-0.001'), Decimal('10.00'))):
            with self.subTest(fiado=fiado):
                with self.assertRaises(ValidationError):
                    create_sale(
                        self.business, self.user, Decimal('10.00'),
                        [{'method': 'pix', 'amount': paid}],
                        customer=self.customer, fiado_amount=fiado,
                    )
        self.assertFalse(Sale.objects.exists())

    def test_comanda_rejects_customer_from_another_business(self):
        with self.assertRaises(ValidationError):
            open_comanda(self.business, self.user, customer=self.other_customer)
        self.assertFalse(Comanda.objects.exists())

    def test_comanda_payment_rejects_customer_from_another_business(self):
        comanda = open_comanda(self.business, self.user, customer=self.customer)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('10.00'))
        with self.assertRaises(ValidationError):
            register_comanda_payment(
                comanda, 'fiado', Decimal('10.00'), self.user, self.other_customer
            )
        self.assertFalse(ComandaPayment.objects.exists())

    def test_payment_update_rejects_customer_from_another_business(self):
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('10.00'))
        payment = register_comanda_payment(
            comanda, 'fiado', Decimal('10.00'), self.user, self.customer
        )
        with self.assertRaises(ValidationError):
            update_comanda_payment(payment, 'fiado', Decimal('10.00'), self.other_customer)
        payment.refresh_from_db()
        self.assertEqual(payment.customer_id, self.customer.pk)
