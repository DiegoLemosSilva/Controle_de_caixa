from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.customers.models import Customer
from apps.payables.models import Payable
from apps.payables.services import register_payment as pay_payable
from apps.receivables.services import register_payment as pay_receivable
from apps.sales.services import create_sale, open_comanda

from .models import CashCountAdjustment, CashSession
from .services import (
    all_methods_checked,
    build_summary,
    cash_adjustments_total,
    close_cash_session,
    daily_revenue,
    ensure_date_open,
    expected_amount_for_method,
    is_date_closed,
    latest_adjustments_for_date,
    open_cash_session,
    paid_expenses_total,
    receipts_total,
    register_cash_count,
    reopen_cash_session,
    sales_total,
)

User = get_user_model()

ALL_PAYMENT_METHODS = ['dinheiro', 'pix', 'debito', 'credito', 'outro']


class CashSessionOpenCloseTests(TestCase):
    """
    Garante o novo padrão: por default o caixa está fechado para
    qualquer data (regra de caixa único e abertura obrigatória).
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.today = timezone.localdate()

    def test_date_is_closed_by_default_without_any_session(self):
        self.assertTrue(is_date_closed(self.business, self.today))

    def test_cannot_create_sale_without_open_session(self):
        with self.assertRaises(ValidationError):
            create_sale(
                business=self.business,
                user=self.user,
                total_amount=Decimal('10.00'),
                payments=[{'method': 'dinheiro', 'amount': Decimal('10.00')}],
            )

    def test_open_cash_session_allows_sale(self):
        open_cash_session(self.business, self.user, self.today, Decimal('100.00'))
        self.assertFalse(is_date_closed(self.business, self.today))

        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('10.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('10.00')}],
        )
        self.assertEqual(sale.total_amount, Decimal('10.00'))

    def test_cannot_open_second_session_while_one_is_open(self):
        open_cash_session(self.business, self.user, self.today, Decimal('50.00'))

        tomorrow = self.today + timezone.timedelta(days=1)
        with self.assertRaises(ValidationError):
            open_cash_session(self.business, self.user, tomorrow, Decimal('0.00'))

    def test_cannot_open_session_twice_for_same_date(self):
        open_cash_session(self.business, self.user, self.today, Decimal('50.00'))
        close_cash_session_for_test(self, self.today)

        with self.assertRaises(ValidationError):
            open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

    def test_opening_amount_is_separate_from_sales_indicator(self):
        open_cash_session(self.business, self.user, self.today, Decimal('100.00'))
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('30.00')}],
        )

        summary = build_summary(self.business, self.today, self.today)
        self.assertEqual(summary['sales'], Decimal('30.00'))
        self.assertEqual(summary['opening_amount'], Decimal('100.00'))

    def test_expected_cash_amount_includes_opening_amount(self):
        open_cash_session(self.business, self.user, self.today, Decimal('100.00'))
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('30.00')}],
        )

        expected = expected_amount_for_method(self.business, self.today, 'dinheiro')
        self.assertEqual(expected, Decimal('130.00'))

    def test_expected_pix_amount_does_not_include_opening_amount(self):
        open_cash_session(self.business, self.user, self.today, Decimal('100.00'))
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('30.00'),
            payments=[{'method': 'pix', 'amount': Decimal('30.00')}],
        )

        expected = expected_amount_for_method(self.business, self.today, 'pix')
        self.assertEqual(expected, Decimal('30.00'))


def close_cash_session_for_test(testcase, date):
    """Auxiliar: fecha o caixa conferindo todas as formas com valor zero."""
    for method in ALL_PAYMENT_METHODS:
        register_cash_count(
            business=testcase.business,
            user=testcase.user,
            date=date,
            payment_method=method,
            counted_amount=expected_amount_for_method(testcase.business, date, method),
            reason='Conferência de teste',
        )
    close_cash_session(testcase.business, testcase.user, date)


class CashIndicatorsTests(TestCase):
    """Garante que cada indicador reflita os registros de origem sem duplicidade."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Cliente Teste')
        self.today = timezone.localdate()
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

    def test_sales_receipts_and_fiado_are_not_double_counted(self):
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

        self.assertEqual(sales_total(self.business, self.today, self.today), Decimal('100.00'))
        self.assertEqual(receipts_total(self.business, self.today, self.today), Decimal('60.00'))

        summary = build_summary(self.business, self.today, self.today)
        self.assertEqual(summary['pending_receivables'], Decimal('40.00'))

    def test_receivable_payment_counts_once_as_receipt(self):
        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('40.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('40.00'),
        )
        receivable = sale.receivables.get()
        pay_receivable(receivable, self.user, Decimal('40.00'), 'dinheiro', timezone.now())

        # A receita total do dia deve contar o recebimento uma única vez.
        self.assertEqual(receipts_total(self.business, self.today, self.today), Decimal('40.00'))

    def test_paid_expenses_only_count_actual_payments(self):
        payable = Payable.objects.create(
            business=self.business,
            description='Conta de luz',
            original_amount=Decimal('80.00'),
            due_date=self.today,
            created_by=self.user,
        )
        # Apenas a criação da conta não deve gerar despesa paga.
        self.assertEqual(
            paid_expenses_total(self.business, self.today, self.today), Decimal('0.00')
        )

        pay_payable(payable, self.user, Decimal('80.00'), timezone.now())
        self.assertEqual(
            paid_expenses_total(self.business, self.today, self.today), Decimal('80.00')
        )


