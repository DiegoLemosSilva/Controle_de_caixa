"""Modelos abstratos reutilizáveis entre os aplicativos do domínio."""

from django.db import models


class TimestampedModel(models.Model):
    """Modelo abstrato com campos de auditoria de criação e atualização."""

    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        abstract = True
