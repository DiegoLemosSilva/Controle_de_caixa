"""Popula os 6 modelos de análise pré-programados iniciais."""

from django.db import migrations


INITIAL_TEMPLATES = [
    {
        'analysis_type': 'monthly_summary',
        'name': 'Resumo do mês',
        'description': 'Análise geral do desempenho financeiro do mês atual.',
        'prompt_template': (
            'Você é uma assistente financeira para pequenos comerciantes. '
            'Com base apenas nos dados agregados abaixo, faça uma análise '
            'objetiva e clara do desempenho financeiro do mês. Destaque '
            'pontos positivos e pontos de atenção. Não invente números e '
            'não prometa previsões precisas ou aconselhamento financeiro '
            'profissional. Se faltar dado suficiente, diga isso claramente.\n\n'
            '{dados}'
        ),
        'sort_order': 1,
    },
    {
        'analysis_type': 'month_comparison',
        'name': 'Comparação com o mês anterior',
        'description': 'Como este mês se compara ao mês passado em vendas, recebimentos e despesas.',
        'prompt_template': (
            'Você é uma assistente financeira para pequenos comerciantes. '
            'Com base nos dados dos dois períodos abaixo, compare os '
            'indicadores financeiros (vendas, recebimentos, despesas). '
            'Indique o que melhorou, o que piorou e quanto foi a variação '
            'percentual. Seja objetivo. Não invente valores.\n\n'
            '{dados}'
        ),
        'sort_order': 2,
    },
    {
        'analysis_type': 'expenses_increase',
        'name': 'Despesas que aumentaram',
        'description': 'Identifica se as despesas cresceram em relação ao mês anterior e em quanto.',
        'prompt_template': (
            'Você é uma assistente financeira para pequenos comerciantes. '
            'Com base nos dados abaixo, analise se as despesas pagas '
            'cresceram em relação ao período anterior e em quanto. '
            'Se houver crescimento, destaque o impacto no resultado do '
            'negócio. Seja direto e objetivo. Não invente valores.\n\n'
            '{dados}'
        ),
        'sort_order': 3,
    },
    {
        'analysis_type': 'plan_vs_actual',
        'name': 'Planejado vs. Realizado',
        'description': 'Como o mês está em relação às metas de faturamento e gastos definidas no Planejamento.',
        'prompt_template': (
            'Você é uma assistente financeira para pequenos comerciantes. '
            'Com base nos dados de Planejamento vs. Realizado abaixo, '
            'analise se o negócio está atingindo suas metas de faturamento '
            'e controlando bem os gastos. Indique os dias ou períodos com '
            'maior divergência e sugira atenção. Não invente valores.\n\n'
            '{dados}'
        ),
        'sort_order': 4,
    },
    {
        'analysis_type': 'alerts',
        'name': 'Alertas: vencidas e fiado',
        'description': 'Resumo das contas vencidas sem pagamento e dos clientes com fiado em aberto.',
        'prompt_template': (
            'Você é uma assistente financeira para pequenos comerciantes. '
            'Com base nos dados abaixo sobre contas a pagar vencidas e '
            'clientes com fiado em aberto, faça um alerta claro e objetivo '
            'sobre os riscos financeiros imediatos. Sugira prioridades de '
            'ação. Não invente valores nem nomes de clientes.\n\n'
            '{dados}'
        ),
        'sort_order': 5,
    },
    {
        'analysis_type': 'weekday_suggestion',
        'name': 'Sugestão de planejamento por dia da semana',
        'description': 'A IA analisa o histórico e sugere metas de faturamento e gastos para cada dia da semana.',
        'prompt_template': (
            'Você é uma assistente financeira para pequenos comerciantes. '
            'Com base no histórico de faturamento e gastos por dia da '
            'semana dos últimos meses (abaixo), sugira valores de meta '
            'para cada dia da semana (segunda a domingo), separando '
            'Faturamento e Gastos. Apresente os valores sugeridos em uma '
            'tabela clara. Baseie as sugestões apenas nos dados '
            'fornecidos. Não invente valores.\n\n'
            '{dados}'
        ),
        'sort_order': 6,
    },
]


def seed_templates(apps, schema_editor):
    AnalysisTemplate = apps.get_model('ai_assistant', 'AnalysisTemplate')
    for data in INITIAL_TEMPLATES:
        AnalysisTemplate.objects.get_or_create(
            analysis_type=data['analysis_type'],
            defaults={k: v for k, v in data.items() if k != 'analysis_type'},
        )


def unseed_templates(apps, schema_editor):
    AnalysisTemplate = apps.get_model('ai_assistant', 'AnalysisTemplate')
    AnalysisTemplate.objects.filter(
        analysis_type__in=[t['analysis_type'] for t in INITIAL_TEMPLATES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0002_add_analysis_template'),
    ]

    operations = [
        migrations.RunPython(seed_templates, unseed_templates),
    ]
