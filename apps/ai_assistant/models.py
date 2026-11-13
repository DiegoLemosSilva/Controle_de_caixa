"""Registro de uso da integração com a API do Google Gemini."""

from django.conf import settings
from django.db import models

from apps.businesses.models import Business
from apps.core.models import TimestampedModel


class AnalysisTemplate(models.Model):
    """
    Modelo de análise pré-programada disponível na tela do Assistente IA.

    Cada registro representa um botão de análise na tela. O usuário com
    acesso ao Admin pode editar o texto da instrução enviada à IA
    (prompt_template), ativar/desativar a análise e alterar a ordem de
    exibição, sem precisar modificar o código.

    O campo `analysis_type` é uma chave interna que o sistema usa para
    saber quais dados financeiros montar antes de enviar o prompt para
    a IA — esse campo só pode ser escolhido a partir de um conjunto
    fixo de opções definidas no código.
    """

    TYPE_MONTHLY_SUMMARY = 'monthly_summary'
    TYPE_MONTH_COMPARISON = 'month_comparison'
    TYPE_EXPENSES_INCREASE = 'expenses_increase'
    TYPE_PLAN_VS_ACTUAL = 'plan_vs_actual'
    TYPE_ALERTS = 'alerts'
    TYPE_WEEKDAY_SUGGESTION = 'weekday_suggestion'

    TYPE_CHOICES = [
        (TYPE_MONTHLY_SUMMARY, 'Resumo do mês atual'),
        (TYPE_MONTH_COMPARISON, 'Comparação com o mês anterior'),
        (TYPE_EXPENSES_INCREASE, 'Despesas que aumentaram'),
        (TYPE_PLAN_VS_ACTUAL, 'Planejado vs. Realizado'),
        (TYPE_ALERTS, 'Alertas de vencidos e fiado'),
        (TYPE_WEEKDAY_SUGGESTION, 'Sugestão de planejamento por dia da semana'),
    ]

    analysis_type = models.CharField(
        'Tipo de análise',
        max_length=30,
        choices=TYPE_CHOICES,
        unique=True,
    )
    name = models.CharField('Nome', max_length=100)
    description = models.CharField('Descrição curta', max_length=255)
    prompt_template = models.TextField(
        'Instrução enviada à IA',
        help_text=(
            'Texto enviado à IA como instrução para esta análise. '
            'O sistema acrescenta automaticamente os dados financeiros '
            'relevantes antes de enviar. Use {dados} como marcador do '
            'ponto onde os dados serão inseridos, se quiser controlar '
            'a posição — caso contrário eles são adicionados no final.'
        ),
    )
    is_active = models.BooleanField('Ativo', default=True)
    sort_order = models.PositiveSmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Modelo de análise'
        verbose_name_plural = 'Modelos de análise'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class AIInteraction(TimestampedModel):
    """
    Registro de uma interação com a IA (análise automática).

    Armazena apenas o contexto agregado enviado e a resposta recebida,
    nunca dados pessoais de clientes. Serve de auditoria de uso e custo.
    """

    TYPE_ANALYSIS = 'analysis'
    TYPE_CHAT = 'chat'
    TYPE_CHOICES = [
        (TYPE_ANALYSIS, 'Análise automática'),
        (TYPE_CHAT, 'Chat'),
    ]

    business = models.ForeignKey(
        Business,
        verbose_name='Empresa',
        on_delete=models.CASCADE,
        related_name='ai_interactions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Usuário',
        on_delete=models.PROTECT,
        related_name='ai_interactions',
    )
    interaction_type = models.CharField(
        'Tipo', max_length=20, choices=TYPE_CHOICES, default=TYPE_ANALYSIS
    )
    analysis_type = models.CharField(
        'Tipo de análise', max_length=30, blank=True,
    )
    prompt = models.TextField('Pergunta/contexto enviado')
    response = models.TextField('Resposta recebida', blank=True)
    success = models.BooleanField('Sucesso', default=True)
    error_message = models.TextField('Erro', blank=True)

    class Meta:
        verbose_name = 'Interação com IA'
        verbose_name_plural = 'Interações com IA'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_interaction_type_display()} em {self.created_at:%d/%m/%Y %H:%M}'
