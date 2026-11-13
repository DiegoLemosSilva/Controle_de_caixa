"""Cálculos de fiado para a listagem e os avisos de limite."""

from decimal import Decimal

from django.db.models import Sum

from apps.core.constants import PAYMENT_METHOD_FIADO
from apps.receivables.models import Receivable, ReceivablePayment


def credit_balances(business):
    """Retorna saldos por cliente, separando dívidas e comandas abertas.

    Pagamentos de comandas abertas são apenas uma projeção: ainda não são
    recebíveis nem integram os indicadores financeiros.
    """
    from apps.sales.models import Comanda, ComandaPayment

    balances = {}

    def entry(customer_id):
        return balances.setdefault(customer_id, {
            'open_balance': Decimal('0.00'),
            'open_comanda_credit': Decimal('0.00'),
        })

    receivables = Receivable.objects.filter(
        business=business, customer__business=business, status=Receivable.STATUS_OPEN,
    ).values('customer_id').annotate(total=Sum('original_amount'))
    for row in receivables:
        entry(row['customer_id'])['open_balance'] = row['total']

    payments = ReceivablePayment.objects.filter(
        receivable__business=business,
        receivable__customer__business=business,
        receivable__status=Receivable.STATUS_OPEN,
        status=ReceivablePayment.STATUS_ACTIVE,
    ).values('receivable__customer_id').annotate(total=Sum('amount'))
    for row in payments:
        entry(row['receivable__customer_id'])['open_balance'] -= row['total']

    pending = ComandaPayment.objects.filter(
        comanda__business=business, comanda__status=Comanda.STATUS_OPEN,
        customer__business=business, method=PAYMENT_METHOD_FIADO,
    ).values('customer_id').annotate(total=Sum('amount'))
    for row in pending:
        entry(row['customer_id'])['open_comanda_credit'] = row['total']

    return balances


def credit_warning_data(business, customers):
    """Dados para aviso nos formulários, sem modificar registros financeiros."""
    balances = credit_balances(business)
    return {
        str(customer.pk): {
            'limit': str(customer.credit_limit),
            'projected': str(projected_credit(customer, balances)),
        }
        for customer in customers
        if customer.business_id == business.pk and customer.credit_limit is not None
    }


def projected_credit(customer, balances, additional=Decimal('0.00')):
    """Exposição informativa: dívida atual + fiado em comandas abertas."""
    values = balances.get(customer.pk, {})
    return (
        values.get('open_balance', Decimal('0.00'))
        + values.get('open_comanda_credit', Decimal('0.00'))
        + additional
    )
