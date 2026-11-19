"""Modelos de contas a pagar, seus pagamentos e séries recorrentes."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.businesses.models import Business
from apps.core.constants import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from apps.core.models import TimestampedModel


WEEKDAY_CHOICES = [
    (0, 'Segunda-feira'),
    (1, 'Terça-feira'),
    (2, 'Quarta-feira'),
    (3, 'Quinta-feira'),
    (4, 'Sexta-feira'),
    (5, 'Sábado'),
    (6, 'Domingo'),
]


class PayableSeries(TimestampedModel):
    """
    "Molde" de uma conta a pagar recorrente (fixa, semanal ou parcelada).

    A série nunca representa, por si só, um lançamento financeiro: cada
    ocorrência é um Payable normal e independente, com seu próprio
    saldo, pagamentos e histórico. A série apenas controla a geração de
    novas ocorrências e permite editar várias de uma vez.
    """

    KIND_FIXED = 'fixed'
    KIND_WEEKLY = 'weekly'
    KIND_INSTALLMENT = 'installment'
    KIND_CHOICES = [
        (KIND_FIXED, 'Fixa mensal'),
        (KIND_WEEKLY, 'Semanal'),
        (KIND_INSTALLMENT, 'Parcelada'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='payable_series',
    )
    kind = models.CharField('Tipo', max_length=20, choices=KIND_CHOICES)
    description = models.CharField('Descrição', max_length=255)
    supplier_name = models.CharField('Fornecedor', max_length=150, blank=True)
    amount = models.DecimalField(
        'Valor de cada ocorrência',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    # Usado apenas por séries fixas: dia do mês em que a conta vence
    # (ex.: 10 para "todo dia 10"). Dias além do último dia do mês
    # (ex.: 31 em fevereiro) recuam para o último dia disponível.
    day_of_month = models.PositiveSmallIntegerField(
        'Dia do mês', null=True, blank=True
    )
    # Usado apenas por séries semanais.
    weekday = models.PositiveSmallIntegerField(
        'Dia da semana', choices=WEEKDAY_CHOICES, null=True, blank=True
    )
    # Usado apenas por séries parceladas: quantidade total de parcelas,
    # todas geradas de uma vez na criação da série.
    total_installments = models.PositiveSmallIntegerField(
        'Total de parcelas', null=True, blank=True
    )
    # Para fixa/semanal: permite pausar a geração de novas ocorrências
    # sem afetar as já criadas. Sempre True para parceladas (não há
    # geração contínua a pausar).
    is_active = models.BooleanField('Gerando novas ocorrências', default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Criada por',
        on_delete=models.PROTECT,
        related_name='payable_series_created',
    )

    class Meta:
        verbose_name = 'Série de contas a pagar'
        verbose_name_plural = 'Séries de contas a pagar'
        ordering = ['description']

    def __str__(self):
        return f'{self.description} ({self.get_kind_display()})'

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError('O valor de cada ocorrência deve ser maior que zero.')
        if self.kind == self.KIND_FIXED and not self.day_of_month:
            raise ValidationError('Informe o dia do mês para uma série fixa.')
        if self.kind == self.KIND_WEEKLY and self.weekday is None:
            raise ValidationError('Informe o dia da semana para uma série semanal.')
        if self.kind == self.KIND_INSTALLMENT and not self.total_installments:
            raise ValidationError('Informe o número de parcelas para uma série parcelada.')


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
    # Campos opcionais de recorrência. Uma conta sem `series` é uma
    # conta "única", com comportamento idêntico ao de antes dessa
    # funcionalidade existir.
    series = models.ForeignKey(
        'PayableSeries',
        verbose_name='Série',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='payables',
    )
    installment_number = models.PositiveSmallIntegerField(
        'Número da parcela', null=True, blank=True
    )
    # Marca que esta ocorrência foi editada manualmente de forma
    # divergente do "molde" da série (valor ou data diferentes).
    # Edições em massa da série nunca sobrescrevem ocorrências com
    # esta marca, preservando a escolha explícita do usuário.
    detached_from_series = models.BooleanField(
        'Alterada manualmente', default=False
    )

    class Meta:
        verbose_name = 'Conta a pagar'
        verbose_name_plural = 'Contas a pagar'
        ordering = ['due_date']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['business', 'due_date']),
            models.Index(fields=['series']),
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
