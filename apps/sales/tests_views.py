from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.services import open_cash_session
from apps.customers.models import Customer

from .models import Comanda, Sale
from .services import add_comanda_item, create_sale, open_comanda

User = get_user_model()


class ComandaFinalizeViewTests(TestCase):
    """
    Garante o fluxo completo pela interface: registrar o pagamento
    parcial (inclusive inteiramente em fiado) via POST na tela da
    comanda, e só então finalizar — a finalização é bloqueada enquanto
    o saldo restante não for zero.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

        self.comanda = open_comanda(self.business, self.user, identifier='Mesa 5')
        add_comanda_item(self.comanda, 'Cerveja', Decimal('2'), Decimal('10.00'))

    def test_finalize_comanda_entirely_as_fiado_via_view(self):
        response = self.client.post(
            reverse('sales:comanda_detail', args=[self.comanda.pk]),
            data={
                'register_payment': '1',
                'method': 'fiado',
                'amount': '20.00',
                'customer': self.customer.pk,
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse('sales:comanda_finalize', args=[self.comanda.pk]),
        )
        self.assertEqual(response.status_code, 302)

        self.comanda.refresh_from_db()
        self.assertEqual(self.comanda.status, Comanda.STATUS_FINALIZED)

        sale = Sale.objects.get(business=self.business)
        self.assertEqual(sale.total_amount, Decimal('20.00'))
        self.assertEqual(sale.receivables.get().original_amount, Decimal('20.00'))

    def test_cannot_finalize_via_view_with_pending_balance(self):
        response = self.client.post(
            reverse('sales:comanda_finalize', args=[self.comanda.pk]),
        )
        self.assertEqual(response.status_code, 302)

        self.comanda.refresh_from_db()
        self.assertEqual(self.comanda.status, Comanda.STATUS_OPEN)


class SaleListPaymentMethodTotalsTests(TestCase):
    """
    Garante que a tela de Vendas exiba corretamente o total por forma de
    pagamento (incluindo Fiado) do mês selecionado.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_payment_method_totals_include_fiado_and_methods(self):
        create_sale(
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
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[{'method': 'pix', 'amount': Decimal('30.00')}],
        )

        response = self.client.get(reverse('sales:sale_list'))
        totals = {
            item['label']: item['total']
            for item in response.context['payment_method_totals']
        }

        self.assertEqual(totals['Pix'], Decimal('70.00'))
        self.assertEqual(totals['Dinheiro'], Decimal('20.00'))
        self.assertEqual(totals['Cartão de débito'], Decimal('0.00'))

        # Fiado não entra na lista por forma de pagamento (que representa
        # apenas valores já recebidos); é exibido separadamente via
        # received_sales_total/fiado_total para deixar claro o que já
        # entrou no caixa e o que ainda está pendente de recebimento.
        self.assertNotIn('Fiado', totals)
        self.assertEqual(response.context['received_sales_total'], Decimal('90.00'))
        self.assertEqual(response.context['received_fiado_total'], Decimal('0.00'))
        self.assertEqual(response.context['total_received'], Decimal('90.00'))
        self.assertEqual(response.context['fiado_total'], Decimal('40.00'))

    def test_monthly_sales_composition_and_receipts_use_different_dates(self):
        from apps.receivables.models import Receivable, ReceivablePayment
        from .models import SalePayment

        december = timezone.make_aware(timezone.datetime(2025, 12, 15, 12))
        january = timezone.make_aware(timezone.datetime(2026, 1, 15, 12))

        def sale(business, amount, sold_at, status=Sale.STATUS_COMPLETED):
            return Sale.objects.create(
                business=business, created_by=self.user, total_amount=Decimal(amount),
                sold_at=sold_at, status=status,
            )

        mixed = sale(self.business, '100.00', january)
        SalePayment.objects.create(sale=mixed, method='pix', amount=Decimal('60.00'), received_at=december)
        receivable = Receivable.objects.create(
            business=self.business, customer=self.customer, sale=mixed, original_amount=Decimal('40.00'),
        )
        ReceivablePayment.objects.create(
            receivable=receivable, amount=Decimal('10.00'), method='dinheiro',
            paid_at=january, received_by=self.user,
        )
        ReceivablePayment.objects.create(
            receivable=receivable, amount=Decimal('5.00'), method='dinheiro',
            paid_at=january, received_by=self.user, status=ReceivablePayment.STATUS_CANCELLED,
        )

        previous = sale(self.business, '20.00', december)
        SalePayment.objects.create(sale=previous, method='pix', amount=Decimal('20.00'), received_at=january)

        cancelled = sale(self.business, '80.00', january, Sale.STATUS_CANCELLED)
        SalePayment.objects.create(sale=cancelled, method='pix', amount=Decimal('80.00'), received_at=january)

        other_business = Business.objects.create(name='Outra empresa')
        other = sale(other_business, '999.00', january)
        SalePayment.objects.create(sale=other, method='pix', amount=Decimal('999.00'), received_at=january)

        response = self.client.get(reverse('sales:sale_list'), {'year': 2026, 'month': 1})
        self.assertEqual(response.context['month_total'], Decimal('100.00'))
        self.assertEqual(response.context['sales_paid_at_sale'], Decimal('60.00'))
        self.assertEqual(response.context['fiado_total'], Decimal('40.00'))
        self.assertEqual(response.context['received_sales_total'], Decimal('20.00'))
        self.assertEqual(response.context['received_fiado_total'], Decimal('10.00'))
        self.assertEqual(response.context['total_received'], Decimal('30.00'))

        response = self.client.get(reverse('sales:sale_list'), {'year': 2025, 'month': 12})
        self.assertEqual(response.context['month_total'], Decimal('20.00'))
        self.assertEqual(response.context['sales_paid_at_sale'], Decimal('20.00'))
        self.assertEqual(response.context['received_sales_total'], Decimal('60.00'))

    def test_received_by_sale_origin_reconciles_across_years_and_timezones(self):
        from apps.receivables.models import Receivable, ReceivablePayment
        from .models import SalePayment

        def at(year, month, day, hour=12, minute=0):
            return timezone.make_aware(timezone.datetime(year, month, day, hour, minute))

        received_at = at(2026, 1, 15)

        def make_sale(business, amount, sold_at, status=Sale.STATUS_COMPLETED):
            return Sale.objects.create(
                business=business, created_by=self.user, total_amount=Decimal(amount),
                sold_at=sold_at, status=status,
            )

        def direct(sale, amount):
            SalePayment.objects.create(
                sale=sale, method='pix', amount=Decimal(amount), received_at=received_at,
            )

        def credit_payment(sale, customer, amount, status=ReceivablePayment.STATUS_ACTIVE):
            receivable = Receivable.objects.create(
                business=sale.business, customer=customer, sale=sale,
                original_amount=Decimal('40.00'),
            )
            ReceivablePayment.objects.create(
                receivable=receivable, amount=Decimal(amount), method='dinheiro',
                paid_at=received_at, received_by=self.user, status=status,
            )
            return receivable

        current = make_sale(self.business, '80.00', at(2026, 1, 1, 0, 15))
        direct(current, '40.00')
        credit_payment(current, self.customer, '10.00')
        previous = make_sale(self.business, '40.00', at(2025, 12, 31, 23, 30))
        credit_payment(previous, self.customer, '20.00')
        credit_payment(previous, self.customer, '5.00', ReceivablePayment.STATUS_CANCELLED)
        later = make_sale(self.business, '30.00', at(2026, 2, 1))
        direct(later, '30.00')

        cancelled = make_sale(self.business, '90.00', at(2026, 1, 10), Sale.STATUS_CANCELLED)
        direct(cancelled, '90.00')

        other_business = Business.objects.create(name='Outra empresa')
        other_customer = Customer.objects.create(business=other_business, name='Outra cliente')
        other = make_sale(other_business, '100.00', at(2026, 1, 10))
        direct(other, '60.00')
        credit_payment(other, other_customer, '20.00')

        response = self.client.get(reverse('sales:sale_list'), {'year': 2026, 'month': 1})
        self.assertEqual(response.context['received_sales_total'], Decimal('70.00'))
        self.assertEqual(response.context['received_fiado_total'], Decimal('30.00'))
        self.assertEqual(
            response.context['received_sales_total'] + response.context['received_fiado_total'],
            response.context['total_received'],
        )
        self.assertEqual(response.context['total_received'], Decimal('100.00'))

    def test_received_fiado_total_counts_debt_payments_received_this_month(self):
        """
        Recebido Fiado deve somar pagamentos de dívidas efetivamente
        recebidos no mês selecionado, separadamente de Recebido Vendas,
        mesmo que a venda de origem tenha sido feita em outro mês.
        """
        from apps.receivables.services import register_customer_payment

        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('50.00'),
        )
        register_customer_payment(self.customer, self.user, Decimal('30.00'), 'dinheiro', timezone.now())

        response = self.client.get(reverse('sales:sale_list'))

        self.assertEqual(response.context['received_fiado_total'], Decimal('30.00'))
        self.assertEqual(response.context['received_sales_total'], Decimal('0.00'))
        self.assertEqual(response.context['total_received'], Decimal('30.00'))
        self.assertEqual(response.context['fiado_total'], Decimal('50.00'))
        self.assertContains(response, 'Fiado lançado no mês')
        self.assertContains(response, 'não representa o saldo atual em aberto')
        self.assertContains(response, 'id="toggle-values-btn"')
        self.assertContains(response, 'aria-label="Mês anterior"')
        self.assertContains(response, 'aria-label="Próximo mês"')


