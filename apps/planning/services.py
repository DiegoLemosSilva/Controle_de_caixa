"""
Regras de negócio do planejamento financeiro mensal.

O usuário informa um valor-base por dia da semana; o sistema aplica
esse valor a todas as ocorrências do dia da semana no mês, respeitando
o calendário real (AGENTS.md seção 12).
"""

import calendar
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import FinancialPlan


def _month_dates(year, month):
    """Retorna todas as datas (date) do mês informado."""
    _, last_day = calendar.monthrange(year, month)
    return [date(year, month, day) for day in range(1, last_day + 1)]


@transaction.atomic
def apply_weekday_values(business, indicator, year, month, weekday_values):
    """
    Aplica valores-base por dia da semana a todo o mês.

    `weekday_values` é um dict {0: valor_segunda, ..., 6: valor_domingo},
    seguindo a convenção do Python (Monday=0 ... Sunday=6).

    Datas que já possuem um valor específico definido manualmente não
    são sobrescritas, exceto quando o próprio usuário solicitar a
    reaplicação explícita (chamando esta função novamente).
    """
    created_or_updated = []
    for current_date in _month_dates(year, month):
        weekday = current_date.weekday()
        if weekday not in weekday_values:
            continue

        amount = Decimal(weekday_values[weekday])
        plan, _ = FinancialPlan.objects.update_or_create(
            business=business,
            indicator=indicator,
            date=current_date,
            defaults={'planned_amount': amount},
        )
        created_or_updated.append(plan)

    return created_or_updated


def set_daily_value(business, indicator, target_date, amount):
    """Sobrescreve a previsão de uma data específica, sem alterar as demais."""
    amount = Decimal(amount)
    if amount < 0:
        raise ValidationError('O valor planejado não pode ser negativo.')

    plan, _ = FinancialPlan.objects.update_or_create(
        business=business,
        indicator=indicator,
        date=target_date,
        defaults={'planned_amount': amount},
    )
    return plan


@transaction.atomic
def copy_previous_month(business, indicator, year, month):
    """
    Copia o planejamento do mês anterior para o mês informado.

    O mês anterior permanece intacto; o novo mês pode ser editado de
    forma independente a partir deste ponto.
    """
    if month == 1:
        previous_year, previous_month = year - 1, 12
    else:
        previous_year, previous_month = year, month - 1

    previous_plans = FinancialPlan.objects.filter(
        business=business,
        indicator=indicator,
        date__year=previous_year,
        date__month=previous_month,
    )

    created = []
    for plan in previous_plans:
        try:
            new_date = plan.date.replace(year=year, month=month)
        except ValueError:
            # Dia inexistente no novo mês (ex.: 31 de um mês menor).
            continue

        new_plan, _ = FinancialPlan.objects.update_or_create(
            business=business,
            indicator=indicator,
            date=new_date,
            defaults={'planned_amount': plan.planned_amount},
        )
        created.append(new_plan)

    return created


def build_comparison(business, indicator, year, month, actual_by_date, allow_pending=True):
    """
    Monta a comparação planejado vs. realizado para cada dia do mês.

    `actual_by_date` é um dict {date: Decimal} com os valores já
    calculados a partir das movimentações financeiras reais (nunca
    duplicadas apenas para preencher o planejamento).

    Quando `allow_pending` é True (padrão), dias futuros (posteriores a
    hoje) são marcados como pendentes, evitando apresentar zero como
    resultado definitivo para um dia que ainda nem começou — usado pelo
    Faturamento, cujo valor realizado só existe após o fechamento do
    caixa daquele dia. O dia de hoje é sempre tratado como um dia
    normal, exibindo o valor realizado até o momento.

    Quando `allow_pending` é False, nenhum dia é marcado como pendente:
    a ausência de valor realizado em `actual_by_date` já significa
    zero, de forma definitiva — usado pelos Gastos, cujo valor
    realizado não depende do fechamento de caixa, apenas dos
    pagamentos de contas já registrados (ou não) naquela data.
    """
    today = timezone.localdate()
    plans = {
        plan.date: plan.planned_amount
        for plan in FinancialPlan.objects.filter(
            business=business, indicator=indicator, date__year=year, date__month=month
        )
    }

    comparison = []
    for current_date in _month_dates(year, month):
        planned = plans.get(current_date, Decimal('0.00'))
        is_pending = allow_pending and current_date > today
        actual = actual_by_date.get(current_date, Decimal('0.00'))

        entry = {
            'date': current_date,
            'planned': planned,
            'actual': actual,
            'is_pending': is_pending,
            'difference': None,
            'percentage': None,
        }

        if not is_pending:
            entry['difference'] = actual - planned
            if planned > 0:
                entry['percentage'] = (actual - planned) / planned * Decimal('100')

        comparison.append(entry)

    return comparison
