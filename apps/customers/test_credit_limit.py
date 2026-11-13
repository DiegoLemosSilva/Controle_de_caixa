from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.services import open_cash_session
from apps.receivables.services import register_customer_payment
from apps.sales.models import ComandaPayment
from apps.sales.services import (
    add_comanda_item, cancel_sale, create_sale, open_comanda, register_comanda_payment,
)

from .forms import CustomerForm
from .models import Customer
from .services import credit_balances, projected_credit


class CustomerCreditTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa')
        self.other_business = Business.objects.create(name='Outra empresa')
        self.user = get_user_model().objects.create_user(username='cliente-teste', password='senha')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(
            business=self.business, name='Ana', credit_limit=Decimal('50.00')
        )
        self.other_customer = Customer.objects.create(
            business=self.other_business, name='Ana outra', credit_limit=Decimal('10.00')
        )
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))
        self.client.force_login(self.user)

    def test_optional_zero_and_negative_limit(self):
        base = {'name': 'Cliente', 'is_active': 'on'}
        self.assertTrue(CustomerForm({**base, 'credit_limit': ''}).is_valid())
        self.assertTrue(CustomerForm({**base, 'credit_limit': '0.00'}).is_valid())
        self.assertFalse(CustomerForm({**base, 'credit_limit': '-1.00'}).is_valid())

    def test_balances_and_total_exclude_open_comandas_and_other_business(self):
        create_sale(
            self.business, self.user, Decimal('50.00'), [], customer=self.customer,
            fiado_amount=Decimal('50.00'),
        )
        register_customer_payment(self.customer, self.user, Decimal('20.00'), 'dinheiro', timezone.now())
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('25.00'))
        register_comanda_payment(comanda, 'fiado', Decimal('25.00'), self.user, self.customer)

        balances = credit_balances(self.business)
        self.assertEqual(balances[self.customer.pk]['open_balance'], Decimal('30.00'))
        self.assertEqual(projected_credit(self.customer, balances), Decimal('55.00'))
        self.assertNotIn(self.other_customer.pk, balances)
        response = self.client.get(reverse('customers:customer_list'), {'q': 'ANA'})
        self.assertEqual(response.context['total_open_credit'], Decimal('30.00'))
        self.assertEqual(list(response.context['customers']), [self.customer])
        self.assertNotContains(response, 'Ana outra')

    def test_list_total_is_not_limited_by_filter(self):
        other = Customer.objects.create(business=self.business, name='Bruno', is_active=False)
        for customer, amount in [(self.customer, Decimal('20.00')), (other, Decimal('30.00'))]:
            create_sale(self.business, self.user, amount, [], customer=customer, fiado_amount=amount)
        response = self.client.get(reverse('customers:customer_list'), {'q': 'Ana'})
        self.assertEqual(response.context['total_open_credit'], Decimal('50.00'))
        self.assertContains(response, 'data-value="20,00"')
        self.assertNotContains(response, 'Bruno')

    def test_cancelled_sale_does_not_count(self):
        sale = create_sale(
            self.business, self.user, Decimal('20.00'), [], customer=self.customer,
            fiado_amount=Decimal('20.00'),
        )
        cancel_sale(sale, self.user, 'Cancelamento')
        self.assertNotIn(self.customer.pk, credit_balances(self.business))

    def test_edit_comanda_payment_at_limit_does_not_warn_or_double_count(self):
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('100.00'))
        payment = register_comanda_payment(
            comanda, 'fiado', Decimal('40.00'), self.user, self.customer,
        )
        response = self.client.post(reverse('sales:comanda_detail', args=[comanda.pk]), {
            'edit_payment': '1', 'payment_id': payment.pk, 'method': 'fiado',
            'amount': '50.00', 'customer': self.customer.pk,
        })
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal('50.00'))
        self.assertNotContains(response, 'limite de fiado de Ana foi ultrapassado')
        self.assertEqual(projected_credit(self.customer, credit_balances(self.business)), Decimal('50.00'))

    def test_sale_above_limit_is_recorded_and_warned(self):
        response = self.client.post(reverse('sales:sale_create'), {
            'description': 'Venda', 'sold_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'customer': self.customer.pk, 'fiado_amount': '60.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.customer.receivables.get().original_amount, Decimal('60.00'))
        self.assertTrue(any('limite de fiado' in str(message).lower()
                            for message in get_messages(response.wsgi_request)))

    def test_comanda_above_limit_is_recorded_and_warned(self):
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('60.00'))
        response = self.client.post(reverse('sales:comanda_detail', args=[comanda.pk]), {
            'register_payment': '1', 'method': 'fiado',
            'amount': '60.00', 'customer': self.customer.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ComandaPayment.objects.filter(comanda=comanda, customer=self.customer).exists())
        self.assertContains(response, 'limite de fiado de Ana foi ultrapassado')
        self.assertEqual(self.customer.receivables.count(), 0)

    def test_other_business_customer_is_not_accepted_in_sale(self):
        response = self.client.post(reverse('sales:sale_create'), {
            'description': 'Venda', 'sold_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'customer': self.other_customer.pk, 'fiado_amount': '60.00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.other_customer.receivables.exists())