class SaleListGroupedByDayTests(TestCase):
    """Garante que as vendas sejam agrupadas corretamente por dia, com total e contagem."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_sales_are_grouped_by_day_with_total_and_count(self):
        today = timezone.localdate()
        today_dt = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time().replace(hour=10))
        )

        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('20.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('20.00')}],
            sold_at=today_dt,
        )
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[{'method': 'pix', 'amount': Decimal('30.00')}],
            sold_at=today_dt.replace(hour=15),
        )

        response = self.client.get(reverse('sales:sale_list'))
        groups = response.context['sales_by_day']

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['day'], today)
        self.assertEqual(groups[0]['total'], Decimal('50.00'))
        self.assertEqual(groups[0]['count'], 2)

    def test_sales_by_day_includes_fiado_breakdown(self):
        """Cada grupo de dia deve indicar quanto do total vendido foi fiado."""
        today = timezone.localdate()
        today_dt = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time().replace(hour=10))
        )
        customer = Customer.objects.create(business=self.business, name='Cliente Teste')

        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('100.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('70.00')}],
            customer=customer,
            fiado_amount=Decimal('30.00'),
            sold_at=today_dt,
        )

        response = self.client.get(reverse('sales:sale_list'))
        groups = response.context['sales_by_day']

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['total'], Decimal('100.00'))
        self.assertEqual(groups[0]['fiado_total'], Decimal('30.00'))
        self.assertEqual(groups[0]['received_fiado_total'], Decimal('0.00'))

    def test_sales_by_day_includes_received_fiado_payment_on_its_own_day(self):
        """
        Um recebimento de fiado deve aparecer no dia em que foi recebido,
        mesmo que seja referente a uma venda de um dia anterior, e mesmo
        que não haja nenhuma venda nova naquele dia específico.
        """
        from apps.receivables.services import register_customer_payment

        customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[],
            customer=customer,
            fiado_amount=Decimal('50.00'),
        )
        register_customer_payment(customer, self.user, Decimal('30.00'), 'dinheiro', timezone.now())

        response = self.client.get(reverse('sales:sale_list'))
        groups = {entry['day']: entry for entry in response.context['sales_by_day']}
        today = timezone.localdate()

        self.assertIn(today, groups)
        self.assertEqual(groups[today]['received_fiado_total'], Decimal('30.00'))

    def test_sale_near_midnight_local_time_is_grouped_on_correct_day(self):
        """
        Regressão: uma venda feita perto da meia-noite no horário local
        (America/Sao_Paulo, UTC-3) deve ser agrupada no dia local correto,
        mesmo que em UTC a data já seja o dia seguinte.
        """
        from django.utils import timezone

        today = timezone.localdate()
        # 23h30 no horário local de Brasília (UTC-3) -> 02h30 UTC do dia seguinte.
        late_night_local = timezone.make_aware(
            timezone.datetime.combine(
                today, timezone.datetime.min.time().replace(hour=23, minute=30)
            )
        )

        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('15.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('15.00')}],
            sold_at=late_night_local,
        )

        response = self.client.get(reverse('sales:sale_list'))
        groups = response.context['sales_by_day']

        self.assertEqual(len(groups), 1)
        # A venda deve aparecer no dia local real (hoje), não no dia seguinte em UTC.
        self.assertEqual(groups[0]['day'], today)
        self.assertEqual(groups[0]['total'], Decimal('15.00'))
        self.assertEqual(groups[0]['count'], 1)
