from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.businesses.mixins import BusinessRequiredMixin
from apps.cash.services import daily_revenue

from .annual import build_annual_charts, build_annual_summary
from .forms import DailyValueForm, WeekdayValuesForm
from .models import FinancialPlan
from .services import apply_weekday_values, build_comparison, copy_previous_month, set_daily_value

MONTH_NAMES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


def _revenue_actuals_by_date(business, year, month):
    """Faturamento real de cada dia do mês (None = caixa ainda não fechado)."""
    import calendar

    _, last_day = calendar.monthrange(year, month)
    actuals = {}
    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        value = daily_revenue(business, current_date)
        if value is not None:
            actuals[current_date] = value
    return actuals


def _expenses_actuals_by_date(business, year, month):
    """
    Gastos (despesas pagas) de cada dia do mês, somados pela DATA
    PREVISTA DE PAGAMENTO da conta (Payable.due_date), e não pela data
    em que o pagamento foi efetivamente registrado no sistema.

    Isso é intencional e específico do Planejamento: uma conta prevista
    para o dia 18, quando marcada como paga em qualquer outro dia,
    deve aparecer como Realizado no dia 18 (sua data prevista), não no
    dia em que o usuário clicou em "Marcar como paga". Quando mais de
    um pagamento (de uma mesma conta ou de contas diferentes) cai na
    mesma data prevista, os valores se somam.

    Esse cálculo é isolado da função paid_expenses_total (usada em
    outras partes do sistema, como indicadores de fluxo de caixa real),
    que continua baseada na data efetiva do pagamento.
    """
    import calendar
    from decimal import Decimal

    from django.db.models import Sum

    from apps.payables.models import PayablePayment

    _, last_day = calendar.monthrange(year, month)
    actuals = {date(year, month, day): Decimal('0.00') for day in range(1, last_day + 1)}

    payments_by_due_date = (
        PayablePayment.objects.filter(
            payable__business=business,
            payable__due_date__year=year,
            payable__due_date__month=month,
        )
        .exclude(status=PayablePayment.STATUS_CANCELLED)
        .values('payable__due_date')
        .annotate(total=Sum('amount'))
    )

    for row in payments_by_due_date:
        actuals[row['payable__due_date']] = row['total']

    return actuals


class PlanDashboardView(BusinessRequiredMixin, TemplateView):
    """
    Painel de planejamento financeiro: Faturamento e Gastos exibidos em
    colunas lado a lado, sob a mesma navegação de mês, cada um com seu
    próprio resumo e grade de dias.
    """

    template_name = 'planning/plan_dashboard.html'

    def get_year_month(self):
        today = timezone.localdate()
        try:
            year = int(self.request.GET.get('year', today.year))
            month = int(self.request.GET.get('month', today.month))
        except (TypeError, ValueError):
            year, month = today.year, today.month

        month_index = year * 12 + (month - 1)
        year, month = divmod(month_index, 12)
        month += 1
        return year, month

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self.get_year_month()
        selected_view = self.request.GET.get('view', 'daily')
        if selected_view not in ('daily', 'weekly', 'annual'):
            selected_view = 'daily'

        revenue_actuals = _revenue_actuals_by_date(self.business, year, month)
        expenses_actuals = _expenses_actuals_by_date(self.business, year, month)

        revenue_comparison = build_comparison(
            self.business, FinancialPlan.INDICATOR_REVENUE, year, month, revenue_actuals
        )
        expenses_comparison = build_comparison(
            self.business, FinancialPlan.INDICATOR_PAID_EXPENSES, year, month, expenses_actuals,
            allow_pending=False,
        )

        revenue_summary = _summarize(revenue_comparison)
        expenses_summary = _summarize(expenses_comparison)
        net_summary = _net_summary(revenue_summary, expenses_summary)

        previous_index = year * 12 + (month - 1) - 1
        previous_year, previous_month = divmod(previous_index, 12)
        previous_month += 1
        next_index = year * 12 + (month - 1) + 1
        next_year, next_month = divmod(next_index, 12)
        next_month += 1

        merged_rows = [
            {'date': revenue_entry['date'], 'revenue': revenue_entry, 'expenses': expenses_entry}
            for revenue_entry, expenses_entry in zip(revenue_comparison, expenses_comparison)
        ]

        annual_summary = (
            build_annual_summary(self.business, year, month)
            if selected_view == 'annual' else []
        )

        context.update({
            'year': year,
            'month': month,
            'month_label': MONTH_NAMES_PT[month],
            'previous_year': previous_year,
            'previous_month': previous_month,
            'next_year': next_year,
            'next_month': next_month,
            'merged_rows': merged_rows,
            'revenue_summary': revenue_summary,
            'expenses_summary': expenses_summary,
            'net_summary': net_summary,
            'selected_view': selected_view,
            'annual_summary': annual_summary,
            'annual_charts': build_annual_charts(annual_summary) if annual_summary else [],
            'weekly_summary': _weekly_summary(merged_rows, revenue_actuals) if selected_view == 'weekly' else [],
            'weekday_form': WeekdayValuesForm(),
            'daily_form': DailyValueForm(),
            'revenue_indicator': FinancialPlan.INDICATOR_REVENUE,
            'expenses_indicator': FinancialPlan.INDICATOR_PAID_EXPENSES,
        })
        return context