class CashCountAdjustmentTests(TestCase):
    """
    Garante que a conferência de caixa físico calcule corretamente o valor
    esperado, a diferença (sobra/falta) e não permita registros sem
    justificativa, preservando o histórico de conferências anteriores.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.today = timezone.localdate()
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

    def test_expected_amount_matches_sales_received_by_method(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
        )

        expected = expected_amount_for_method(self.business, self.today, 'dinheiro')
        self.assertEqual(expected, Decimal('50.00'))

    def test_register_cash_count_requires_reason_only_when_divergent(self):
        """Sem divergência, basta confirmar: a justificativa não é exigida."""
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
        )

        adjustment = register_cash_count(
            business=self.business,
            user=self.user,
            date=self.today,
            payment_method='dinheiro',
            counted_amount=Decimal('50.00'),
            reason='',
        )
        self.assertEqual(adjustment.difference, Decimal('0.00'))

    def test_register_cash_count_requires_reason_when_divergent(self):
        """Com divergência (sobra ou falta), a justificativa é obrigatória."""
        with self.assertRaises(ValidationError):
            register_cash_count(
                business=self.business,
                user=self.user,
                date=self.today,
                payment_method='dinheiro',
                counted_amount=Decimal('50.00'),
                reason='',
            )

    def test_register_cash_count_calculates_shortage_correctly(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('100.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('100.00')}],
        )

        adjustment = register_cash_count(
            business=self.business,
            user=self.user,
            date=self.today,
            payment_method='dinheiro',
            counted_amount=Decimal('90.00'),
            reason='Troco errado dado ao cliente',
        )

        self.assertEqual(adjustment.expected_amount, Decimal('100.00'))
        self.assertEqual(adjustment.counted_amount, Decimal('90.00'))
        self.assertEqual(adjustment.difference, Decimal('-10.00'))

    def test_register_cash_count_calculates_surplus_correctly(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('100.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('100.00')}],
        )

        adjustment = register_cash_count(
            business=self.business,
            user=self.user,
            date=self.today,
            payment_method='dinheiro',
            counted_amount=Decimal('110.00'),
            reason='Cliente deu valor maior sem pedir troco',
        )

        self.assertEqual(adjustment.difference, Decimal('10.00'))

    def test_cash_adjustments_total_uses_only_latest_adjustment_per_day_and_method(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('100.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('100.00')}],
        )

        # Primeira conferência (equivocada): falta de R$ 10.
        register_cash_count(
            business=self.business,
            user=self.user,
            date=self.today,
            payment_method='dinheiro',
            counted_amount=Decimal('90.00'),
            reason='Contagem inicial',
        )

        # Segunda conferência (correção): na verdade estava tudo certo.
        register_cash_count(
            business=self.business,
            user=self.user,
            date=self.today,
            payment_method='dinheiro',
            counted_amount=Decimal('90.00'),
            reason='Recontagem confirma o mesmo valor; segue como falta de R$ 10 real',
        )

        # O total deve considerar apenas a conferência mais recente,
        # não somar a diferença das duas (preservando histórico sem duplicar).
        total = cash_adjustments_total(self.business, self.today, self.today)
        self.assertEqual(total, Decimal('-10.00'))

        # Ambas as conferências permanecem no histórico (nunca são apagadas).
        self.assertEqual(
            CashCountAdjustment.objects.filter(
                business=self.business, date=self.today, payment_method='dinheiro'
            ).count(),
            2,
        )


class DailyClosureTests(TestCase):
    """
    Garante o fluxo de fechamento/reabertura diário: exige conferência
    completa antes de fechar, bloqueia novos lançamentos em dias fechados
    e permite reabertura apenas com justificativa.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.today = timezone.localdate()
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

    def _check_all_methods(self):
        for method in ALL_PAYMENT_METHODS:
            register_cash_count(
                business=self.business,
                user=self.user,
                date=self.today,
                payment_method=method,
                counted_amount=expected_amount_for_method(self.business, self.today, method),
                reason='Conferência de teste',
            )

    def test_cannot_close_day_without_checking_all_methods(self):
        with self.assertRaises(ValidationError):
            close_cash_session(self.business, self.user, self.today)

    def test_close_day_blocks_new_sale(self):
        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)

        self.assertTrue(is_date_closed(self.business, self.today))
        with self.assertRaises(ValidationError):
            create_sale(
                business=self.business,
                user=self.user,
                total_amount=Decimal('10.00'),
                payments=[{'method': 'dinheiro', 'amount': Decimal('10.00')}],
            )

    def test_cannot_close_already_closed_day(self):
        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)

        with self.assertRaises(ValidationError):
            close_cash_session(self.business, self.user, self.today)

    def test_reopen_day_requires_reason(self):
        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)

        with self.assertRaises(ValidationError):
            reopen_cash_session(self.business, self.user, self.today, '')

    def test_reopen_day_allows_new_sale_again(self):
        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)
        reopen_cash_session(self.business, self.user, self.today, 'Correção de lançamento')

        self.assertFalse(is_date_closed(self.business, self.today))
        # Não deve lançar exceção.
        ensure_date_open(self.business, self.today)
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('10.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('10.00')}],
        )

    def test_cannot_reopen_if_another_session_is_open(self):
        """
        Regra de caixa único: se outro dia já estiver aberto, não é
        possível reabrir uma sessão fechada sem fechar a atual primeiro.
        """
        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)

        tomorrow = self.today + timezone.timedelta(days=1)
        open_cash_session(self.business, self.user, tomorrow, Decimal('0.00'))

        with self.assertRaises(ValidationError):
            reopen_cash_session(self.business, self.user, self.today, 'Tentando reabrir')

    def test_cannot_close_day_with_open_comanda(self):
        """
        Uma comanda em aberto representa uma venda em andamento ainda não
        contabilizada; fechar o caixa nesse momento "perderia" essa venda.
        """
        self._check_all_methods()
        open_comanda(self.business, self.user, identifier='Mesa 1')

        with self.assertRaises(ValidationError):
            close_cash_session(self.business, self.user, self.today)


