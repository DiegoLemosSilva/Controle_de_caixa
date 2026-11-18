"""Resumo anual do planejamento, calculado a partir dos registros de origem."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.cash.models import CashCountAdjustment, CashSession
from apps.core.constants import PAYMENT_METHOD_CASH, PAYMENT_METHOD_CHOICES
from apps.payables.models import PayablePayment
from apps.receivables.models import ReceivablePayment
from apps.sales.models import SalePayment

from .models import FinancialPlan

ZERO = Decimal('0.00')
MONTH_NAMES = (
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
)


def _received_by_date_and_method(business, year):
    """Mesmas origens e exclusões de expected_amount_for_method."""
    totals = defaultdict(lambda: ZERO)
    sale_payments = (
        SalePayment.objects.filter(sale__business=business, received_at__date__year=year)
        .exclude(sale__status='cancelled')
        .annotate(day=TruncDate('received_at'))
        .values('day', 'method')
        .annotate(total=Sum('amount'))
    )
    receivable_payments = (
        ReceivablePayment.objects.filter(receivable__business=business, paid_at__date__year=year)
        .exclude(status=ReceivablePayment.STATUS_CANCELLED)
        .annotate(day=TruncDate('paid_at'))
        .values('day', 'method')
        .annotate(total=Sum('amount'))
    )
    for row in sale_payments:
        totals[row['day'], row['method']] += row['total']
    for row in receivable_payments:
        totals[row['day'], row['method']] += row['total']
    return totals


def _revenue_by_date(business, year):
    """Reproduz daily_revenue em lote e indica conferências incompletas."""
    sessions = {
        session.date: session
        for session in CashSession.objects.filter(business=business, date__year=year)
    }
    latest = {}
    adjustments = CashCountAdjustment.objects.filter(
        business=business, date__year=year
    ).order_by('date', 'payment_method', '-created_at', '-pk')
    for adjustment in adjustments:
        latest.setdefault((adjustment.date, adjustment.payment_method), adjustment)

    received = _received_by_date_and_method(business, year)
    actuals = {}
    complete = {}
    for day, session in sessions.items():
        if session.is_open:
            continue
        total = ZERO
        all_checked = True
        for method, _ in PAYMENT_METHOD_CHOICES:
            adjustment = latest.get((day, method))
            expected = received[day, method]
            if method == PAYMENT_METHOD_CASH:
                expected += session.opening_amount
            if adjustment is None or adjustment.expected_amount != expected:
                all_checked = False
                continue
            amount = adjustment.counted_amount
            if method == PAYMENT_METHOD_CASH:
                amount -= session.opening_amount
            total += amount
        actuals[day] = total
        complete[day] = all_checked
    return actuals, complete


def build_annual_summary(business, year, selected_month, today=None):
    """Retorna os 12 meses sem criar registros ou apresentar futuro como definitivo."""
    today = today or timezone.localdate()
    planned = defaultdict(lambda: ZERO)
    for row in (
        FinancialPlan.objects.filter(business=business, date__year=year)
        .values('date', 'indicator')
        .annotate(total=Sum('planned_amount'))
    ):
        planned[row['date'].month, row['indicator']] += row['total']

    expenses = defaultdict(lambda: ZERO)
    payments = (
        PayablePayment.objects.filter(payable__business=business, payable__due_date__year=year)
        .exclude(status=PayablePayment.STATUS_CANCELLED)
        .values('payable__due_date')
        .annotate(total=Sum('amount'))
    )
    for row in payments:
        expenses[row['payable__due_date'].month] += row['total']

    actuals, complete = _revenue_by_date(business, year)
    revenue = defaultdict(lambda: ZERO)
    for day, amount in actuals.items():
        # O resumo mensal existente não inclui faturamento de dias futuros.
        if day <= today:
            revenue[day.month] += amount

    months = []
    for month, name in enumerate(MONTH_NAMES, start=1):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        elapsed_last = min(last, today)
        elapsed_days = max(0, (elapsed_last - first).days + 1)
        closed_days = sum(
            1 for day, is_complete in complete.items()
            if first <= day <= elapsed_last and is_complete
        )
        has_closed_session = any(first <= day <= elapsed_last for day in actuals)
        if first > today:
            status = 'Futuro'
        elif not has_closed_session:
            status = 'Sem fechamento'
        elif last > today or closed_days < elapsed_days:
            status = 'Parcial'
        else:
            status = 'Concluído'

        revenue_planned = planned[month, FinancialPlan.INDICATOR_REVENUE]
        expenses_planned = planned[month, FinancialPlan.INDICATOR_PAID_EXPENSES]
        revenue_actual = revenue[month]
        expenses_actual = expenses[month]
        months.append({
            'month': month,
            'name': name,
            'selected': month == selected_month,
            'status': status,
            'revenue_planned': revenue_planned,
            'revenue_actual': revenue_actual,
            'expenses_planned': expenses_planned,
            'expenses_actual': expenses_actual,
            'net_planned': revenue_planned - expenses_planned,
            'net_actual': revenue_actual - expenses_actual,
        })
    return months


def build_annual_charts(months):
    """Prepara coordenadas SVG sem alterar os valores financeiros."""
    definitions = (
        ('Comparativo de faturamento e gastos', 'Faturamento realizado', 'Gastos realizados', 'revenue_actual', 'expenses_actual'),
        ('Faturamento', 'Planejado', 'Realizado', 'revenue_planned', 'revenue_actual'),
        ('Gastos', 'Planejado', 'Realizado', 'expenses_planned', 'expenses_actual'),
        ('Receita (Faturamento − Gastos)', 'Planejado', 'Realizado', 'net_planned', 'net_actual'),
    )
    charts = []
    for title, label_a, label_b, field_a, field_b in definitions:
        values = []
        for month in months:
            for field in (field_a, field_b):
                if field in ('revenue_actual', 'net_actual') and month['status'] in ('Futuro', 'Sem fechamento'):
                    continue
                values.append(month[field])
        has_nonzero_values = any(value != ZERO for value in values)
        low = min([ZERO] + values)
        high = max([ZERO] + values)
        if low == high:
            high = low + Decimal('1')
        span = high - low

        def coordinate(value):
            return Decimal('20') + (high - value) * Decimal('150') / span

        baseline = coordinate(ZERO)
        rows = []
        for index, month in enumerate(months):
            bars = []
            for series, field in enumerate((field_a, field_b)):
                pending = field in ('revenue_actual', 'net_actual') and month['status'] in ('Futuro', 'Sem fechamento')
                value = None if pending else month[field]
                y = baseline if pending else coordinate(value)
                bars.append({
                    'value': value,
                    'pending': pending,
                    'x': 56 + index * 50 + series * 15,
                    'y': f'{min(y, baseline):.2f}',
                    'height': f'{abs(baseline - y):.2f}',
                    'class_name': 'annual-chart__bar--first' if series == 0 else 'annual-chart__bar--second',
                    'label': label_a if series == 0 else label_b,
                })
            rows.append({
                'name': month['name'],
                'short_name': month['name'][:3],
                'status': month['status'],
                'x': 70 + index * 50,
                'bars': bars,
            })
        charts.append({
            'title': title, 'label_a': label_a, 'label_b': label_b,
            'high': high, 'low': low, 'baseline': f'{baseline:.2f}',
            'has_nonzero_values': has_nonzero_values,
            'rows': rows,
        })
    return charts
