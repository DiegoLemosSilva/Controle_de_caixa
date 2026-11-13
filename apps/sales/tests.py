from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.services import open_cash_session
from apps.customers.models import Customer
from apps.receivables.models import Receivable

from .models import Comanda, Sale
from .services import (
    add_comanda_item,
    cancel_sale,
    create_sale,
    delete_empty_comanda,
    finalize_comanda,
    open_comanda,
    register_comanda_payment,
    remove_comanda_item,
    remove_comanda_payment,
    update_comanda_item,
    update_comanda_payment,
)

User = get_user_model()


class SaleServiceTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

    def test_create_sale_with_pix_cash_and_fiado(self):
        """Venda de R$100 dividida em Pix 40 + Dinheiro 20 + Fiado 40 (exemplo do AGENTS.md)."""
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('100.00'),
            payments=[
                {'method': 'pix', 'amount': Decimal('40.00')},
                {'method': 'dinheiro', 'amount': Decimal('20.00')},
            ],
            customer=self.customer,
            fiado_amount=Decimal('40.00'),
        )

        self.assertEqual(sale.total_amount, Decimal('100.00'))
        self.assertEqual(sale.payments.count(), 2)

        receivable = Receivable.objects.get(sale=sale)
        self.assertEqual(receivable.original_amount, Decimal('40.00'))
        self.assertEqual(receivable.balance, Decimal('40.00'))

        # Nenhuma receita duplicada: soma de pagamentos + fiado = total da venda.
        payments_total = sum(p.amount for p in sale.payments.all())
        self.assertEqual(payments_total + receivable.original_amount, sale.total_amount)

    def test_create_sale_rejects_amount_mismatch(self):
        with self.assertRaises(ValidationError):
            create_sale(
                business=self.business,
                user=self.user,
                total_amount=Decimal('100.00'),
                payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
                customer=self.customer,
                fiado_amount=Decimal('40.00'),
            )

    def test_create_sale_rejects_fiado_without_customer(self):
        with self.assertRaises(ValidationError):
            create_sale(
                business=self.business,
                user=self.user,
                total_amount=Decimal('40.00'),
                payments=[],
                customer=None,
                fiado_amount=Decimal('40.00'),
            )

    def test_cancel_sale_cannot_be_cancelled_twice(self):
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('30.00')}],
        )
        cancel_sale(sale, self.user, 'Erro de lançamento')
        sale.refresh_from_db()
        self.assertTrue(sale.is_cancelled)

        with self.assertRaises(ValidationError):
            cancel_sale(sale, self.user, 'Tentando cancelar de novo')


