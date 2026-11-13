"""
Cálculo de indicadores financeiros do caixa, conferência de caixa físico
e controle de sessões de caixa (abertura/fechamento/reabertura).

Os indicadores são sempre calculados a partir dos registros de origem
(Sale, SalePayment, ReceivablePayment, Payable, PayablePayment), nunca
duplicados, conforme AGENTS.md (seção 11).

Por padrão, uma data SEM sessão de caixa aberta está bloqueada para
lançamentos financeiros (ver ensure_date_open). Só pode existir uma
sessão aberta por empresa a qualquer momento (regra de caixa único).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.businesses.models import Business
from apps.core.constants import PAYMENT_METHOD_CASH, PAYMENT_METHOD_CHOICES

from .models import CashCountAdjustment, CashSession, CashSessionEvent


def _sum(queryset, field='amount'):
    return queryset.aggregate(total=Sum(field))['total'] or Decimal('0.00')


def sales_total(business, start_date, end_date):
    """Valor das vendas finalizadas (não canceladas) no período."""
    from apps.sales.models import Sale

    qs = Sale.objects.filter(
        business=business,
        sold_at__date__gte=start_date,
        sold_at__date__lte=end_date,
    ).exclude(status=Sale.STATUS_CANCELLED)
    return _sum(qs, 'total_amount')


def receipts_total(business, start_date, end_date):
    """
    Valores efetivamente recebidos no período: recebimentos imediatos
    de vendas + pagamentos de recebíveis (fiado de vendas anteriores).
    """
    from apps.receivables.models import ReceivablePayment
    from apps.sales.models import SalePayment

    sale_payments = SalePayment.objects.filter(
        sale__business=business,
        received_at__date__gte=start_date,
        received_at__date__lte=end_date,
    ).exclude(sale__status__exact='cancelled')

    receivable_payments = ReceivablePayment.objects.filter(
        receivable__business=business,
        paid_at__date__gte=start_date,
        paid_at__date__lte=end_date,
    ).exclude(status=ReceivablePayment.STATUS_CANCELLED)

    return _sum(sale_payments) + _sum(receivable_payments)


def paid_expenses_total(business, start_date, end_date):
    """Valor das despesas efetivamente pagas (contas a pagar) no período."""
    from apps.payables.models import PayablePayment

    qs = PayablePayment.objects.filter(
        payable__business=business,
        paid_at__date__gte=start_date,
        paid_at__date__lte=end_date,
    ).exclude(status=PayablePayment.STATUS_CANCELLED)
    return _sum(qs)


def pending_receivables_total(business):
    """Soma do saldo em aberto de todos os clientes (fiado), na data atual."""
    from apps.receivables.models import Receivable

    qs = Receivable.objects.filter(business=business, status=Receivable.STATUS_OPEN)
    total = Decimal('0.00')
    for receivable in qs:
        total += receivable.balance
    return total


def pending_payables_total(business):
    """Soma do saldo em aberto das contas a pagar, na data atual."""
    from apps.payables.models import Payable

    qs = Payable.objects.filter(business=business).exclude(
        status=Payable.STATUS_PAID
    ).exclude(status=Payable.STATUS_CANCELLED)
    total = Decimal('0.00')
    for payable in qs:
        total += payable.balance
    return total


def cash_adjustments_total(business, start_date, end_date):
    """
    Soma das diferenças (sobra/falta) registradas em conferências de caixa
    no período, considerando apenas a conferência mais recente de cada
    combinação empresa/data/forma de pagamento (as anteriores são histórico).
    """
    adjustments = _latest_adjustments_queryset(business, start_date, end_date)
    total = Decimal('0.00')
    for adjustment in adjustments:
        total += adjustment.difference
    return total


def opening_amount_total(business, start_date, end_date):
    """
    Soma dos valores de abertura (dinheiro) das sessões de caixa no
    período. Este valor é um saldo inicial, nunca uma receita: deve ser
    exibido separadamente de Vendas e Recebimentos nos indicadores.
    """
    qs = CashSession.objects.filter(
        business=business, date__gte=start_date, date__lte=end_date
    )
    return _sum(qs, 'opening_amount')


def build_summary(business, start_date, end_date):
    """Monta o resumo de indicadores financeiros do período informado."""
    return {
        'start_date': start_date,
        'end_date': end_date,
        'sales': sales_total(business, start_date, end_date),
        'receipts': receipts_total(business, start_date, end_date),
        'paid_expenses': paid_expenses_total(business, start_date, end_date),
        'pending_receivables': pending_receivables_total(business),
        'pending_payables': pending_payables_total(business),
        'cash_adjustments': cash_adjustments_total(business, start_date, end_date),
        'opening_amount': opening_amount_total(business, start_date, end_date),
    }


# --- Conferência de caixa físico --------------------------------------

def _received_amount_for_method(business, date, payment_method):
    """
    Valor efetivamente recebido naquela forma de pagamento naquele dia:
    recebimentos imediatos de vendas + pagamentos de recebíveis (fiado)
    feitos com essa mesma forma de pagamento.
    """
    from apps.receivables.models import ReceivablePayment
    from apps.sales.models import SalePayment

    sale_payments = SalePayment.objects.filter(
        sale__business=business,
        received_at__date=date,
        method=payment_method,
    ).exclude(sale__status__exact='cancelled')

    receivable_payments = ReceivablePayment.objects.filter(
        receivable__business=business,
        paid_at__date=date,
        method=payment_method,
    ).exclude(status=ReceivablePayment.STATUS_CANCELLED)

    return _sum(sale_payments) + _sum(receivable_payments)


def expected_amount_for_method(business, date, payment_method):
    """
    Valor esperado no caixa físico para uma forma de pagamento em um dia:
    o valor efetivamente recebido naquele método, de acordo com os
    registros de origem do sistema (vendas e recebimentos de fiado).

    Para "Dinheiro", soma-se também o valor de abertura da sessão de
    caixa daquele dia (fundo de caixa físico que iniciou o período),
    pois ele compõe o total que deve estar fisicamente na gaveta.
    """
    received = _received_amount_for_method(business, date, payment_method)

    if payment_method == PAYMENT_METHOD_CASH:
        session = CashSession.objects.filter(business=business, date=date).first()
        if session:
            received += session.opening_amount

    return received


@transaction.atomic
def register_cash_count(business, user, date, payment_method, counted_amount, reason):
    """
    Registra a conferência do caixa físico para uma forma de pagamento
    em um dia específico. O valor esperado é calculado automaticamente
    pelo sistema no momento do registro.

    A justificativa só é obrigatória quando houver divergência entre o
    valor contado e o valor esperado pelo sistema. Quando os valores
    coincidem, o operador apenas confirma a conferência, sem necessidade
    de preencher um motivo.
    """
    lock_date_open(business, date)

    counted_amount = Decimal(counted_amount)
    expected_amount = expected_amount_for_method(business, date, payment_method)
    reason = (reason or '').strip()

    if counted_amount != expected_amount and not reason:
        raise ValidationError(
            'É obrigatório informar a justificativa quando o valor contado '
            'é diferente do valor esperado pelo sistema.'
        )

    return CashCountAdjustment.objects.create(
        business=business,
        date=date,
        payment_method=payment_method,
        expected_amount=expected_amount,
        counted_amount=counted_amount,
        reason=reason,
        created_by=user,
    )


def _latest_adjustments_queryset(business, start_date, end_date):
    """
    Retorna apenas a conferência mais recente de cada combinação
    empresa/data/forma de pagamento dentro do período informado.
    """
    all_adjustments = CashCountAdjustment.objects.filter(
        business=business,
        date__gte=start_date,
        date__lte=end_date,
    ).order_by('date', 'payment_method', '-created_at')

    latest_by_key = {}
    for adjustment in all_adjustments:
        key = (adjustment.date, adjustment.payment_method)
        if key not in latest_by_key:
            latest_by_key[key] = adjustment
    return latest_by_key.values()


def latest_adjustments_for_date(business, date):
    """
    Lista a conferência mais recente de cada forma de pagamento para
    uma data específica, incluindo os métodos ainda não conferidos
    (com expected_amount calculado e counted_amount=None).

    Se novos lançamentos (ex.: um recebimento de fiado) forem feitos
    após uma conferência já registrada — o que só é possível depois de
    uma reabertura de caixa —, o valor esperado pelo sistema muda, mas
    o valor contado fisicamente da conferência antiga continua
    "congelado". Nesse caso, o item é marcado como desatualizado
    (`stale=True`) e tratado como não conferido (`checked=False`),
    forçando uma nova conferência antes que o caixa possa ser fechado
    novamente — evitando que indicadores (como o Faturamento do
    Planejamento) continuem usando um valor contado obsoleto.
    """
    existing = {
        adjustment.payment_method: adjustment
        for adjustment in _latest_adjustments_queryset(business, date, date)
    }

    results = []
    for code, label in PAYMENT_METHOD_CHOICES:
        adjustment = existing.get(code)
        current_expected = expected_amount_for_method(business, date, code)

        if adjustment:
            is_stale = adjustment.expected_amount != current_expected
            if is_stale:
                results.append({
                    'payment_method': code,
                    'label': label,
                    'expected_amount': current_expected,
                    'counted_amount': None,
                    'difference': None,
                    'reason': '',
                    'checked': False,
                    'stale': True,
                    'previous_counted_amount': adjustment.counted_amount,
                })
            else:
                results.append({
                    'payment_method': code,
                    'label': label,
                    'expected_amount': adjustment.expected_amount,
                    'counted_amount': adjustment.counted_amount,
                    'difference': adjustment.difference,
                    'reason': adjustment.reason,
                    'checked': True,
                    'stale': False,
                    'previous_counted_amount': None,
                })
        else:
            results.append({
                'payment_method': code,
                'label': label,
                'expected_amount': current_expected,
                'counted_amount': None,
                'difference': None,
                'reason': '',
                'checked': False,
                'stale': False,
                'previous_counted_amount': None,
            })
    return results


def all_methods_checked(business, date):
    """True se todas as formas de pagamento já têm conferência para o dia."""
    return all(item['checked'] for item in latest_adjustments_for_date(business, date))


def daily_revenue(business, date):
    """
    Faturamento real do dia, usado no Planejamento financeiro.

    Definido como a soma dos valores CONFERIDOS (não os esperados) em
    cada forma de pagamento no fechamento do caixa daquele dia; para
    Dinheiro, subtrai-se o valor de abertura da sessão (fundo de caixa
    físico, que não é receita).

    Só é possível calcular o faturamento real de um dia cujo caixa já
    foi fechado (todas as formas conferidas). Se o caixa não estiver
    fechado, retorna None (o dia deve ser tratado como pendente).
    """
    if not is_date_closed(business, date):
        return None

    session = get_session_for_date(business, date)
    if session is None:
        return None

    total = Decimal('0.00')
    for item in latest_adjustments_for_date(business, date):
        if not item['checked']:
            continue
        amount = item['counted_amount']
        if item['payment_method'] == PAYMENT_METHOD_CASH:
            amount -= session.opening_amount
        total += amount

    return total


# --- Sessões de caixa (abertura, fechamento, reabertura) --------------

def get_open_session(business):
    """Retorna a sessão de caixa atualmente aberta da empresa, se houver."""
    return CashSession.objects.filter(
        business=business, status=CashSession.STATUS_OPEN
    ).first()


def get_session_for_date(business, date):
    """Retorna a sessão de caixa (aberta ou fechada) de uma data específica."""
    return CashSession.objects.filter(business=business, date=date).first()


def is_date_closed(business, date):
    """
    Retorna True se a data NÃO tiver uma sessão de caixa aberta — ou
    seja, se os lançamentos financeiros estiverem bloqueados para ela.
    Por padrão (sem nenhuma sessão criada), a data é considerada fechada.
    """
    session = get_session_for_date(business, date)
    if session is None:
        return True
    return not session.is_open


def ensure_date_open(business, date):
    """Lança ValidationError se a data não tiver uma sessão de caixa aberta."""
    if is_date_closed(business, date):
        raise ValidationError(
            f'O caixa do dia {date:%d/%m/%Y} está fechado. Abra o caixa para '
            'lançar ou alterar movimentações nesta data.'
        )


def lock_date_open(business, date):
    """Bloqueia a empresa e valida o caixa dentro de uma transação."""
    Business.objects.select_for_update().get(pk=business.pk)
    ensure_date_open(business, date)


@transaction.atomic
def open_cash_session(business, user, date, opening_amount):
    """
    Abre uma nova sessão de caixa para a data informada, com o valor
    inicial em dinheiro. Rejeita a abertura se já existir qualquer
    sessão aberta para a empresa (regra de caixa único) ou se a data
    já tiver uma sessão criada anteriormente.
    """
    Business.objects.select_for_update().get(pk=business.pk)
    opening_amount = Decimal(opening_amount)

    if opening_amount < 0:
        raise ValidationError('O valor de abertura não pode ser negativo.')

    existing_open = get_open_session(business)
    if existing_open is not None:
        raise ValidationError(
            f'Já existe um caixa aberto para o dia {existing_open.date:%d/%m/%Y}. '
            'Feche-o antes de abrir um novo caixa.'
        )

    if CashSession.objects.filter(business=business, date=date).exists():
        raise ValidationError(
            f'O dia {date:%d/%m/%Y} já teve um caixa aberto anteriormente. '
            'Utilize a reabertura, se necessário.'
        )

    session = CashSession.objects.create(
        business=business,
        date=date,
        status=CashSession.STATUS_OPEN,
        opening_amount=opening_amount,
        opened_at=timezone.now(),
        opened_by=user,
    )

    CashSessionEvent.objects.create(
        session=session,
        event_type=CashSessionEvent.EVENT_OPENED,
        performed_by=user,
    )
    return session


def open_comandas_blocking_closure(business, date):
    """
    Comandas abertas (não finalizadas/canceladas) até a data informada,
    que impedem o fechamento do caixa por representarem vendas em
    andamento ainda não contabilizadas.
    """
    from apps.sales.models import Comanda

    return Comanda.objects.filter(
        business=business,
        status=Comanda.STATUS_OPEN,
        opened_at__date__lte=date,
    ).order_by('opened_at')


@transaction.atomic
def close_cash_session(business, user, date):
    """
    Fecha a sessão de caixa de uma data, bloqueando novos lançamentos.

    Exige que todas as formas de pagamento já tenham sido conferidas
    fisicamente e que não existam comandas abertas até aquela data
    (uma comanda aberta representa uma venda em andamento, ainda não
    contabilizada, e não deve ser "perdida" por um fechamento de caixa).
    """
    Business.objects.select_for_update().get(pk=business.pk)
    session = get_session_for_date(business, date)
    if session is None or not session.is_open:
        raise ValidationError(f'Não há um caixa aberto para o dia {date:%d/%m/%Y}.')

    if open_comandas_blocking_closure(business, date).exists():
        raise ValidationError(
            'Existem comandas abertas que ainda não foram finalizadas ou '
            'canceladas. Finalize ou cancele todas as comandas antes de '
            'fechar o caixa do dia.'
        )

    if not all_methods_checked(business, date):
        raise ValidationError(
            'Confira todas as formas de pagamento antes de fechar o caixa do dia.'
        )

    session.status = CashSession.STATUS_CLOSED
    session.closed_at = timezone.now()
    session.closed_by = user
    session.save(update_fields=['status', 'closed_at', 'closed_by', 'updated_at'])

    CashSessionEvent.objects.create(
        session=session,
        event_type=CashSessionEvent.EVENT_CLOSED,
        performed_by=user,
    )
    return session


@transaction.atomic
def reopen_cash_session(business, user, date, reason):
    """
    Reabre uma sessão de caixa fechada, exigindo justificativa.

    Rejeita a reabertura se já existir outra sessão aberta no momento
    (regra de caixa único): é preciso fechar a sessão atual primeiro.
    """
    if not reason or not reason.strip():
        raise ValidationError('É obrigatório informar o motivo da reabertura.')

    Business.objects.select_for_update().get(pk=business.pk)
    session = get_session_for_date(business, date)
    if session is None or session.is_open:
        raise ValidationError(f'O dia {date:%d/%m/%Y} não está fechado.')

    existing_open = get_open_session(business)
    if existing_open is not None:
        raise ValidationError(
            f'Já existe um caixa aberto para o dia {existing_open.date:%d/%m/%Y}. '
            'Feche-o antes de reabrir outro caixa.'
        )

    session.status = CashSession.STATUS_OPEN
    session.reopened_at = timezone.now()
    session.reopened_by = user
    session.reopen_reason = reason
    session.save(update_fields=[
        'status', 'reopened_at', 'reopened_by', 'reopen_reason', 'updated_at'
    ])

    CashSessionEvent.objects.create(
        session=session,
        event_type=CashSessionEvent.EVENT_REOPENED,
        performed_by=user,
        reason=reason,
    )
    return session
