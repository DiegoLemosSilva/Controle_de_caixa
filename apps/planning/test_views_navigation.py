from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.businesses.models import Business, BusinessOwner

from .models import FinancialPlan


class PlanningNavigationTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa')
        self.other = Business.objects.create(name='Outra empresa')
        self.user = get_user_model().objects.create_user(username='gerente', password='senha')
        BusinessOwner.objects.create(business=self.business, user=self.user)
        self.client.force_login(self.user)
        self.url = reverse('planning:plan_dashboard')

    @patch('apps.planning.views._revenue_actuals_by_date', return_value={})
    def test_only_selected_view_is_rendered(self, _actuals):
        for selected, visible, hidden in (
            ('daily', 'js-edit-day-card', ('weekly-summary-title', 'annual-summary-title')),
            ('weekly', 'weekly-summary-title', ('js-edit-day-card', 'annual-summary-title')),
            ('annual', 'annual-summary-title', ('js-edit-day-card', 'weekly-summary-title')),
        ):
            with self.subTest(selected=selected):
                response = self.client.get(self.url, {'year': 2024, 'month': 2, 'view': selected})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['selected_view'], selected)
                self.assertContains(response, visible)
                for marker in hidden:
                    self.assertNotContains(response, marker)
                self.assertContains(response, 'aria-current="page"')

    @patch('apps.planning.views._revenue_actuals_by_date', return_value={})
    def test_weeks_partition_leap_month_and_match_monthly_plans(self, _actuals):
        for business, day, amount in (
            (self.business, 1, '10.00'),
            (self.business, 5, '20.00'),
            (self.business, 29, '30.00'),
            (self.other, 5, '999.00'),
        ):
            FinancialPlan.objects.create(
                business=business, indicator=FinancialPlan.INDICATOR_REVENUE,
                date=date(2024, 2, day), planned_amount=Decimal(amount),
            )
        response = self.client.get(self.url, {'year': 2024, 'month': 2, 'view': 'weekly'})
        weeks = response.context['weekly_summary']
        self.assertEqual(
            [(week['start'].day, week['end'].day) for week in weeks],
            [(1, 4), (5, 11), (12, 18), (19, 25), (26, 29)],
        )
        self.assertEqual(sum(week['revenue']['total_planned'] for week in weeks), Decimal('60.00'))
        self.assertEqual(
            sum(week['revenue']['total_planned'] for week in weeks),
            response.context['revenue_summary']['total_planned'],
        )
        self.assertTrue(all(week['status'] == 'Pendente' for week in weeks))

    def test_save_returns_to_selected_view(self):
        response = self.client.post(reverse('planning:set_daily_value'), {
            'year': '2024', 'month': '2', 'view': 'weekly',
            'indicator': FinancialPlan.INDICATOR_REVENUE,
            'date': '2024-02-05', 'amount': '10.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('view=weekly', response.url)
