"""Testes das chaves estrangeiras compostas no PostgreSQL."""

from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.businesses.models import Business
from apps.customers.models import Customer
from apps.receivables.models import Receivable
from apps.sales.models import Comanda, Sale


@skipUnless(connection.vendor == 'postgresql', 'Constraints específicas do PostgreSQL.')
class TenantForeignKeyTests(TransactionTestCase):
    def setUp(self):
        self.a = Business.objects.create(name='Empresa A')
        self.b = Business.objects.create(name='Empresa B')
        self.user = get_user_model().objects.create_user(username='teste-fk')
        self.customer_a = Customer.objects.create(business=self.a, name='Cliente A')
        self.customer_b = Customer.objects.create(business=self.b, name='Cliente B')
        self.sale_a = self.make_sale(self.a, self.customer_a)
        self.sale_b = self.make_sale(self.b, self.customer_b)

    def make_sale(self, business, customer=None):
        return Sale.objects.create(
            business=business, customer=customer, total_amount=Decimal('10.00'),
            sold_at=timezone.now(), created_by=self.user,
        )

    def make_comanda(self, business, customer=None, sale=None):
        return Comanda.objects.create(
            business=business, customer=customer, sale=sale, opened_by=self.user,
        )

    def make_receivable(self, business, customer, sale):
        return Receivable.objects.create(
            business=business, customer=customer, sale=sale,
            original_amount=Decimal('5.00'),
        )

    def test_cross_business_relationships_are_rejected(self):
        attempts = (
            lambda: self.make_sale(self.a, self.customer_b),
            lambda: self.make_comanda(self.a, customer=self.customer_b),
            lambda: self.make_comanda(self.a, sale=self.sale_b),
            lambda: self.make_receivable(self.a, self.customer_b, self.sale_a),
            lambda: self.make_receivable(self.a, self.customer_a, self.sale_b),
        )
        for attempt in attempts:
            with self.subTest(attempt=attempt):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        attempt()

    def test_valid_and_optional_relationships_are_allowed(self):
        with transaction.atomic():
            sale = self.make_sale(self.a)
            self.make_comanda(self.a, sale=sale)
            self.make_comanda(self.a, customer=self.customer_a)
            self.make_receivable(self.a, self.customer_a, self.sale_a)
