"""
Modelos de recebíveis (fiado) e seus pagamentos.

Um recebível é sempre originado de uma venda com cliente identificado.
O saldo em aberto é sempre calculado a partir dos pagamentos registrados,
nunca armazenado de forma duplicada, para evitar divergências.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.businesses.models import Business
from apps.core.constants import (
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    PAYMENT_METHOD_CHOICES,
)
from apps.core.models import TimestampedModel
from apps.customers.models import Customer


class Receivable(TimestampedModel):
    """Valor a receber de um cliente, originado de uma venda fiado."""

    STATUS_OPEN = 'open'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Em aberto'),
        (STATUS_PAID, 'Pago'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='receivables',
    )
    customer = models.ForeignKey(
        Customer,
        verbose_name='Cliente',
        on_delete=models.PROTECT,
        related_name='receivables',
    )
    sale = models.ForeignKey(
        'sales.Sale',
        verbose_name='Venda de origem',
        on_delete=models.PROTECT,
        related_name='receivables',
    )
    original_amount = models.DecimalField(
        'Valor original',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    status = models.CharField(
        'Situação', max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN
    )

    class Meta:
        verbose_name = 'Recebível (fiado)'
        verbose_name_plural = 'Recebíveis (fiado)'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'customer', 'status']),
        ]

    def __str__(self):
        return f'Fiado de {self.customer.name} - R$ {self.original_amount}'

    def clean(self):
        if self.original_amount is not None and self.original_amount <= 0:
            raise ValidationError('O valor original do recebível deve ser maior que zero.')

    @property
    def paid_amount(self):
        total = self.payments.exclude(
            status=ReceivablePayment.STATUS_CANCELLED
        ).aggregate(total=models.Sum('amount'))['total']
        return total or 0

    @property
    def balance(self):
        return self.original_amount - self.paid_amount


class ReceivablePayment(TimestampedModel):
    """Pagamento (total ou parcial) de um recebível em aberto."""

    STATUS_ACTIVE = 'active'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Ativo'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    receivable = models.ForeignKey(
        Receivable,
        verbose_name='Recebível',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(
        'Valor pago',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    method = models.CharField(
        'Forma de pagamento', max_length=20, choices=PAYMENT_METHOD_CHOICES
    )
    paid_at = models.DateTimeField('Pago em')
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Registrado por',
        on_delete=models.PROTECT,
        related_name='receivable_payments_registered',
    )
    status = models.CharField(
        'Situação', max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )

    class Meta:
        verbose_name = 'Pagamento de recebível'
        verbose_name_plural = 'Pagamentos de recebíveis'
        ordering = ['paid_at']

    def __str__(self):
        return f'Pagamento de R$ {self.amount} em {self.paid_at:%d/%m/%Y}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError('O valor do pagamento deve ser maior que zero.')
