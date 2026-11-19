"""
Regras de negócio para séries recorrentes de contas a pagar (fixa,
semanal e parcelada).

Sem dependência de jobs em background (Celery etc., proibido pelo
AGENTS.md): a geração de ocorrências futuras de séries fixas/semanais
é feita sob demanda (quando o usuário acessa a listagem ou aciona a
geração manual), sempre de forma idempotente — nunca duplica uma
ocorrência já existente para a mesma série/data.

Cada ocorrência gerada é um Payable normal e independente; a série é
apenas o "molde" usado para criá-las e para permitir edição em massa
das ocorrências futuras ainda não personalizadas manualmente.
"""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Payable, PayableSeries

# Janela de geração "lazy" para séries sem fim definido (fixa/semanal):
# sempre garante ocorrências geradas até esse horizonte a partir de hoje.
FIXED_GENERATION_MONTHS_AHEAD = 2
WEEKLY_GENERATION_WEEKS_AHEAD = 8


def _last_day_of_month(year, month):
    return calendar.monthrange(year, month)[1]


def _add_months(base_date, months):
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, _last_day_of_month(year, month))
    return date(year, month, day)


@transaction.atomic
def create_series(business, user, kind, description, supplier_name, amount,
                   start_date, day_of_month=None, weekday=None,
                   total_installments=None):
    """
    Cria uma PayableSeries e já gera as ocorrências iniciais:
    - Parcelada: gera todas as parcelas de uma vez.
    - Fixa/Semanal: gera a primeira ocorrência e a janela padrão de
      ocorrências futuras (mesma lógica usada depois pela geração lazy).
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError('O valor de cada ocorrência deve ser maior que zero.')

    series = PayableSeries(
        business=business,
        kind=kind,
        description=description,
        supplier_name=supplier_name,
        amount=amount,
        day_of_month=day_of_month,
        weekday=weekday,
        total_installments=total_installments,
        created_by=user,
    )
    series.full_clean()
    series.save()

    if kind == PayableSeries.KIND_INSTALLMENT:
        _generate_installments(series, user, start_date)
    elif kind == PayableSeries.KIND_FIXED:
        generate_fixed_occurrences(series, user)
    elif kind == PayableSeries.KIND_WEEKLY:
        generate_weekly_occurrences(series, user)

    return series


def _split_installment_amounts(total_amount, total_installments):
    """
    Divide o valor total em N parcelas com Decimal, ajustando a última
    parcela para que a soma seja exatamente igual ao total (nunca usar
    float em valores monetários, conforme AGENTS.md seção 6).
    """
    base = (total_amount / total_installments).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    amounts = [base] * total_installments
    difference = total_amount - (base * total_installments)
    amounts[-1] += difference
    return amounts


def _generate_installments(series, user, start_date):
    amounts = _split_installment_amounts(series.amount, series.total_installments)
    for index, installment_amount in enumerate(amounts, start=1):
        due_date = _add_months(start_date, index - 1)
        Payable.objects.create(
            business=series.business,
            description=f'{series.description} ({index}/{series.total_installments})',
            supplier_name=series.supplier_name,
            original_amount=installment_amount,
            due_date=due_date,
            created_by=user,
            series=series,
            installment_number=index,
        )


def _existing_dates_for_series(series):
    return set(
        series.payables.exclude(status=Payable.STATUS_CANCELLED).values_list(
            'due_date', flat=True
        )
    )


def generate_fixed_occurrences(series, user):
    """
    Garante que existam ocorrências geradas para a série fixa até a
    janela padrão (FIXED_GENERATION_MONTHS_AHEAD meses a partir de
    hoje). Idempotente: nunca cria duplicata para a mesma data.
    """
    if series.kind != PayableSeries.KIND_FIXED or not series.is_active:
        return []

    from django.utils import timezone
    today = timezone.localdate()
    existing_dates = _existing_dates_for_series(series)
    created = []

    month_cursor = today.replace(day=1)
    for _ in range(FIXED_GENERATION_MONTHS_AHEAD + 1):
        year, month = month_cursor.year, month_cursor.month
        day = min(series.day_of_month, _last_day_of_month(year, month))
        due_date = date(year, month, day)

        if due_date >= today and due_date not in existing_dates:
            payable = Payable.objects.create(
                business=series.business,
                description=series.description,
                supplier_name=series.supplier_name,
                original_amount=series.amount,
                due_date=due_date,
                created_by=user,
                series=series,
            )
            created.append(payable)
            existing_dates.add(due_date)

        month_cursor = _add_months(month_cursor, 1)

    return created


def generate_weekly_occurrences(series, user):
    """
    Garante que existam ocorrências geradas para a série semanal até a
    janela padrão (WEEKLY_GENERATION_WEEKS_AHEAD semanas a partir de
    hoje). Idempotente: nunca cria duplicata para a mesma data.
    """
    if series.kind != PayableSeries.KIND_WEEKLY or not series.is_active:
        return []

    from django.utils import timezone
    today = timezone.localdate()
    existing_dates = _existing_dates_for_series(series)
    created = []

    # Próxima data (hoje ou futura) que cai no dia da semana da série.
    days_ahead = (series.weekday - today.weekday()) % 7
    cursor = today + timedelta(days=days_ahead)

    for _ in range(WEEKLY_GENERATION_WEEKS_AHEAD):
        if cursor not in existing_dates:
            payable = Payable.objects.create(
                business=series.business,
                description=series.description,
                supplier_name=series.supplier_name,
                original_amount=series.amount,
                due_date=cursor,
                created_by=user,
                series=series,
            )
            created.append(payable)
            existing_dates.add(cursor)
        cursor += timedelta(days=7)

    return created


def ensure_series_occurrences(business, user):
    """
    Chamada pela listagem de contas a pagar: garante que todas as
    séries fixas/semanais ativas da empresa tenham ocorrências geradas
    dentro da janela padrão. Operação idempotente e rápida (sem
    chamadas externas), segura para rodar a cada carregamento de tela.
    """
    series_qs = PayableSeries.objects.filter(
        business=business, is_active=True,
    ).exclude(kind=PayableSeries.KIND_INSTALLMENT)

    for series in series_qs:
        if series.kind == PayableSeries.KIND_FIXED:
            generate_fixed_occurrences(series, user)
        elif series.kind == PayableSeries.KIND_WEEKLY:
            generate_weekly_occurrences(series, user)


@transaction.atomic
def update_series_and_future_occurrences(series, description, supplier_name, amount):
    """
    Edita o "molde" da série (fixa/semanal) e aplica a mudança a todas
    as ocorrências futuras (due_date >= hoje) que ainda estejam
    pendentes/parcialmente pagas e não tenham sido personalizadas
    manualmente (`detached_from_series=False`).

    Ocorrências já pagas, canceladas ou destacadas manualmente nunca
    são alteradas — preserva o histórico financeiro (AGENTS.md).
    """
    if series.kind == PayableSeries.KIND_INSTALLMENT:
        raise ValidationError(
            'Séries parceladas não podem ter valor ou descrição alterados em massa.'
        )

    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError('O valor de cada ocorrência deve ser maior que zero.')

    from django.utils import timezone
    today = timezone.localdate()

    series.description = description
    series.supplier_name = supplier_name
    series.amount = amount
    series.full_clean()
    series.save(update_fields=['description', 'supplier_name', 'amount', 'updated_at'])

    affected = series.payables.filter(
        due_date__gte=today,
        detached_from_series=False,
    ).exclude(
        status__in=[Payable.STATUS_PAID, Payable.STATUS_CANCELLED]
    )
    count = affected.update(
        description=description,
        supplier_name=supplier_name,
        original_amount=amount,
    )
    return count


@transaction.atomic
def cancel_future_occurrences(series, user=None):
    """
    Cancela todas as ocorrências futuras não pagas da série e pausa a
    geração de novas ocorrências. Ocorrências já pagas são preservadas
    intactas (histórico nunca é apagado).
    """
    from django.utils import timezone
    today = timezone.localdate()

    affected = series.payables.filter(due_date__gte=today).exclude(
        status__in=[Payable.STATUS_PAID, Payable.STATUS_CANCELLED]
    )
    count = affected.update(status=Payable.STATUS_CANCELLED)

    series.is_active = False
    series.save(update_fields=['is_active', 'updated_at'])
    return count


def mark_detached_if_diverges(payable, original_description, original_amount,
                               original_due_date):
    """
    Se uma ocorrência pertence a uma série e os valores editados
    divergem do que estava gravado antes da edição, marca
    `detached_from_series=True` para que futuras edições em massa da
    série nunca sobrescrevam essa personalização manual.
    """
    if payable.series_id is None:
        return False

    diverged = (
        payable.description != original_description
        or payable.original_amount != original_amount
        or payable.due_date != original_due_date
    )
    if diverged and not payable.detached_from_series:
        payable.detached_from_series = True
        payable.save(update_fields=['detached_from_series', 'updated_at'])
        return True
    return False
