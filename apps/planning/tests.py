from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner

from .models import FinancialPlan
from .services import apply_weekday_values, build_comparison, set_daily_value

User = get_user_model()


class PlanningServiceTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')

    def test_apply_weekday_values_respects_real_calendar(self):
        """Novembro/2026: todas as segundas-feiras (weekday=0) recebem o mesmo valor."""
        apply_weekday_values(
            self.business,
            FinancialPlan.INDICATOR_REVENUE,
            2026,
            11,
            {0: Decimal('500.00')},
        )

        mondays = FinancialPlan.objects.filter(
            business=self.business,
            indicator=FinancialPlan.INDICATOR_REVENUE,
            date__year=2026,
            date__month=11,
        )
        self.assertTrue(mondays.exists())
        for plan in mondays:
            self.assertEqual(plan.date.weekday(), 0)
            self.assertEqual(plan.planned_amount, Decimal('500.00'))

    def test_set_daily_value_overrides_single_date_only(self):
        apply_weekday_values(
            self.business,
            FinancialPlan.INDICATOR_REVENUE,
            2026,
            11,
            {0: Decimal('500.00')},
        )

        mondays = list(
            FinancialPlan.objects.filter(
                business=self.business,
                indicator=FinancialPlan.INDICATOR_REVENUE,
                date__year=2026,
                date__month=11,
            ).order_by('date')
        )
        first_monday = mondays[0]

        set_daily_value(
            self.business, FinancialPlan.INDICATOR_REVENUE, first_monday.date, Decimal('900.00')
        )

        first_monday.refresh_from_db()
        self.assertEqual(first_monday.planned_amount, Decimal('900.00'))

        # As demais segundas permanecem com o valor original.
        for plan in mondays[1:]:
            plan.refresh_from_db()
            self.assertEqual(plan.planned_amount, Decimal('500.00'))

    def test_build_comparison_marks_only_future_days_as_pending(self):
        """
        O dia de hoje deve ser tratado como um dia normal (não pendente),
        exibindo o valor realizado até o momento; apenas dias futuros
        continuam marcados como pendentes.
        """
        today = timezone.localdate()

        comparison = build_comparison(
            self.business, FinancialPlan.INDICATOR_REVENUE, today.year, today.month, {}
        )
        by_date = {entry['date']: entry for entry in comparison}

        self.assertFalse(by_date[today]['is_pending'])
        self.assertIsNotNone(by_date[today]['difference'])

        if today.day > 1:
            yesterday = today.replace(day=today.day - 1)
            self.assertFalse(by_date[yesterday]['is_pending'])

        last_day_of_month = max(by_date.keys())
        if last_day_of_month > today:
            self.assertTrue(by_date[last_day_of_month]['is_pending'])
            self.assertIsNone(by_date[last_day_of_month]['difference'])

    def test_build_comparison_for_expenses_never_marks_pending(self):
        """
        Gastos não depende do fechamento de caixa: dias futuros sem
        pagamento registrado devem aparecer como R$ 0,00 definitivo,
        nunca como "Pendente".
        """
        today = timezone.localdate()

        comparison = build_comparison(
            self.business, FinancialPlan.INDICATOR_PAID_EXPENSES, today.year, today.month, {},
            allow_pending=False,
        )
        by_date = {entry['date']: entry for entry in comparison}

        last_day_of_month = max(by_date.keys())
        if last_day_of_month > today:
            self.assertFalse(by_date[last_day_of_month]['is_pending'])
            self.assertEqual(by_date[last_day_of_month]['actual'], Decimal('0.00'))
            self.assertIsNotNone(by_date[last_day_of_month]['difference'])

    def test_unique_constraint_prevents_duplicate_plan(self):
        from django.db import IntegrityError, transaction

        FinancialPlan.objects.create(
            business=self.business,
            indicator=FinancialPlan.INDICATOR_REVENUE,
            date='2026-11-02',
            planned_amount=Decimal('100.00'),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinancialPlan.objects.create(
                    business=self.business,
                    indicator=FinancialPlan.INDICATOR_REVENUE,
                    date='2026-11-02',
                    planned_amount=Decimal('200.00'),
                )


class DailyRevenueTests(TestCase):
    """
    Garante o cálculo do Faturamento real: soma dos valores conferidos
    por forma de pagamento no fechamento do caixa, subtraindo o valor de
    abertura apenas da parcela em dinheiro. Pendente se o caixa não
    estiver fechado.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        from apps.businesses.models import BusinessOwner
        from apps.cash.services import close_cash_session, open_cash_session, register_cash_count
        from apps.sales.services import create_sale

        User = get_user_model()

        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

        self.open_cash_session = open_cash_session
        self.close_cash_session = close_cash_session
        self.register_cash_count = register_cash_count
        self.create_sale = create_sale

    def test_daily_revenue_is_none_when_session_not_closed(self):
        from django.utils import timezone

        from apps.cash.services import daily_revenue

        today = timezone.localdate()
        self.open_cash_session(self.business, self.user, today, Decimal('50.00'))

        self.assertIsNone(daily_revenue(self.business, today))

    def test_daily_revenue_subtracts_opening_amount_only_from_cash(self):
        from django.utils import timezone

        from apps.cash.services import all_methods_checked, daily_revenue, expected_amount_for_method

        today = timezone.localdate()
        self.open_cash_session(self.business, self.user, today, Decimal('50.00'))

        self.create_sale(
            business=self.business,
            user=self.user,
            total_amount=Decimal('100.00'),
            payments=[
                {'method': 'dinheiro', 'amount': Decimal('60.00')},
                {'method': 'pix', 'amount': Decimal('40.00')},
            ],
        )

        for method in ['dinheiro', 'pix', 'debito', 'credito', 'outro']:
            self.register_cash_count(
                business=self.business,
                user=self.user,
                date=today,
                payment_method=method,
                counted_amount=expected_amount_for_method(self.business, today, method),
                reason='Conferência de teste',
            )

        self.close_cash_session(self.business, self.user, today)

        # Dinheiro conferido = 60 (vendas) + 50 (abertura) = 110; menos a
        # abertura (50) = 60. Pix conferido = 40. Total = 100.
        self.assertEqual(daily_revenue(self.business, today), Decimal('100.00'))


class PlanDashboardViewTests(TestCase):
    """
    Garante que o dashboard exiba os dois indicadores (Faturamento e
    Gastos) lado a lado, com navegação de mês e os dados necessários
    para o modal de edição de dia.
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

        self.client = Client()
        self.client.login(username='operador', password='senha12345')

    def test_dashboard_shows_both_indicators(self):
        today = timezone.localdate()
        response = self.client.get(
            reverse('planning:plan_dashboard'),
            {'year': today.year, 'month': today.month},
        )

        self.assertEqual(response.context['revenue_indicator'], FinancialPlan.INDICATOR_REVENUE)
        self.assertEqual(response.context['expenses_indicator'], FinancialPlan.INDICATOR_PAID_EXPENSES)
        self.assertIn('merged_rows', response.context)
        self.assertIn('revenue_summary', response.context)
        self.assertIn('expenses_summary', response.context)
        self.assertIn('net_summary', response.context)

    def test_net_summary_is_revenue_minus_expenses(self):
        """
        O indicador de Receita deve ser exatamente Faturamento - Gastos,
        tanto no valor planejado quanto no realizado, sem duplicar
        nenhum cálculo já feito para os dois indicadores originais.
        """
        today = timezone.localdate()
        FinancialPlan.objects.create(
            business=self.business,
            indicator=FinancialPlan.INDICATOR_REVENUE,
            date=today,
            planned_amount=Decimal('100.00'),
        )
        FinancialPlan.objects.create(
            business=self.business,
            indicator=FinancialPlan.INDICATOR_PAID_EXPENSES,
            date=today,
            planned_amount=Decimal('30.00'),
        )

        response = self.client.get(
            reverse('planning:plan_dashboard'),
            {'year': today.year, 'month': today.month},
        )

        revenue_summary = response.context['revenue_summary']
        expenses_summary = response.context['expenses_summary']
        net_summary = response.context['net_summary']

        self.assertEqual(
            net_summary['total_planned'],
            revenue_summary['total_planned'] - expenses_summary['total_planned'],
        )
        self.assertEqual(
            net_summary['total_actual'],
            revenue_summary['total_actual'] - expenses_summary['total_actual'],
        )

        # Cada linha da tabela única compartilha a mesma data entre os
        # dois indicadores (Faturamento e Gastos).
        merged_rows = response.context['merged_rows']
        self.assertTrue(merged_rows)
        for row in merged_rows:
            self.assertEqual(row['date'], row['revenue']['date'])
            self.assertEqual(row['date'], row['expenses']['date'])

    def test_expenses_actual_uses_payable_due_date_not_payment_date(self):
        """
        Uma conta prevista para o dia 11 e outra para o dia 18, quando
        marcadas como pagas em outro dia (ex.: dia 12), devem aparecer
        no Realizado de Gastos nas suas respectivas datas previstas,
        não na data em que o pagamento foi efetivamente registrado.
        """
        from apps.payables.models import Payable
        from apps.payables.services import mark_payable_as_paid

        today = timezone.localdate()
        year, month = today.year, today.month

        due_date_11 = today.replace(day=11) if today.day != 11 else today
        due_date_18 = today.replace(day=18) if today.day != 18 else today

        payable_11 = Payable.objects.create(
            business=self.business,
            description='Conta A',
            original_amount=Decimal('50.00'),
            due_date=due_date_11,
            created_by=self.user,
        )
        payable_18 = Payable.objects.create(
            business=self.business,
            description='Conta B',
            original_amount=Decimal('70.00'),
            due_date=due_date_18,
            created_by=self.user,
        )

        # Ambos os pagamentos são registrados "agora" (today), mas
        # devem cair no Realizado nas datas previstas de cada conta.
        mark_payable_as_paid(payable_11, self.user)
        mark_payable_as_paid(payable_18, self.user)

        response = self.client.get(
            reverse('planning:plan_dashboard'), {'year': year, 'month': month}
        )
        merged_rows = {row['date']: row for row in response.context['merged_rows']}

        self.assertEqual(merged_rows[due_date_11]['expenses']['actual'], Decimal('50.00'))
        self.assertEqual(merged_rows[due_date_18]['expenses']['actual'], Decimal('70.00'))

        if today not in (due_date_11, due_date_18):
            self.assertEqual(merged_rows[today]['expenses']['actual'], Decimal('0.00'))

    def test_set_daily_value_via_modal_form(self):
        today = timezone.localdate()
        response = self.client.post(
            reverse('planning:set_daily_value'),
            data={
                'year': today.year,
                'month': today.month,
                'indicator': FinancialPlan.INDICATOR_REVENUE,
                'date': today,
                'amount': '250.00',
            },
        )
        self.assertEqual(response.status_code, 302)

        plan = FinancialPlan.objects.get(
            business=self.business,
            indicator=FinancialPlan.INDICATOR_REVENUE,
            date=today,
        )
        self.assertEqual(plan.planned_amount, Decimal('250.00'))
