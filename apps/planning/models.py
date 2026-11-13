"""Modelos de planejamento financeiro mensal por dia do calendário."""

from django.db import models

from apps.businesses.models import Business
from apps.core.constants import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from apps.core.models import TimestampedModel


class FinancialPlan(TimestampedModel):
    """
    Meta planejada para um indicador, em uma data específica.

    Cada combinação (empresa, indicador, data) é única: ao aplicar um
    valor-base por dia da semana, cada data do mês recebe um único
    registro, que pode depois ser sobrescrito individualmente.
    """

    INDICATOR_REVENUE = 'revenue'
    INDICATOR_PAID_EXPENSES = 'paid_expenses'
    INDICATOR_CHOICES = [
        (INDICATOR_REVENUE, 'Faturamento'),
        (INDICATOR_PAID_EXPENSES, 'Gastos'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='financial_plans',
    )
    indicator = models.CharField('Indicador', max_length=20, choices=INDICATOR_CHOICES)
    date = models.DateField('Data planejada')
    planned_amount = models.DecimalField(
        'Valor planejado',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )

    class Meta:
        verbose_name = 'Planejamento financeiro'
        verbose_name_plural = 'Planejamentos financeiros'
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'indicator', 'date'],
                name='unique_plan_per_business_indicator_date',
            )
        ]
        indexes = [
            models.Index(fields=['business', 'indicator', 'date']),
        ]

    def __str__(self):
        return f'{self.get_indicator_display()} em {self.date:%d/%m/%Y}: R$ {self.planned_amount}'
