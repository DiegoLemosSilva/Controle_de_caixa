"""
Cadastro simples de produtos (nome + preço de venda).

Não é um controle de estoque: serve apenas para pré-preencher a
descrição e o valor unitário ao lançar itens de venda/comanda, e para
permitir uma análise de produtos mais vendidos. Vendas e itens de
comanda continuam aceitando descrição livre normalmente — o produto é
apenas um atalho opcional, nunca uma obrigação.
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.businesses.models import Business
from apps.core.constants import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from apps.core.models import TimestampedModel


class Product(TimestampedModel):
    """Produto cadastrado pela empresa, com nome e preço de venda padrão."""

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='products',
    )
    name = models.CharField('Nome', max_length=150)
    price = models.DecimalField(
        'Preço de venda',
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
    )
    is_active = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['name']
        indexes = [
            models.Index(fields=['business', 'name']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.price is not None and self.price <= 0:
            raise ValidationError('O preço do produto deve ser maior que zero.')
