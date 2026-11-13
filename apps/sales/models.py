"""
Modelos de vendas e divisão entre formas de pagamento.

Uma venda só é criada quando já está totalmente definida: o valor total,
os recebimentos imediatos e, se houver, o recebível de fiado são
gravados em uma única transação atômica (ver apps/sales/services.py).
Isso evita o estado intermediário de "venda aberta" fora das comandas
e facilita garantir que a mesma venda nunca seja finalizada duas vezes.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.businesses.models import Business
from apps.core.constants import (
    COMANDA_PAYMENT_METHOD_CHOICES,
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    PAYMENT_METHOD_CHOICES,
    PAYMENT_METHOD_FIADO,
)
from apps.core.models import TimestampedModel
from apps.customers.models import Customer


class Sale(TimestampedModel):
    """Uma venda finalizada, com valor total e data/hora do fechamento."""

    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_COMPLETED, 'Concluída'),
        (STATUS_CANCELLED, 'Cancelada'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='sales',
    )
    description = models.CharField('Descrição', max_length=255, blank=True)
    total_amount = models.DecimalField(
        'Valor total',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    sold_at = models.DateTimeField('Data e hora da venda')
    customer = models.ForeignKey(
        Customer,
        verbose_name='Cliente',
        on_delete=models.PROTECT,
        related_name='sales',
        null=True,
        blank=True,
        help_text='Obrigatório quando houver valor fiado nesta venda.',
    )
    status = models.CharField(
        'Situação', max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Registrada por',
        on_delete=models.PROTECT,
        related_name='sales_created',
    )
    cancelled_at = models.DateTimeField('Cancelada em', null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Cancelada por',
        on_delete=models.PROTECT,
        related_name='sales_cancelled',
        null=True,
        blank=True,
    )
    cancellation_reason = models.TextField('Motivo do cancelamento', blank=True)

    class Meta:
        verbose_name = 'Venda'
        verbose_name_plural = 'Vendas'
        ordering = ['-sold_at']
        indexes = [
            models.Index(fields=['business', 'sold_at']),
            models.Index(fields=['business', 'status']),
        ]

    def __str__(self):
        return f'Venda #{self.pk} - R$ {self.total_amount}'

    def clean(self):
        if self.total_amount is not None and self.total_amount <= 0:
            raise ValidationError('O valor total da venda deve ser maior que zero.')

    @property
    def is_cancelled(self):
        return self.status == self.STATUS_CANCELLED


class SalePayment(TimestampedModel):
    """Um recebimento imediato vinculado a uma venda (Pix, dinheiro, etc.)."""

    sale = models.ForeignKey(
        Sale,
        verbose_name='Venda',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    method = models.CharField(
        'Forma de pagamento', max_length=20, choices=PAYMENT_METHOD_CHOICES
    )
    amount = models.DecimalField(
        'Valor recebido',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    received_at = models.DateTimeField('Recebido em')

    class Meta:
        verbose_name = 'Recebimento da venda'
        verbose_name_plural = 'Recebimentos da venda'
        ordering = ['received_at']

    def __str__(self):
        return f'{self.get_method_display()} - R$ {self.amount}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError('O valor recebido deve ser maior que zero.')


class Comanda(TimestampedModel):
    """
    Representa uma venda em andamento (comanda aberta).

    Uma comanda aberta nunca é contabilizada como venda finalizada.
    Ao ser finalizada, gera uma única Sale definitiva com seus
    respectivos SalePayment e Receivable.
    """

    STATUS_OPEN = 'open'
    STATUS_FINALIZED = 'finalized'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Aberta'),
        (STATUS_FINALIZED, 'Finalizada'),
        (STATUS_CANCELLED, 'Cancelada'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='comandas',
    )
    identifier = models.CharField(
        'Identificação', max_length=50, blank=True,
        help_text='Mesa, nome do cliente ou outra referência livre.',
    )
    customer = models.ForeignKey(
        Customer,
        verbose_name='Cliente',
        on_delete=models.PROTECT,
        related_name='comandas',
        null=True,
        blank=True,
    )
    status = models.CharField(
        'Situação', max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Aberta por',
        on_delete=models.PROTECT,
        related_name='comandas_opened',
    )
    opened_at = models.DateTimeField('Aberta em', auto_now_add=True)
    sale = models.OneToOneField(
        Sale,
        verbose_name='Venda gerada',
        on_delete=models.PROTECT,
        related_name='comanda',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Comanda'
        verbose_name_plural = 'Comandas'
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['business', 'status']),
        ]

    def __str__(self):
        label = self.identifier or f'Comanda #{self.pk}'
        return label

    @property
    def is_open(self):
        return self.status == self.STATUS_OPEN

    @property
    def total_amount(self):
        total = self.items.aggregate(
            total=models.Sum(models.F('quantity') * models.F('unit_price'))
        )['total']
        return total or 0

    @property
    def paid_amount(self):
        """Soma de todos os pagamentos parciais já registrados na comanda."""
        total = self.payments.aggregate(total=models.Sum('amount'))['total']
        return total or 0

    @property
    def balance(self):
        """
        Saldo restante a pagar: total dos itens menos o que já foi
        registrado via pagamentos parciais (ComandaPayment). A comanda só
        pode ser finalizada quando este valor for exatamente zero.
        """
        return self.total_amount - self.paid_amount


class ComandaItem(TimestampedModel):
    """Item lançado em uma comanda aberta, com descrição livre."""

    comanda = models.ForeignKey(
        Comanda,
        verbose_name='Comanda',
        on_delete=models.CASCADE,
        related_name='items',
    )
    description = models.CharField('Descrição', max_length=255)
    quantity = models.DecimalField('Quantidade', max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(
        'Valor unitário',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )

    class Meta:
        verbose_name = 'Item da comanda'
        verbose_name_plural = 'Itens da comanda'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.quantity}x {self.description}'

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError('A quantidade deve ser maior que zero.')
        if self.unit_price is not None and self.unit_price <= 0:
            raise ValidationError('O valor unitário deve ser maior que zero.')

    @property
    def subtotal(self):
        return self.quantity * self.unit_price


class ComandaPayment(TimestampedModel):
    """
    Pagamento parcial registrado em uma comanda ainda aberta.

    Permite que várias pessoas em uma mesma mesa paguem partes
    diferentes da conta, à medida que vão se decidindo, cada uma com
    sua própria forma de pagamento. A comanda só pode ser finalizada
    quando a soma de todos os pagamentos cobrir exatamente o total dos
    itens (ver Comanda.balance).

    Enquanto a comanda estiver aberta, esses pagamentos NÃO entram nos
    indicadores financeiros (Vendas, Recebimentos, Caixa): só passam a
    ser contabilizados quando a comanda é finalizada e consolidada em
    uma única Sale (ver apps/sales/services.py, finalize_comanda),
    conforme AGENTS.md (uma comanda aberta nunca é venda finalizada).
    """

    comanda = models.ForeignKey(
        Comanda,
        verbose_name='Comanda',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    method = models.CharField(
        'Forma de pagamento', max_length=20, choices=COMANDA_PAYMENT_METHOD_CHOICES
    )
    amount = models.DecimalField(
        'Valor pago',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    customer = models.ForeignKey(
        Customer,
        verbose_name='Cliente (obrigatório se for fiado)',
        on_delete=models.PROTECT,
        related_name='comanda_payments',
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField('Pago em', auto_now_add=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Registrado por',
        on_delete=models.PROTECT,
        related_name='comanda_payments_received',
    )

    class Meta:
        verbose_name = 'Pagamento parcial da comanda'
        verbose_name_plural = 'Pagamentos parciais da comanda'
        ordering = ['paid_at']

    def __str__(self):
        return f'{self.get_method_display()} - R$ {self.amount}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError('O valor do pagamento deve ser maior que zero.')
        if self.method == PAYMENT_METHOD_FIADO and self.customer is None:
            raise ValidationError('É obrigatório informar o cliente para pagamento em fiado.')
