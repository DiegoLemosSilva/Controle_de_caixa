from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.services import open_cash_session
from apps.receivables.services import register_customer_payment
from apps.sales.services import create_sale

from .models import Customer

User = get_user_model()


class CustomerDetailViewTests(TestCase):
    """
    Garante que a tela de detalhe do cliente exiba o valor total devido,
    permita registrar o recebimento (distribuído automaticamente entre
    as dívidas em aberto) e mostre o histórico combinado de compras
    (fiado) e pagamentos.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Baiano')

        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_detail_shows_total_open_balance(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('40.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('40.00'),
        )

        response = self.client.get(
            reverse('customers:customer_detail', args=[self.customer.pk])
        )
        self.assertEqual(response.context['open_balance'], Decimal('40.00'))
        self.assertTrue(response.context['has_open_receivable'])

    def test_detail_hides_payment_button_without_open_receivable(self):
        response = self.client.get(
            reverse('customers:customer_detail', args=[self.customer.pk])
        )
        self.assertFalse(response.context['has_open_receivable'])
        self.assertNotContains(response, 'Receber pagamento')

    def test_history_includes_purchase_and_payment_entries(self):
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('50.00'),
        )
        register_customer_payment(self.customer, self.user, Decimal('20.00'), 'dinheiro', timezone.now())

        response = self.client.get(
            reverse('customers:customer_detail', args=[self.customer.pk])
        )
        history = response.context['history']

        purchase_entries = [entry for entry in history if entry['type'] == 'purchase']
        payment_entries = [entry for entry in history if entry['type'] == 'payment']

        self.assertEqual(len(purchase_entries), 1)
        self.assertEqual(len(payment_entries), 1)
        self.assertEqual(payment_entries[0]['payment'].amount, Decimal('20.00'))

    def test_register_payment_via_detail_view_reduces_balance(self):
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('50.00'),
        )
        receivable = sale.receivables.get()

        response = self.client.post(
            reverse('customers:customer_detail', args=[self.customer.pk]),
            data={
                'paid_at': timezone.localdate().isoformat(),
                'amount': '20.00',
                'method': 'dinheiro',
            },
        )
        self.assertEqual(response.status_code, 200)

        receivable.refresh_from_db()
        self.assertEqual(receivable.balance, Decimal('30.00'))


class RegisterCustomerPaymentServiceTests(TestCase):
    """
    Testes do serviço de recebimento agregado: o valor pago é
    distribuído automaticamente entre as dívidas em aberto do cliente,
    da mais antiga para a mais nova (FIFO), sem exigir que o usuário
    escolha manualmente qual venda está sendo quitada.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Baiano')

        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

    def test_payment_settles_single_open_receivable(self):
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('30.00'),
        )
        receivable = sale.receivables.get()

        register_customer_payment(self.customer, self.user, Decimal('30.00'), 'dinheiro', timezone.now())

        receivable.refresh_from_db()
        self.assertEqual(receivable.balance, Decimal('0.00'))
        self.assertEqual(receivable.status, 'paid')

    def test_payment_is_distributed_across_multiple_receivables_fifo(self):
        sale_1 = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('20.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('20.00'),
        )
        sale_2 = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('30.00'),
        )
        receivable_1 = sale_1.receivables.get()
        receivable_2 = sale_2.receivables.get()

        # Paga R$ 25,00: deve quitar totalmente a primeira dívida (R$ 20,00)
        # e abater R$ 5,00 da segunda, sem exigir seleção manual.
        payments = register_customer_payment(
            self.customer, self.user, Decimal('25.00'), 'dinheiro', timezone.now()
        )

        receivable_1.refresh_from_db()
        receivable_2.refresh_from_db()

        self.assertEqual(receivable_1.balance, Decimal('0.00'))
        self.assertEqual(receivable_1.status, 'paid')
        self.assertEqual(receivable_2.balance, Decimal('25.00'))
        self.assertEqual(receivable_2.status, 'open')
        self.assertEqual(len(payments), 2)

    def test_payment_above_total_open_balance_is_rejected(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('10.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('10.00'),
        )

        with self.assertRaises(ValidationError):
            register_customer_payment(
                self.customer, self.user, Decimal('50.00'), 'dinheiro', timezone.now()
            )

    def test_payment_with_custom_date(self):
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('15.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('15.00'),
        )

        custom_date = timezone.now()
        payments = register_customer_payment(
            self.customer, self.user, Decimal('15.00'), 'pix', custom_date
        )
        self.assertEqual(payments[0].paid_at, custom_date)
