from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.businesses.models import Business, BusinessOwner

from .models import Product

User = get_user_model()


class ProductModelTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')

    def test_product_rejects_non_positive_price(self):
        product = Product(business=self.business, name='Refrigerante', price=Decimal('0.00'))
        with self.assertRaises(ValidationError):
            product.full_clean()


class ProductViewTests(TestCase):
    """
    Garante o isolamento entre empresas e o fluxo básico de cadastro de
    produtos (CRUD simples, sem controle de estoque).
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

        self.other_business = Business.objects.create(name='Outra Empresa')
        self.other_user = User.objects.create_user(username='outro', password='senha12345')
        BusinessOwner.objects.create(user=self.other_user, business=self.other_business)

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_create_product_via_view(self):
        response = self.client.post(
            reverse('products:product_create'),
            data={'name': 'Cerveja Long Neck', 'price': '8.50', 'is_active': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(business=self.business, name='Cerveja Long Neck')
        self.assertEqual(product.price, Decimal('8.50'))

    def test_product_list_only_shows_own_business_products(self):
        own_product = Product.objects.create(
            business=self.business, name='Água', price=Decimal('3.00')
        )
        other_product = Product.objects.create(
            business=self.other_business, name='Refrigerante', price=Decimal('5.00')
        )

        response = self.client.get(reverse('products:product_list'))
        products = list(response.context['products'])

        self.assertIn(own_product, products)
        self.assertNotIn(other_product, products)

    def test_cannot_update_product_from_another_business(self):
        other_product = Product.objects.create(
            business=self.other_business, name='Refrigerante', price=Decimal('5.00')
        )

        response = self.client.post(
            reverse('products:product_update', args=[other_product.pk]),
            data={'name': 'Hackeado', 'price': '1.00', 'is_active': 'on'},
        )

        self.assertEqual(response.status_code, 404)
        other_product.refresh_from_db()
        self.assertEqual(other_product.name, 'Refrigerante')