class DashboardComandasTests(TestCase):
    """
    Garante que a aba Caixa exiba as comandas do dia e permita buscá-las
    por identificador/cliente, já que a listagem de comandas foi
    transferida de Vendas para o Caixa.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Baiano')
        open_cash_session(self.business, self.user, timezone.localdate(), Decimal('0.00'))

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_dashboard_lists_comandas_of_the_day(self):
        open_comanda(self.business, self.user, identifier='Mesa 1')
        open_comanda(self.business, self.user, identifier='Mesa 2', customer=self.customer)

        response = self.client.get(reverse('cash:dashboard'))
        comandas = list(response.context['comandas'])

        self.assertEqual(len(comandas), 2)

    def test_dashboard_search_filters_comandas_by_identifier(self):
        open_comanda(self.business, self.user, identifier='Mesa 1')
        open_comanda(self.business, self.user, identifier='Mesa 2', customer=self.customer)

        response = self.client.get(reverse('cash:dashboard'), {'q': 'Mesa 1'})
        comandas = list(response.context['comandas'])

        self.assertEqual(len(comandas), 1)
        self.assertEqual(comandas[0].identifier, 'Mesa 1')

    def test_dashboard_search_filters_comandas_by_customer_name(self):
        open_comanda(self.business, self.user, identifier='Mesa 1')
        open_comanda(self.business, self.user, identifier='Mesa 2', customer=self.customer)

        response = self.client.get(reverse('cash:dashboard'), {'q': 'Baiano'})
        comandas = list(response.context['comandas'])

        self.assertEqual(len(comandas), 1)
        self.assertEqual(comandas[0].identifier, 'Mesa 2')


class DashboardOpenSessionTests(TestCase):
    """
    Garante que o dashboard exiba a tela de abertura de caixa quando não
    houver sessão aberta para a data, e que a abertura funcione via view.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_dashboard_shows_open_form_when_closed(self):
        response = self.client.get(reverse('cash:dashboard'))
        self.assertTrue(response.context['is_closed'])
        self.assertIsNotNone(response.context['open_form'])

    def test_open_session_view_creates_session(self):
        today = timezone.localdate()
        response = self.client.post(
            reverse('cash:open_session'),
            data={'date': today, 'opening_amount': '150.00'},
        )
        self.assertEqual(response.status_code, 302)

        session = CashSession.objects.get(business=self.business, date=today)
        self.assertEqual(session.opening_amount, Decimal('150.00'))
        self.assertTrue(session.is_open)


