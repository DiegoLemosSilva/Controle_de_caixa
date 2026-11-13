"""
Modelos do app cash.

CashCountAdjustment registra a conferência do caixa físico contra o
valor esperado pelo sistema (vendas, recebimentos e pagamentos daquela
forma de pagamento no dia). É um registro histórico, nunca apagado ou
sobrescrito: uma correção gera um novo registro, preservando o anterior
para auditoria (ver AGENTS.md, seção 16 - preferir estornos auditáveis
a exclusões silenciosas).

CashSession representa o ciclo de vida completo do caixa físico de um
dia: abertura (com valor inicial em dinheiro), fechamento e eventual
reabertura. Por padrão, uma data SEM sessão aberta está bloqueada para
lançamentos financeiros (ver AGENTS.md, seção 13) — é preciso abrir o
caixa explicitamente antes de registrar vendas, recebimentos ou
pagamentos. Só pode existir uma sessão aberta por empresa a qualquer
momento (regra de caixa único).
"""

from django.conf import settings
from django.db import models

from apps.businesses.models import Business
from apps.core.constants import (
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    PAYMENT_METHOD_CHOICES,
)
from apps.core.models import TimestampedModel


class CashCountAdjustment(TimestampedModel):
    """
    Conferência do caixa físico de uma forma de pagamento em um dia.

    `expected_amount` é calculado automaticamente pelo sistema no momento
    do registro (nunca informado manualmente) e armazenado como
    "fotografia" daquele instante, para que o histórico permaneça correto
    mesmo que novos lançamentos sejam feitos depois para a mesma data.

    Pode haver mais de um registro para a mesma empresa/data/forma de
    pagamento: o mais recente é considerado o oficial. Isso permite
    corrigir uma conferência equivocada sem apagar o histórico.
    """

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='cash_count_adjustments',
    )
    date = models.DateField('Data conferida')
    payment_method = models.CharField(
        'Forma de pagamento', max_length=20, choices=PAYMENT_METHOD_CHOICES
    )
    expected_amount = models.DecimalField(
        'Valor esperado pelo sistema',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    counted_amount = models.DecimalField(
        'Valor contado fisicamente',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    reason = models.TextField('Justificativa')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Conferido por',
        on_delete=models.PROTECT,
        related_name='cash_count_adjustments_created',
    )

    class Meta:
        verbose_name = 'Conferência de caixa'
        verbose_name_plural = 'Conferências de caixa'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'date', 'payment_method']),
        ]

    def __str__(self):
        return f'{self.date:%d/%m/%Y} - {self.get_payment_method_display()}'

    @property
    def difference(self):
        """Positivo = sobra de caixa. Negativo = falta de caixa."""
        return self.counted_amount - self.expected_amount


class CashSession(TimestampedModel):
    """
    Sessão de caixa físico: abertura, fechamento e eventual reabertura.

    Por padrão o caixa está fechado para qualquer data. Para registrar
    vendas, recebimentos ou pagamentos em uma data, é necessário abrir
    uma sessão para ela, informando o valor inicial em dinheiro.

    Regra de caixa único: não pode existir mais de uma sessão com
    status 'open' simultaneamente para a mesma empresa.
    """

    STATUS_OPEN = 'open'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Aberto'),
        (STATUS_CLOSED, 'Fechado'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='cash_sessions',
    )
    date = models.DateField('Data do movimento')
    status = models.CharField(
        'Situação', max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN
    )
    opening_amount = models.DecimalField(
        'Valor de abertura (dinheiro)',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        help_text='Valor em dinheiro que iniciou o caixa físico neste dia.',
    )
    opened_at = models.DateTimeField('Aberto em')
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Aberto por',
        on_delete=models.PROTECT,
        related_name='cash_sessions_opened',
    )
    closed_at = models.DateTimeField('Fechado em', null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Fechado por',
        on_delete=models.PROTECT,
        related_name='cash_sessions_closed',
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField('Reaberto em', null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Reaberto por',
        on_delete=models.PROTECT,
        related_name='cash_sessions_reopened',
        null=True,
        blank=True,
    )
    reopen_reason = models.TextField('Motivo da reabertura', blank=True)

    class Meta:
        verbose_name = 'Sessão de caixa'
        verbose_name_plural = 'Sessões de caixa'
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'date'],
                name='unique_cash_session_per_business_date',
            ),
            models.UniqueConstraint(
                fields=['business'],
                condition=models.Q(status='open'),
                name='unique_open_cash_session_per_business',
            ),
        ]

    def __str__(self):
        return f'{self.date:%d/%m/%Y} ({self.get_status_display()})'

    @property
    def is_open(self):
        return self.status == self.STATUS_OPEN


class CashSessionEvent(TimestampedModel):
    """Histórico auditável dos eventos de abertura, fechamento e reabertura."""

    EVENT_OPENED = 'opened'
    EVENT_CLOSED = 'closed'
    EVENT_REOPENED = 'reopened'
    EVENT_CHOICES = [
        (EVENT_OPENED, 'Abertura'),
        (EVENT_CLOSED, 'Fechamento'),
        (EVENT_REOPENED, 'Reabertura'),
    ]

    session = models.ForeignKey(
        CashSession,
        verbose_name='Sessão de caixa',
        on_delete=models.CASCADE,
        related_name='events',
    )
    event_type = models.CharField('Tipo de evento', max_length=20, choices=EVENT_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Realizado por',
        on_delete=models.PROTECT,
        related_name='cash_session_events',
    )
    performed_at = models.DateTimeField('Realizado em', auto_now_add=True)
    reason = models.TextField('Motivo', blank=True)

    class Meta:
        verbose_name = 'Evento de sessão de caixa'
        verbose_name_plural = 'Eventos de sessão de caixa'
        ordering = ['performed_at']

    def __str__(self):
        return f'{self.get_event_type_display()} em {self.performed_at:%d/%m/%Y %H:%M}'