class ComandaServiceTests(TestCase):
    """
    Testes do fluxo de comanda com pagamentos parciais: várias pessoas
    da mesma mesa podem pagar partes diferentes da conta, cada uma com
    sua forma de pagamento, até o saldo chegar a zero — só então a
    comanda pode ser finalizada.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

    def test_finalize_comanda_creates_single_sale(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        add_comanda_item(comanda, 'Cerveja', Decimal('2'), Decimal('10.00'))
        add_comanda_item(comanda, 'Porção', Decimal('1'), Decimal('30.00'))

        self.assertEqual(comanda.total_amount, Decimal('50.00'))

        register_comanda_payment(comanda, 'dinheiro', Decimal('50.00'), self.user)
        sale = finalize_comanda(comanda, self.user)

        self.assertEqual(Sale.objects.filter(business=self.business).count(), 1)
        comanda.refresh_from_db()
        self.assertEqual(comanda.sale, sale)
        self.assertFalse(comanda.is_open)
        self.assertEqual(sale.total_amount, Decimal('50.00'))
        self.assertEqual(sale.payments.get().amount, Decimal('50.00'))

    def test_comanda_cannot_be_finalized_twice(self):
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('20.00'))
        register_comanda_payment(comanda, 'dinheiro', Decimal('20.00'), self.user)

        finalize_comanda(comanda, self.user)

        with self.assertRaises(ValidationError):
            finalize_comanda(comanda, self.user)

    def test_cannot_finalize_empty_comanda(self):
        comanda = open_comanda(self.business, self.user)
        with self.assertRaises(ValidationError):
            finalize_comanda(comanda, self.user)

    def test_cannot_finalize_comanda_with_pending_balance(self):
        """A comanda só pode ser finalizada quando o saldo restante for zero."""
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('100.00'))
        register_comanda_payment(comanda, 'dinheiro', Decimal('60.00'), self.user)

        self.assertEqual(comanda.balance, Decimal('40.00'))
        with self.assertRaises(ValidationError):
            finalize_comanda(comanda, self.user)

    def test_split_payment_among_multiple_people(self):
        """
        Exemplo do cenário real: comanda de R$100, 3 pessoas dividindo
        a conta: 25 em dinheiro, 30 em Pix e o restante em dinheiro.
        """
        comanda = open_comanda(self.business, self.user, identifier='Mesa 5')
        add_comanda_item(comanda, 'Itens da mesa', Decimal('1'), Decimal('100.00'))

        register_comanda_payment(comanda, 'dinheiro', Decimal('25.00'), self.user)
        self.assertEqual(comanda.balance, Decimal('75.00'))

        register_comanda_payment(comanda, 'pix', Decimal('30.00'), self.user)
        self.assertEqual(comanda.balance, Decimal('45.00'))

        register_comanda_payment(comanda, 'dinheiro', Decimal('45.00'), self.user)
        self.assertEqual(comanda.balance, Decimal('0.00'))

        sale = finalize_comanda(comanda, self.user)

        self.assertEqual(sale.total_amount, Decimal('100.00'))
        # Os dois pagamentos em dinheiro (25 + 45) permanecem como dois
        # SalePayment separados (um por registro parcial), somando
        # corretamente, mais um de Pix R$ 30,00.
        self.assertEqual(sale.payments.count(), 3)
        self.assertEqual(
            sum(p.amount for p in sale.payments.filter(method='dinheiro')), Decimal('70.00')
        )
        self.assertEqual(
            sum(p.amount for p in sale.payments.filter(method='pix')), Decimal('30.00')
        )

    def test_payment_rejects_amount_exceeding_balance(self):
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('50.00'))

        with self.assertRaises(ValidationError):
            register_comanda_payment(comanda, 'dinheiro', Decimal('60.00'), self.user)

    def test_fiado_payment_requires_customer(self):
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('50.00'))

        with self.assertRaises(ValidationError):
            register_comanda_payment(comanda, 'fiado', Decimal('50.00'), self.user, customer=None)

    def test_fiado_payment_with_own_customer_creates_receivable(self):
        """
        Um pagamento parcial em fiado pode ter um cliente diferente do
        cliente vinculado à comanda (ex: uma pessoa específica da mesa
        ficou devendo, não a mesa como um todo).
        """
        other_customer = Customer.objects.create(business=self.business, name='Outro Cliente')
        comanda = open_comanda(self.business, self.user, identifier='Mesa 5')
        add_comanda_item(comanda, 'Itens', Decimal('1'), Decimal('100.00'))

        register_comanda_payment(comanda, 'dinheiro', Decimal('60.00'), self.user)
        register_comanda_payment(
            comanda, 'fiado', Decimal('40.00'), self.user, customer=other_customer
        )

        sale = finalize_comanda(comanda, self.user)

        receivable = Receivable.objects.get(sale=sale)
        self.assertEqual(receivable.customer, other_customer)
        self.assertEqual(receivable.original_amount, Decimal('40.00'))

    def test_multiple_fiado_payments_same_customer_consolidate_into_one_receivable(self):
        """Dois pagamentos em fiado do mesmo cliente geram um único Receivable."""
        comanda = open_comanda(self.business, self.user)
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('100.00'))

        register_comanda_payment(
            comanda, 'fiado', Decimal('30.00'), self.user, customer=self.customer
        )
        register_comanda_payment(
            comanda, 'fiado', Decimal('70.00'), self.user, customer=self.customer
        )

        sale = finalize_comanda(comanda, self.user)

        self.assertEqual(Receivable.objects.filter(sale=sale).count(), 1)
        receivable = Receivable.objects.get(sale=sale)
        self.assertEqual(receivable.customer, self.customer)
        self.assertEqual(receivable.original_amount, Decimal('100.00'))

    def test_delete_empty_comanda_removes_it(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 9')
        comanda_pk = comanda.pk

        delete_empty_comanda(comanda)

        self.assertFalse(Comanda.objects.filter(pk=comanda_pk).exists())

    def test_cannot_delete_comanda_with_items(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 9')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('10.00'))

        with self.assertRaises(ValidationError):
            delete_empty_comanda(comanda)

    def test_cannot_delete_finalized_comanda(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 9')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('10.00'))
        register_comanda_payment(comanda, 'dinheiro', Decimal('10.00'), self.user)
        finalize_comanda(comanda, self.user)
        comanda.refresh_from_db()

        with self.assertRaises(ValidationError):
            delete_empty_comanda(comanda)

    def test_update_comanda_item_changes_values(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        item = add_comanda_item(comanda, 'Cerveja', Decimal('2'), Decimal('10.00'))

        update_comanda_item(item, 'Cerveja Long Neck', Decimal('3'), Decimal('12.00'))

        item.refresh_from_db()
        self.assertEqual(item.description, 'Cerveja Long Neck')
        self.assertEqual(item.quantity, Decimal('3'))
        self.assertEqual(item.unit_price, Decimal('12.00'))
        self.assertEqual(comanda.total_amount, Decimal('36.00'))

    def test_remove_comanda_item_deletes_it(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        item = add_comanda_item(comanda, 'Cerveja', Decimal('2'), Decimal('10.00'))
        add_comanda_item(comanda, 'Porção', Decimal('1'), Decimal('30.00'))

        remove_comanda_item(item)

        self.assertEqual(comanda.items.count(), 1)
        self.assertEqual(comanda.total_amount, Decimal('30.00'))

    def test_cannot_edit_or_remove_item_after_comanda_finalized(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        item = add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('20.00'))
        register_comanda_payment(comanda, 'dinheiro', Decimal('20.00'), self.user)

        finalize_comanda(comanda, self.user)
        comanda.refresh_from_db()

        with self.assertRaises(ValidationError):
            update_comanda_item(item, 'Item editado', Decimal('1'), Decimal('25.00'))

        with self.assertRaises(ValidationError):
            remove_comanda_item(item)

    def test_update_comanda_payment_changes_values_and_balance(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('100.00'))
        payment = register_comanda_payment(comanda, 'dinheiro', Decimal('30.00'), self.user)

        update_comanda_payment(payment, 'pix', Decimal('50.00'))

        payment.refresh_from_db()
        self.assertEqual(payment.method, 'pix')
        self.assertEqual(payment.amount, Decimal('50.00'))
        self.assertEqual(comanda.balance, Decimal('50.00'))

    def test_update_comanda_payment_rejects_amount_exceeding_available_balance(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('100.00'))
        payment_1 = register_comanda_payment(comanda, 'dinheiro', Decimal('30.00'), self.user)
        register_comanda_payment(comanda, 'pix', Decimal('40.00'), self.user)

        # Saldo restante é 30; o valor disponível para este pagamento é
        # 30 (saldo) + 30 (valor atual dele) = 60. Pedir mais que isso deve falhar.
        with self.assertRaises(ValidationError):
            update_comanda_payment(payment_1, 'dinheiro', Decimal('70.00'))

    def test_update_comanda_payment_to_fiado_requires_customer(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('50.00'))
        payment = register_comanda_payment(comanda, 'dinheiro', Decimal('50.00'), self.user)

        with self.assertRaises(ValidationError):
            update_comanda_payment(payment, 'fiado', Decimal('50.00'), customer=None)

    def test_remove_comanda_payment_restores_balance(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('100.00'))
        payment = register_comanda_payment(comanda, 'dinheiro', Decimal('40.00'), self.user)

        self.assertEqual(comanda.balance, Decimal('60.00'))
        remove_comanda_payment(payment)
        self.assertEqual(comanda.balance, Decimal('100.00'))

    def test_cannot_edit_or_remove_payment_after_comanda_finalized(self):
        comanda = open_comanda(self.business, self.user, identifier='Mesa 1')
        add_comanda_item(comanda, 'Item', Decimal('1'), Decimal('20.00'))
        payment = register_comanda_payment(comanda, 'dinheiro', Decimal('20.00'), self.user)

        finalize_comanda(comanda, self.user)
        payment.refresh_from_db()

        with self.assertRaises(ValidationError):
            update_comanda_payment(payment, 'pix', Decimal('20.00'))

        with self.assertRaises(ValidationError):
            remove_comanda_payment(payment)
