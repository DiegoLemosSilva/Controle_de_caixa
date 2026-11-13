"""Modelos de empresa (estabelecimento) e vínculo com o usuário autenticado."""

from django.conf import settings
from django.db import models

from apps.core.models import TimestampedModel


class Business(TimestampedModel):
    """Representa um estabelecimento (empresa) cadastrado no sistema."""

    name = models.CharField('Nome do estabelecimento', max_length=150)
    document = models.CharField(
        'CNPJ/CPF',
        max_length=20,
        blank=True,
        help_text='Documento opcional para identificação do estabelecimento.',
    )
    phone = models.CharField('Telefone', max_length=20, blank=True)
    is_active = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['name']

    def __str__(self):
        return self.name


class BusinessOwner(TimestampedModel):
    """
    Vincula um usuário autenticado a uma empresa.

    No MVP cada usuário pertence a exatamente uma empresa (relação
    OneToOne), mas a estrutura permite evoluir para múltiplos usuários
    por empresa no futuro sem romper o isolamento de dados.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name='Usuário',
        on_delete=models.CASCADE,
        related_name='business_owner',
    )
    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='owners',
    )

    class Meta:
        verbose_name = 'Vínculo usuário-empresa'
        verbose_name_plural = 'Vínculos usuário-empresa'

    def __str__(self):
        return f'{self.user.username} -> {self.business.name}'
