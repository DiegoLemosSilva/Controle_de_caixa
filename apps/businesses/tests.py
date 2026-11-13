from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.customers.models import Customer

from .models import Business, BusinessOwner
from .services import OPERATOR_GROUP_NAME

User = get_user_model()


class BusinessIsolationTests(TestCase):
    """Garante que dados de uma empresa nunca sejam visíveis para outra."""

    def setUp(self):
        self.business_a = Business.objects.create(name='Empresa A')
        self.business_b = Business.objects.create(name='Empresa B')

        self.user_a = User.objects.create_user(username='user_a', password='senha12345')
        self.user_b = User.objects.create_user(username='user_b', password='senha12345')

        BusinessOwner.objects.create(user=self.user_a, business=self.business_a)
        BusinessOwner.objects.create(user=self.user_b, business=self.business_b)

        self.customer_a = Customer.objects.create(business=self.business_a, name='Cliente A')
        self.customer_b = Customer.objects.create(business=self.business_b, name='Cliente B')

    def test_user_only_sees_own_business_customers(self):
        client = Client()
        client.login(username='user_a', password='senha12345')

        response = client.get(reverse('customers:customer_list'))
        self.assertContains(response, 'Cliente A')
        self.assertNotContains(response, 'Cliente B')

    def test_user_cannot_access_other_business_customer_detail_by_url(self):
        """Mesmo manipulando a URL, o usuário não pode acessar dados de outra empresa."""
        client = Client()
        client.login(username='user_a', password='senha12345')

        response = client.get(
            reverse('customers:customer_detail', args=[self.customer_b.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_is_redirected_to_login(self):
        client = Client()
        response = client.get(reverse('cash:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_user_without_business_is_denied(self):
        user_without_business = User.objects.create_user(
            username='sem_empresa', password='senha12345'
        )
        client = Client()
        client.login(username='sem_empresa', password='senha12345')

        response = client.get(reverse('cash:dashboard'))
        self.assertEqual(response.status_code, 403)


class OperatorGroupRestrictionTests(TestCase):
    """
    Garante que usuários do grupo "Operador" só acessem as
    funcionalidades do Caixa (vendas, comandas e conferência de caixa),
    conforme AGENTS.md: acesso restrito por papel dentro da empresa.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')

        self.operator_group, _ = Group.objects.get_or_create(name=OPERATOR_GROUP_NAME)

        self.operator = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.operator, business=self.business)
        self.operator.groups.add(self.operator_group)

        self.manager = User.objects.create_user(username='gerente', password='senha12345')
        BusinessOwner.objects.create(user=self.manager, business=self.business)

        self.client = Client()

    def test_operator_can_access_cash_dashboard(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('cash:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_operator_can_access_sale_create(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('sales:sale_create'))
        self.assertEqual(response.status_code, 200)

    def test_operator_can_access_comanda_create(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('sales:comanda_create'))
        self.assertEqual(response.status_code, 200)

    def test_operator_is_denied_sale_list(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('sales:sale_list'))
        self.assertEqual(response.status_code, 403)

    def test_operator_is_denied_customers(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('customers:customer_list'))
        self.assertEqual(response.status_code, 403)

    def test_operator_is_denied_payables(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('payables:payable_list'))
        self.assertEqual(response.status_code, 403)

    def test_operator_is_denied_planning(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('planning:plan_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_operator_is_denied_ai_assistant(self):
        self.client.login(username='operador', password='senha12345')
        response = self.client.get(reverse('ai_assistant:analysis_list'))
        self.assertEqual(response.status_code, 403)

    def test_operator_cannot_reopen_cash_session(self):
        """
        A reabertura de um caixa fechado é uma decisão gerencial: o
        grupo Operador nunca pode acessar essa view, independentemente
        de qualquer configuração de permissão.
        """
        from datetime import date as date_cls
        from decimal import Decimal

        from apps.cash.services import close_cash_session, open_cash_session, register_cash_count

        today = date_cls.today()
        open_cash_session(self.business, self.manager, today, Decimal('0.00'))
        for method in ['dinheiro', 'pix', 'debito', 'credito', 'outro']:
            register_cash_count(
                business=self.business,
                user=self.manager,
                date=today,
                payment_method=method,
                counted_amount=Decimal('0.00'),
                reason='',
            )
        close_cash_session(self.business, self.manager, today)

        self.client.login(username='operador', password='senha12345')
        response = self.client.post(
            reverse('cash:reopen_day'),
            data={'date': today, 'reason': 'Tentando reabrir'},
        )
        self.assertEqual(response.status_code, 403)

    def test_non_operator_can_reopen_cash_session(self):
        """Um usuário fora do grupo Operador continua podendo reabrir o caixa."""
        from datetime import date as date_cls
        from decimal import Decimal

        from apps.cash.services import (
            close_cash_session,
            is_date_closed,
            open_cash_session,
            register_cash_count,
        )

        today = date_cls.today()
        open_cash_session(self.business, self.manager, today, Decimal('0.00'))
        for method in ['dinheiro', 'pix', 'debito', 'credito', 'outro']:
            register_cash_count(
                business=self.business,
                user=self.manager,
                date=today,
                payment_method=method,
                counted_amount=Decimal('0.00'),
                reason='',
            )
        close_cash_session(self.business, self.manager, today)

        self.client.login(username='gerente', password='senha12345')
        response = self.client.post(
            reverse('cash:reopen_day'),
            data={'date': today, 'reason': 'Correção de lançamento'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(is_date_closed(self.business, today))

    def test_non_operator_has_full_access(self):
        """Um usuário fora do grupo Operador continua com acesso total."""
        self.client.login(username='gerente', password='senha12345')

        self.assertEqual(self.client.get(reverse('cash:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('sales:sale_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('customers:customer_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('payables:payable_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('planning:plan_dashboard')).status_code, 200)
