"""Regras de negócio para pagamento de recebíveis (fiado)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.cash.services import lock_date_open

from .models import Receivable, ReceivablePayment


def register_customer_payment(customer, user, amount, method, paid_at):
    """
    Registra o recebimento de um valor do cliente, distribuindo-o
    automaticamente entre os recebíveis (fiado) em aberto, do mais
    antigo para o mais novo (FIFO) — sem exigir que o operador escolha
    manualmente qual venda está sendo quitada.

    Não permite receber valor superior à soma do saldo devedor de
    todos os recebíveis em aberto do cliente. Cada recebível afetado
    recebe seu próprio ReceivablePayment, preservando o histórico e o
    rastreamento individual de cada dívida (nenhuma venda nova é criada
    e nenhuma receita é contabilizada duas vezes).

    Retorna a lista de ReceivablePayment criados (um por recebível
    afetado, na ordem em que foram quitados/abatidos).
    """
    amount = Decimal(amount)

    if amount <= 0:
        raise ValidationError('O valor do pagamento deve ser maior que zero.')

    with transaction.atomic():
        lock_date_open(customer.business, timezone.localtime(paid_at).date())
        open_receivables = list(
            Receivable.objects.select_for_update().filter(
                customer=customer, status=Receivable.STATUS_OPEN
            ).order_by('created_at', 'pk')
        )
        total_open_balance = sum((r.balance for r in open_receivables), Decimal('0.00'))

        if amount > total_open_balance:
            raise ValidationError(
                'O valor do pagamento não pode ser maior que o saldo total devido pelo cliente.'
            )

        remaining = amount
        payments = []
        for receivable in open_receivables:
            if remaining <= 0:
                break

            portion = min(remaining, receivable.balance)
            if portion <= 0:
                continue

            payment = ReceivablePayment.objects.create(
                receivable=receivable,
                amount=portion,
                method=method,
                paid_at=paid_at,
                received_by=user,
            )
            payments.append(payment)

            if receivable.balance <= 0:
                receivable.status = Receivable.STATUS_PAID
                receivable.save(update_fields=['status', 'updated_at'])

            remaining -= portion

        return payments


def register_payment(receivable, user, amount, method, paid_at):
    """
    Registra o pagamento (parcial ou total) de um recebível em aberto.

    Não permite receber valor superior ao saldo devedor. O pagamento
    de uma dívida antiga não gera uma nova venda nem nova receita:
    apenas reduz o saldo do recebível já existente.
    """
    amount = Decimal(amount)

    if amount <= 0:
        raise ValidationError('O valor do pagamento deve ser maior que zero.')

    with transaction.atomic():
        lock_date_open(receivable.business, timezone.localtime(paid_at).date())
        receivable = Receivable.objects.select_for_update().get(pk=receivable.pk)
        if receivable.status == Receivable.STATUS_CANCELLED:
            raise ValidationError('Não é possível receber um fiado cancelado.')

        if amount > receivable.balance:
            raise ValidationError(
                'O valor do pagamento não pode ser maior que o saldo devido pelo cliente.'
            )

        payment = ReceivablePayment.objects.create(
            receivable=receivable,
            amount=amount,
            method=method,
            paid_at=paid_at,
            received_by=user,
        )

        if receivable.balance <= 0:
            receivable.status = Receivable.STATUS_PAID
            receivable.save(update_fields=['status', 'updated_at'])

        return payment