class OpenCashSessionIndicatorTests(TestCase):
    """
    Garante que o sistema indique claramente em qual dia o caixa está
    aberto, tanto no menu global (context processor) quanto no
    dashboard quando o usuário estiver visualizando outra data fechada
    (ver AGENTS.md seção 13 e necessidade de UX para localizar o caixa
    aberto sem precisar navegar dia a dia).
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.today = timezone.localdate()

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_context_processor_exposes_none_when_no_session_open(self):
        response = self.client.get(reverse('cash:dashboard'))
        self.assertIsNone(response.context['open_cash_session'])

    def test_context_processor_exposes_open_session(self):
        session = open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

        response = self.client.get(reverse('cash:dashboard'))
        self.assertEqual(response.context['open_cash_session'], session)

    def test_dashboard_warns_about_other_open_day_when_viewing_closed_date(self):
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

        other_date = self.today + timezone.timedelta(days=2)
        response = self.client.get(reverse('cash:dashboard'), {'date': other_date.strftime('%Y-%m-%d')})

        self.assertTrue(response.context['is_closed'])
        self.assertIsNotNone(response.context['other_open_session'])
        self.assertEqual(response.context['other_open_session'].date, self.today)
        self.assertContains(response, 'O caixa está aberto no dia')

    def test_dashboard_does_not_warn_when_viewing_the_open_date_itself(self):
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

        response = self.client.get(reverse('cash:dashboard'), {'date': self.today.strftime('%Y-%m-%d')})
        self.assertFalse(response.context['is_closed'])
        self.assertNotIn('other_open_session', response.context)


class CashCountDetailViewTests(TestCase):
    """
    Garante o novo fluxo de conferência: cada forma de pagamento tem sua
    própria tela de detalhe; sem divergência basta confirmar; com
    divergência a justificativa é obrigatória.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.today = timezone.localdate()
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_detail_view_shows_expected_amount(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
        )

        response = self.client.get(
            reverse('cash:cash_count_detail', args=['dinheiro']),
            {'date': self.today},
        )
        self.assertEqual(response.context['expected_amount'], Decimal('50.00'))

    def test_confirm_without_divergence_does_not_require_reason(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
        )

        response = self.client.post(
            reverse('cash:cash_count_detail', args=['dinheiro']),
            data={
                'date': self.today,
                'payment_method': 'dinheiro',
                'counted_amount': '50.00',
                'reason': '',
            },
        )
        self.assertEqual(response.status_code, 302)

        adjustment = CashCountAdjustment.objects.get(
            business=self.business, date=self.today, payment_method='dinheiro'
        )
        self.assertEqual(adjustment.difference, Decimal('0.00'))

    def test_divergent_submission_without_reason_shows_error(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
        )

        response = self.client.post(
            reverse('cash:cash_count_detail', args=['dinheiro']),
            data={
                'date': self.today,
                'payment_method': 'dinheiro',
                'counted_amount': '40.00',
                'reason': '',
            },
        )
        # Permanece na própria tela (form_invalid), não redireciona.
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CashCountAdjustment.objects.filter(
                business=self.business, date=self.today, payment_method='dinheiro'
            ).exists()
        )

    def test_divergent_submission_with_reason_succeeds(self):
        create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[{'method': 'dinheiro', 'amount': Decimal('50.00')}],
        )

        response = self.client.post(
            reverse('cash:cash_count_detail', args=['dinheiro']),
            data={
                'date': self.today,
                'payment_method': 'dinheiro',
                'counted_amount': '40.00',
                'reason': 'Troco errado',
            },
        )
        self.assertEqual(response.status_code, 302)

        adjustment = CashCountAdjustment.objects.get(
            business=self.business, date=self.today, payment_method='dinheiro'
        )
        self.assertEqual(adjustment.difference, Decimal('-10.00'))


