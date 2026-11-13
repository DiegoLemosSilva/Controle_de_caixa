"""Modelo de clientes, utilizado para vendas fiado e histórico de dívidas."""

from django.core.validators import MinValueValidator
from django.db import models

from apps.businesses.models import Business
from apps.core.models import TimestampedModel


class Customer(TimestampedModel):
    """Cliente de uma empresa, usado principalmente para controle de fiado."""

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='customers',
    )
    name = models.CharField('Nome', max_length=150)
    phone = models.CharField('Telefone', max_length=20, blank=True)
    notes = models.TextField('Observações', blank=True)
    credit_limit = models.DecimalField(
        'Limite de fiado', max_digits=12, decimal_places=2,
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Opcional. Apenas emite um aviso; não bloqueia lançamentos.',
    )
    is_active = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['name']
        indexes = [
            models.Index(fields=['business', 'name']),
        ]

    def __str__(self):
        return self.name

    def open_balance(self):
        """Soma o saldo em aberto de todos os recebíveis não cancelados."""
        from apps.receivables.models import Receivable

        receivables = Receivable.objects.filter(
            customer=self
        ).exclude(status=Receivable.STATUS_CANCELLED)
        total = sum((r.balance for r in receivables), start=0)
        return total
