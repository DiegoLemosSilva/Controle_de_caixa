"""
Regras de negócio para criação e finalização de vendas e comandas.

Toda a lógica financeira sensível vive aqui, nunca apenas no template
ou no formulário, conforme AGENTS.md (seção 3, item 2).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.cash.services import ensure_date_open, lock_date_open
from apps.core.constants import PAYMENT_METHOD_FIADO
from apps.receivables.models import Receivable

from .models import Comanda, ComandaItem, ComandaPayment, Sale, SalePayment

CENTS = Decimal('0.01')


def _quantize(value):
    return Decimal(value).quantize(CENTS)


def _validate_customer_business(business_id, customer):
    if customer is not None and customer.business_id != business_id:
        raise ValidationError('O cliente deve pertencer à mesma empresa.')


def create_sale(
    business,
    user,
    total_amount,
    payments,
    customer=None,
    description='',
    sold_at=None,
    fiado_amount=Decimal('0.00'),
):
    """
    Cria uma venda finalizada com seus recebimentos e, se houver,
    o recebível de fiado, em uma única transação atômica.

    `payments` é uma lista de dicts: [{'method': ..., 'amount': ...}, ...]
    `fiado_amount` é o valor da venda que ficará como dívida do cliente.

    A soma de `payments` + `fiado_amount` deve ser exatamente igual a
    `total_amount`. Caso contrário, a operação é rejeitada.
    """
    total_amount = _quantize(total_amount)
    fiado_amount = Decimal(fiado_amount or Decimal('0.00'))
    if fiado_amount < 0:
        raise ValidationError('O valor de fiado não pode ser negativo.')
    fiado_amount = _quantize(fiado_amount)
    sold_at = sold_at or timezone.now()
    _validate_customer_business(business.pk, customer)

    if total_amount <= 0:
        raise ValidationError('O valor total da venda deve ser maior que zero.')

    payments_sum = sum((_quantize(p['amount']) for p in payments), Decimal('0.00'))
    computed_total = payments_sum + fiado_amount

    if computed_total != total_amount:
        raise ValidationError(
            'A soma dos recebimentos e do fiado não corresponde ao valor total da venda.'
        )

    if fiado_amount > 0 and customer is None:
        raise ValidationError('Não é possível registrar fiado sem um cliente identificado.')

    for payment in payments:
        if _quantize(payment['amount']) <= 0:
            raise ValidationError('Todo recebimento deve ter valor maior que zero.')

    # IMPORTANTE: `sold_at` é armazenado em UTC (USE_TZ=True). Usar
    # `sold_at.date()` diretamente pegaria a data em UTC, o que faria
    # vendas feitas à noite no horário local (America/Sao_Paulo, UTC-3)
    # serem avaliadas com a data do dia seguinte, rejeitando a venda por
    # "caixa fechado" mesmo com o caixa aberto no dia local correto.
    with transaction.atomic():
        lock_date_open(business, timezone.localtime(sold_at).date())
        sale = Sale.objects.create(
            business=business,
            description=description,
            total_amount=total_amount,
            sold_at=sold_at,
            customer=customer,
            created_by=user,
        )

        for payment in payments:
            SalePayment.objects.create(
                sale=sale,
                method=payment['method'],
                amount=_quantize(payment['amount']),
                received_at=sold_at,
            )

        if fiado_amount > 0:
            Receivable.objects.create(
                business=business,
                customer=customer,
                sale=sale,
                original_amount=fiado_amount,
            )

        return sale


def cancel_sale(sale, user, reason):
    """
    Cancela uma venda preservando o histórico.

    Não exclui registros: marca a venda como cancelada e cancela os
    recebíveis em aberto originados por ela, sem apagar nada.
    """
    if sale.is_cancelled:
        raise ValidationError('Esta venda já está cancelada.')

    # Mesma observação de fuso horário de create_sale: usar a data local,
    # não a data em UTC armazenada internamente no datetime.
    ensure_date_open(sale.business, timezone.localtime(sale.sold_at).date())

    with transaction.atomic():
        sale.status = Sale.STATUS_CANCELLED
        sale.cancelled_at = timezone.now()
        sale.cancelled_by = user
        sale.cancellation_reason = reason
        sale.save(update_fields=[
            'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'
        ])

        sale.receivables.filter(status=Receivable.STATUS_OPEN).update(
            status=Receivable.STATUS_CANCELLED
        )


def open_comanda(business, user, identifier='', customer=None):
    _validate_customer_business(business.pk, customer)
    return Comanda.objects.create(
        business=business,
        identifier=identifier,
        customer=customer,
        opened_by=user,
    )


def delete_empty_comanda(comanda):
    """
    Exclui uma comanda aberta por engano, desde que ainda esteja aberta
    e não tenha nenhum item lançado. Usar exclusão (em vez de
    cancelamento) é seguro aqui porque uma comanda sem itens nunca gerou
    nenhum registro financeiro (nenhuma Sale foi criada), então não há
    histórico financeiro a preservar.
    """
    if not comanda.is_open:
        raise ValidationError('Só é possível excluir uma comanda que ainda está aberta.')

    if comanda.items.exists():
        raise ValidationError(
            'Esta comanda já possui itens lançados e não pode ser excluída. '
            'Cancele a comanda, se necessário.'
        )

    comanda.delete()


def add_comanda_item(comanda, description, quantity, unit_price):
    if not comanda.is_open:
        raise ValidationError('Só é possível adicionar itens a uma comanda aberta.')

    item = ComandaItem(
        comanda=comanda,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
    )
    item.full_clean()
    item.save()
    return item


def update_comanda_item(item, description, quantity, unit_price):
    """Edita um item já lançado em uma comanda ainda aberta."""
    if not item.comanda.is_open:
        raise ValidationError('Só é possível editar itens de uma comanda aberta.')

    item.description = description
    item.quantity = quantity
    item.unit_price = unit_price
    item.full_clean()
    item.save()
    return item


def remove_comanda_item(item):
    """Remove um item lançado em uma comanda ainda aberta."""
    if not item.comanda.is_open:
        raise ValidationError('Só é possível remover itens de uma comanda aberta.')

    item.delete()


def register_comanda_payment(comanda, method, amount, user, customer=None):
    """
    Registra um pagamento parcial em uma comanda ainda aberta.

    Permite que diferentes pessoas em uma mesma mesa paguem partes
    diferentes da conta, cada uma com sua forma de pagamento, à medida
    que vão se decidindo. O valor não pode exceder o saldo restante da
    comanda (total dos itens menos o que já foi pago).

    Quando `method` for fiado, `customer` é obrigatório e pode ser
    diferente do cliente vinculado à comanda (cada pagamento em fiado
    tem seu próprio cliente responsável).

    Enquanto a comanda estiver aberta, este pagamento NÃO é
    contabilizado em nenhum indicador financeiro — isso só ocorre na
    finalização (ver finalize_comanda), evitando duplicidade.
    """
    if not comanda.is_open:
        raise ValidationError('Só é possível registrar pagamentos em uma comanda aberta.')

    _validate_customer_business(comanda.business_id, customer)
    amount = _quantize(amount)
    if amount <= 0:
        raise ValidationError('O valor do pagamento deve ser maior que zero.')

    if method == PAYMENT_METHOD_FIADO and customer is None:
        raise ValidationError('É obrigatório informar o cliente para pagamento em fiado.')

    if amount > comanda.balance:
        raise ValidationError(
            'O valor do pagamento não pode ser maior que o saldo restante da comanda '
            f'(R$ {comanda.balance:.2f}).'
        )

    payment = ComandaPayment(
        comanda=comanda,
        method=method,
        amount=amount,
        customer=customer,
        received_by=user,
    )
    payment.full_clean()
    payment.save()
    return payment


def update_comanda_payment(payment, method, amount, customer=None):
    """
    Edita um pagamento parcial já registrado em uma comanda ainda
    aberta. O novo valor não pode exceder o saldo disponível,
    considerando que o valor atual deste pagamento está sendo liberado
    antes da comparação (ou seja, o limite é o saldo atual + o valor
    antigo deste pagamento).
    """
    comanda = payment.comanda
    if not comanda.is_open:
        raise ValidationError('Só é possível editar pagamentos de uma comanda aberta.')

    _validate_customer_business(comanda.business_id, customer)
    amount = _quantize(amount)
    if amount <= 0:
        raise ValidationError('O valor do pagamento deve ser maior que zero.')

    if method == PAYMENT_METHOD_FIADO and customer is None:
        raise ValidationError('É obrigatório informar o cliente para pagamento em fiado.')

    available = comanda.balance + payment.amount
    if amount > available:
        raise ValidationError(
            'O valor do pagamento não pode ser maior que o saldo disponível '
            f'(R$ {available:.2f}).'
        )

    payment.method = method
    payment.amount = amount
    payment.customer = customer
    payment.full_clean()
    payment.save()
    return payment


def remove_comanda_payment(payment):
    """Remove um pagamento parcial lançado em uma comanda ainda aberta."""
    if not payment.comanda.is_open:
        raise ValidationError('Só é possível remover pagamentos de uma comanda aberta.')

    payment.delete()


def finalize_comanda(comanda, user, sold_at=None):
    """
    Finaliza uma comanda aberta criando uma única venda definitiva.

    Só é permitido finalizar quando o saldo restante for exatamente
    zero (todos os pagamentos parciais já cobrem o total dos itens).
    Consolida todos os ComandaPayment registrados: cada forma normal
    vira um SalePayment; cada pagamento em fiado vira um Receivable
    (um por cliente distinto, se houver mais de um).

    A comanda não pode ser finalizada mais de uma vez: ao final desta
    operação seu status passa a 'finalized' e fica vinculada à Sale
    criada, o que impede nova finalização.
    """
    if not comanda.is_open:
        raise ValidationError('Esta comanda já foi finalizada ou cancelada.')

    total_amount = comanda.total_amount
    if total_amount <= 0:
        raise ValidationError('Não é possível finalizar uma comanda sem itens.')

    balance = comanda.balance
    if balance != 0:
        if balance > 0:
            raise ValidationError(
                f'Ainda faltam R$ {balance:.2f} para finalizar esta comanda. '
                'Registre os pagamentos restantes antes de finalizar.'
            )
        raise ValidationError(
            'O total pago excede o valor da comanda. Verifique os pagamentos registrados.'
        )

    sold_at = sold_at or timezone.now()

    # Mesma observação de fuso horário de create_sale: usar a data
    # local, não a data em UTC armazenada internamente no datetime.
    ensure_date_open(comanda.business, timezone.localtime(sold_at).date())

    comanda_payments = list(comanda.payments.all())

    # Agrupa os pagamentos em fiado por cliente, para criar um único
    # Receivable por cliente mesmo que ele tenha pago em mais de uma vez.
    fiado_by_customer = {}
    normal_payments = []
    for payment in comanda_payments:
        if payment.method == PAYMENT_METHOD_FIADO:
            fiado_by_customer[payment.customer_id] = (
                fiado_by_customer.get(payment.customer_id, Decimal('0.00')) + payment.amount
            )
        else:
            normal_payments.append(payment)

    with transaction.atomic():
        sale = Sale.objects.create(
            business=comanda.business,
            description=f'Comanda {comanda.identifier or comanda.pk}',
            total_amount=total_amount,
            sold_at=sold_at,
            customer=comanda.customer,
            created_by=user,
        )

        for payment in normal_payments:
            SalePayment.objects.create(
                sale=sale,
                method=payment.method,
                amount=payment.amount,
                received_at=payment.paid_at,
            )

        for customer_id, fiado_total in fiado_by_customer.items():
            Receivable.objects.create(
                business=comanda.business,
                customer_id=customer_id,
                sale=sale,
                original_amount=fiado_total,
            )

        comanda.status = Comanda.STATUS_FINALIZED
        comanda.sale = sale
        comanda.save(update_fields=['status', 'sale', 'updated_at'])

    return sale