def _weekly_summary(rows, revenue_actuals):
    """Semanas de segunda a domingo, limitadas ao mês exibido."""
    weeks = []
    current = []
    today = timezone.localdate()

    def append_week(entries):
        revenue = _summarize([entry['revenue'] for entry in entries])
        expenses = _summarize([entry['expenses'] for entry in entries])
        available = sum(
            entry['date'] <= today and entry['date'] in revenue_actuals
            for entry in entries
        )
        if available == 0:
            status = 'Pendente'
        elif available < len(entries) or entries[-1]['date'] > today:
            status = 'Parcial'
        else:
            status = 'Concluída'
        weeks.append({
            'start': entries[0]['date'],
            'end': entries[-1]['date'],
            'status': status,
            'revenue': revenue,
            'expenses': expenses,
            'net': _net_summary(revenue, expenses),
        })

    for row in rows:
        if current and row['date'].weekday() == 0:
            append_week(current)
            current = []
        current.append(row)
    if current:
        append_week(current)
    return weeks


def _summarize(comparison):
    """Soma o planejado e o realizado (dias não pendentes) de uma lista de comparação."""
    from decimal import Decimal

    total_planned = sum((entry['planned'] for entry in comparison), Decimal('0.00'))
    total_actual = sum(
        (entry['actual'] for entry in comparison if not entry['is_pending']),
        Decimal('0.00'),
    )
    difference = total_actual - total_planned
    percentage = None
    if total_planned > 0:
        percentage = difference / total_planned * Decimal('100')

    return {
        'total_planned': total_planned,
        'total_actual': total_actual,
        'difference': difference,
        'percentage': percentage,
    }


def _net_summary(revenue_summary, expenses_summary):
    """
    Calcula o indicador de Receita (lucro líquido do período):
    Faturamento - Gastos, tanto planejado quanto realizado.

    Não é um indicador persistido separadamente no FinancialPlan: é
    derivado diretamente dos resumos de Faturamento e Gastos já
    calculados, evitando qualquer duplicação de cálculo ou de dados.
    """
    from decimal import Decimal

    total_planned = revenue_summary['total_planned'] - expenses_summary['total_planned']
    total_actual = revenue_summary['total_actual'] - expenses_summary['total_actual']
    difference = total_actual - total_planned
    percentage = None
    if total_planned != 0:
        percentage = difference / abs(total_planned) * Decimal('100')

    return {
        'total_planned': total_planned,
        'total_actual': total_actual,
        'difference': difference,
        'percentage': percentage,
    }


def _planning_redirect(request, year, month):
    selected_view = request.POST.get('view', 'daily')
    if selected_view not in ('daily', 'weekly', 'annual'):
        selected_view = 'daily'
    return redirect(
        f"{reverse('planning:plan_dashboard')}?year={year}&month={month}&view={selected_view}"
    )


class ApplyWeekdayValuesView(BusinessRequiredMixin, View):
    def post(self, request):
        year = int(request.POST.get('year'))
        month = int(request.POST.get('month'))
        indicator = request.POST.get('indicator')

        form = WeekdayValuesForm(request.POST)
        if form.is_valid():
            apply_weekday_values(
                self.business, indicator, year, month, form.get_weekday_values()
            )
            messages.success(request, 'Planejamento aplicado por dia da semana com sucesso.')
        else:
            messages.error(request, 'Dados inválidos para aplicar o planejamento.')

        return _planning_redirect(request, year, month)


class CopyPreviousMonthView(BusinessRequiredMixin, View):
    def post(self, request):
        year = int(request.POST.get('year'))
        month = int(request.POST.get('month'))
        indicator = request.POST.get('indicator')

        copy_previous_month(self.business, indicator, year, month)
        messages.success(request, 'Planejamento do mês anterior copiado com sucesso.')

        return _planning_redirect(request, year, month)


class SetDailyValueView(BusinessRequiredMixin, View):
    def post(self, request):
        year = int(request.POST.get('year'))
        month = int(request.POST.get('month'))
        indicator = request.POST.get('indicator')

        form = DailyValueForm(request.POST)
        if form.is_valid():
            try:
                set_daily_value(
                    self.business,
                    indicator,
                    form.cleaned_data['date'],
                    form.cleaned_data['amount'],
                )
                messages.success(request, 'Previsão do dia atualizada com sucesso.')
            except ValidationError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, 'Dados inválidos para atualizar o dia.')

        return _planning_redirect(request, year, month)
