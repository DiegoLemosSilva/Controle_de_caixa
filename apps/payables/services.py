"""
Regras de negócio para pagamento de contas a pagar.

Contas a pagar não dependem da sessão de caixa diária (abertura/
fechamento de caixa): são compromissos financeiros próprios, sem
relação com o fluxo de vendas e recebimentos do dia, portanto seus
pagamentos não são bloqueados por um caixa fechado em determinada data.

O Planejamento financeiro (meta de Gastos) é alimentado exclusivamente
pela tela de Planejamento, nunca automaticamente a partir do pagamento
de uma conta. O valor "Realizado" do indicador Gastos no Planejamento
já é calculado a partir dos registros de PayablePayment pela data em
que o pagamento foi efetivamente registrado (ver apps.cash.services.
paid_expenses_total), sem nenhuma necessidade de duplicar esse cálculo
aqui.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Payable, PayablePayment


def register_payment(payable, user, amount, paid_at):
    """
    Registra um pagamento (parcial ou integral) de uma conta a pagar.

    Rejeita pagamentos que excedam o saldo devido e atualiza a situação
    da conta de forma consistente, preservando o histórico.
    """
    amount = Decimal(amount)

    if amount <= 0:
        raise ValidationError('O valor do pagamento deve ser maior que zero.')

    with transaction.atomic():
        payable = Payable.objects.select_for_update().get(pk=payable.pk)
        if payable.status == Payable.STATUS_CANCELLED:
            raise ValidationError('Não é possível pagar uma conta cancelada.')

        if amount > payable.balance:
            raise ValidationError(
                'O valor do pagamento não pode ser maior que o saldo devido.'
            )

        payment = PayablePayment.objects.create(
            payable=payable,
            amount=amount,
            paid_at=paid_at,
            paid_by=user,
        )

        remaining = payable.balance
        if remaining <= 0:
            payable.status = Payable.STATUS_PAID
        else:
            payable.status = Payable.STATUS_PARTIALLY_PAID
        payable.save(update_fields=['status', 'updated_at'])

        return payment


def mark_payable_as_paid(payable, user):
    """
    Marca a conta a pagar como paga, registrando automaticamente um
    único pagamento pelo valor total do saldo devido. Usado pela ação
    rápida de "Marcar como paga" na listagem, onde o pagamento é
    sempre integral e não há forma de pagamento a informar.
    """
    with transaction.atomic():
        payable = Payable.objects.select_for_update().get(pk=payable.pk)
        if payable.status == Payable.STATUS_CANCELLED:
            raise ValidationError('Não é possível pagar uma conta cancelada.')
        if payable.status == Payable.STATUS_PAID:
            raise ValidationError('Esta conta já está paga.')

        balance = payable.balance
        if balance <= 0:
            raise ValidationError('Esta conta não possui saldo devido.')

        return register_payment(payable, user, balance, timezone.now())


def reopen_payable(payable):
    """
    Reabre uma conta a pagar paga (ou parcialmente paga), cancelando
    todos os pagamentos ativos já registrados, sem apagar o histórico.

    Usado pela ação rápida "Marcar como aberta" na listagem, que é o
    caminho inverso de mark_payable_as_paid.
    """
    with transaction.atomic():
        payable = Payable.objects.select_for_update().get(pk=payable.pk)
        if payable.status == Payable.STATUS_CANCELLED:
            raise ValidationError('Não é possível reabrir uma conta cancelada.')

        payable.payments.filter(status=PayablePayment.STATUS_ACTIVE).update(
            status=PayablePayment.STATUS_CANCELLED
        )

        payable.status = Payable.STATUS_PENDING
        payable.save(update_fields=['status', 'updated_at'])
        return payable
