import json
import re
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.businesses.models import Business, BusinessOwner
from apps.cash.models import CashCountAdjustment
from apps.cash.services import (
    close_cash_session,
    daily_revenue,
    expected_amount_for_method,
    open_cash_session,
    register_cash_count,
    reopen_cash_session,
)
from apps.payables.models import Payable, PayablePayment
from apps.sales.services import create_sale

from .annual import build_annual_charts, build_annual_summary
from .models import FinancialPlan


class AnnualSummaryTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa A')
        self.other = Business.objects.create(name='Empresa B')
        self.user = get_user_model().objects.create_user(username='gerente', password='senha123')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.today = timezone.localdate()

    def _plan(self, business, indicator, day, amount):
        FinancialPlan.objects.create(
            business=business, indicator=indicator, date=day, planned_amount=Decimal(amount)
        )

    def _payment(self, business, due_date, amount, status=PayablePayment.STATUS_ACTIVE):
        payable = Payable.objects.create(
            business=business, description='Conta', original_amount=Decimal(amount),
            due_date=due_date, created_by=self.user,
        )
        return PayablePayment.objects.create(
            payable=payable, amount=Decimal(amount), paid_at=timezone.now(),
            paid_by=self.user, status=status,
        )

    def test_twelve_months_plans_and_payments_are_isolated(self):
        self._plan(self.business, FinancialPlan.INDICATOR_REVENUE, date(2024, 2, 29), '100.00')
        self._plan(self.business, FinancialPlan.INDICATOR_PAID_EXPENSES, date(2024, 2, 29), '30.00')
        self._plan(self.other, FinancialPlan.INDICATOR_REVENUE, date(2024, 2, 29), '999.00')
        self._payment(self.business, date(2024, 2, 29), '20.00')
        self._payment(self.business, date(2024, 2, 29), '10.00', PayablePayment.STATUS_CANCELLED)
        self._payment(self.other, date(2024, 2, 29), '999.00')

        with self.assertNumQueries(6):
            months = build_annual_summary(self.business, 2024, 2, today=date(2024, 2, 15))
        self.assertEqual(len(months), 12)
        february = months[1]
        self.assertTrue(february['selected'])
        self.assertEqual(february['revenue_planned'], Decimal('100.00'))
        self.assertEqual(february['expenses_planned'], Decimal('30.00'))
        self.assertEqual(february['expenses_actual'], Decimal('20.00'))
        self.assertEqual(february['net_planned'], Decimal('70.00'))
        self.assertEqual(february['status'], 'Sem fechamento')
        self.assertEqual(months[2]['status'], 'Futuro')

    def test_revenue_matches_daily_calculation_and_reopening_removes_it(self):
        open_cash_session(self.business, self.user, self.today, Decimal('50.00'))
        create_sale(
            business=self.business, user=self.user, total_amount=Decimal('100.00'),
            payments=[
                {'method': 'dinheiro', 'amount': Decimal('60.00')},
                {'method': 'pix', 'amount': Decimal('40.00')},
            ],
        )
        for method in ['dinheiro', 'pix', 'debito', 'credito', 'outro']:
            register_cash_count(
                self.business, self.user, self.today, method,
                expected_amount_for_method(self.business, self.today, method), '',
            )
        close_cash_session(self.business, self.user, self.today)

        annual = build_annual_summary(self.business, self.today.year, self.today.month)
        month = annual[self.today.month - 1]
        self.assertEqual(month['revenue_actual'], daily_revenue(self.business, self.today))
        self.assertEqual(month['revenue_actual'], Decimal('100.00'))
        self.assertIn(month['status'], ('Parcial', 'Concluído'))

        # Simula uma conferência histórica que deixou de corresponder ao esperado.
        CashCountAdjustment.objects.filter(
            business=self.business, date=self.today, payment_method='pix'
        ).update(expected_amount=Decimal('999.00'))
        month = build_annual_summary(self.business, self.today.year, self.today.month)[self.today.month - 1]
        self.assertEqual(month['revenue_actual'], daily_revenue(self.business, self.today))
        self.assertEqual(month['revenue_actual'], Decimal('60.00'))
        self.assertEqual(month['status'], 'Parcial')

        reopen_cash_session(self.business, self.user, self.today)
        month = build_annual_summary(self.business, self.today.year, self.today.month)[self.today.month - 1]
        self.assertEqual(month['revenue_actual'], Decimal('0.00'))
        self.assertEqual(month['status'], 'Sem fechamento')

    def test_dashboard_shows_annual_summary_when_selected(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('planning:plan_dashboard'),
            {'year': self.today.year, 'month': self.today.month, 'view': 'annual'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visão anual')
        self.assertContains(response, 'annual-chart__graphic', count=4)
        self.assertContains(response, 'data-orientation="vertical"', count=1)
        self.assertContains(response, 'data-orientation="horizontal"', count=3)
        self.assertContains(response, 'class="annual-chart__accessible-table"', count=4)
        self.assertNotContains(response, 'Caixa parcial')
        self.assertNotContains(response, 'Sem fechamento ou mês futuro')
        self.assertNotContains(response, 'annual-chart__status-mark')
        self.assertNotContains(response, 'annual-chart__table-scroll')
        self.assertContains(response, 'css/planning/annual.css')
        self.assertContains(response, 'js/vendor/echarts/echarts.min.js')
        self.assertContains(response, 'js/planning/annual_charts.js')
        match = re.search(
            r'<script id="annual-charts-data" type="application/json">(.*?)</script>',
            response.content.decode(), re.DOTALL,
        )
        self.assertIsNotNone(match)
        serialized = json.loads(match.group(1))
        self.assertEqual(len(serialized), 4)
        self.assertTrue(serialized[0]['rows'][self.today.month - 1]['bars'][0]['pending'])
        self.assertIsNone(serialized[0]['rows'][self.today.month - 1]['bars'][0]['value'])
        charts = response.context['annual_charts']
        self.assertEqual(charts[0]['title'], 'Comparativo de faturamento e gastos')
        self.assertEqual(len(charts[0]['rows']), 12)
        current = response.context['annual_summary'][self.today.month - 1]
        self.assertEqual(current['revenue_planned'], response.context['revenue_summary']['total_planned'])
        self.assertEqual(current['expenses_actual'], response.context['expenses_summary']['total_actual'])

    def test_other_views_do_not_load_chart_library(self):
        self.client.force_login(self.user)
        for view in ('daily', 'weekly'):
            with self.subTest(view=view):
                response = self.client.get(reverse('planning:plan_dashboard'), {'view': view})
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'js/vendor/echarts/echarts.min.js')
                self.assertNotContains(response, 'js/planning/annual_charts.js')

    def test_charts_handle_pending_partial_and_negative_values(self):
        months = [{
            'name': 'Janeiro',
            'status': 'Parcial',
            'revenue_actual': Decimal('60.00'),
            'expenses_actual': Decimal('80.00'),
            'revenue_planned': Decimal('100.00'),
            'expenses_planned': Decimal('40.00'),
            'net_actual': Decimal('-20.00'),
            'net_planned': Decimal('60.00'),
        }, {
            'name': 'Fevereiro',
            'status': 'Futuro',
            'revenue_actual': Decimal('0.00'),
            'expenses_actual': Decimal('15.00'),
            'revenue_planned': Decimal('0.00'),
            'expenses_planned': Decimal('0.00'),
            'net_actual': Decimal('-15.00'),
            'net_planned': Decimal('0.00'),
        }]
        comparison, _, _, net = build_annual_charts(months)
        self.assertEqual(comparison['rows'][0]['bars'][0]['value'], Decimal('60.00'))
        self.assertTrue(comparison['rows'][1]['bars'][0]['pending'])
        self.assertEqual(comparison['rows'][1]['bars'][1]['value'], Decimal('15.00'))
        self.assertEqual(net['rows'][0]['bars'][1]['value'], Decimal('-20.00'))
        self.assertEqual(net['rows'][0]['bars'][1]['y'], net['baseline'])
        self.assertGreater(Decimal(net['rows'][0]['bars'][1]['height']), 0)
        self.assertTrue(net['rows'][1]['bars'][1]['pending'])