class StaleAdjustmentAfterReopenTests(TestCase):
    """
    Garante que, ao reabrir um caixa já conferido e lançar um novo
    recebimento, a conferência antiga seja tratada como desatualizada
    ("stale"): o caixa não pode ser considerado conferido novamente até
    que o operador confira de novo, e o Faturamento do Planejamento
    (daily_revenue) não deve usar o valor contado obsoleto.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.customer = Customer.objects.create(business=self.business, name='Baiano')
        self.today = timezone.localdate()
        open_cash_session(self.business, self.user, self.today, Decimal('0.00'))

    def _check_all_methods(self):
        for method in ALL_PAYMENT_METHODS:
            register_cash_count(
                business=self.business,
                user=self.user,
                date=self.today,
                payment_method=method,
                counted_amount=expected_amount_for_method(self.business, self.today, method),
                reason='Conferência de teste',
            )

    def test_new_receipt_after_reopen_marks_adjustment_as_stale(self):
        from apps.receivables.services import register_customer_payment
        from apps.sales.services import create_sale

        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('50.00'),
        )

        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)

        reopen_cash_session(self.business, self.user, self.today, 'Recebimento esquecido')
        register_customer_payment(self.customer, self.user, Decimal('50.00'), 'dinheiro', timezone.now())

        items = {item['payment_method']: item for item in latest_adjustments_for_date(self.business, self.today)}
        self.assertTrue(items['dinheiro']['stale'])
        self.assertFalse(items['dinheiro']['checked'])
        self.assertEqual(items['dinheiro']['expected_amount'], Decimal('50.00'))

        # Não é possível fechar o caixa de novo sem reconferir a forma afetada.
        self.assertFalse(all_methods_checked(self.business, self.today))
        with self.assertRaises(ValidationError):
            close_cash_session(self.business, self.user, self.today)

    def test_reconfirming_stale_adjustment_updates_daily_revenue(self):
        from apps.receivables.services import register_customer_payment
        from apps.sales.services import create_sale

        sale = create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('50.00'),
            payments=[],
            customer=self.customer,
            fiado_amount=Decimal('50.00'),
        )

        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)
        self.assertEqual(daily_revenue(self.business, self.today), Decimal('0.00'))

        reopen_cash_session(self.business, self.user, self.today, 'Recebimento esquecido')
        register_customer_payment(self.customer, self.user, Decimal('50.00'), 'dinheiro', timezone.now())

        # Reconfirma a conferência de todas as formas (agora com o novo valor esperado).
        self._check_all_methods()
        close_cash_session(self.business, self.user, self.today)

        self.assertEqual(daily_revenue(self.business, self.today), Decimal('50.00'))
