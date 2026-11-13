"""Modelos de contas a pagar e seus pagamentos."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.businesses.models import Business
from apps.core.constants import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from apps.core.models import TimestampedModel


class Payable(TimestampedModel):
    """
    Uma conta a pagar.

    A criação de uma conta a pagar NÃO representa saída de caixa. A
    saída só ocorre quando um PayablePayment é efetivamente registrado.
    """

    STATUS_PENDING = 'pending'
    STATUS_PARTIALLY_PAID = 'partially_paid'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_PARTIALLY_PAID, 'Parcialmente paga'),
        (STATUS_PAID, 'Paga'),
        (STATUS_CANCELLED, 'Cancelada'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='payables',
    )
    description = models.CharField('Descrição', max_length=255)
    supplier_name = models.CharField('Fornecedor', max_length=150, blank=True)
    original_amount = models.DecimalField(
        'Valor original',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    due_date = models.DateField('Data prevista para pagamento')
    status = models.CharField(
        'Situação', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Registrada por',
        on_delete=models.PROTECT,
        related_name='payables_created',
    )

    class Meta:
        verbose_name = 'Conta a pagar'
        verbose_name_plural = 'Contas a pagar'
        ordering = ['due_date']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['business', 'due_date']),
        ]

    def __str__(self):
        return f'{self.description} - R$ {self.original_amount}'

    def clean(self):
        if self.original_amount is not None and self.original_amount <= 0:
            raise ValidationError('O valor original deve ser maior que zero.')

    @property
    def paid_amount(self):
        total = self.payments.exclude(
            status=PayablePayment.STATUS_CANCELLED
        ).aggregate(total=models.Sum('amount'))['total']
        return total or 0

    @property
    def balance(self):
        return self.original_amount - self.paid_amount

    @property
    def is_overdue(self):
        return (
            self.status not in (self.STATUS_PAID, self.STATUS_CANCELLED)
            and self.due_date < timezone.localdate()
        )

    def effective_status(self):
        """Situação exibida considerando vencimento, sem alterar o campo status."""
        if self.status in (self.STATUS_PAID, self.STATUS_CANCELLED):
            return self.status
        if self.is_overdue:
            return 'overdue'
        return self.status


class PayablePayment(TimestampedModel):
    """Pagamento (total ou parcial) de uma conta a pagar."""

    STATUS_ACTIVE = 'active'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Ativo'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    payable = models.ForeignKey(
        Payable,
        verbose_name='Conta a pagar',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(
        'Valor pago',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    paid_at = models.DateTimeField('Pago em')
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Registrado por',
        on_delete=models.PROTECT,
        related_name='payable_payments_registered',
    )
    status = models.CharField(
        'Situação', max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )

    class Meta:
        verbose_name = 'Pagamento de conta a pagar'
        verbose_name_plural = 'Pagamentos de contas a pagar'
        ordering = ['paid_at']

    def __str__(self):
        return f'Pagamento de R$ {self.amount} em {self.paid_at:%d/%m/%Y}'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError('O valor do pagamento deve ser maior que zero.')
