"""
Integração com a API do Google Gemini.

Regras (AGENTS.md seção 14):
- A IA nunca acessa o banco diretamente; recebe apenas um contexto
  textual agregado, previamente calculado pela aplicação Django.
- A chave de API vem de variável de ambiente e nunca é exposta ao
  navegador.
- Timeout, tratamento de erro e desativação por configuração são
  obrigatórios, para que a indisponibilidade da IA nunca impeça o
  funcionamento financeiro do sistema.

Cada análise pré-programada tem sua própria função de montagem de
contexto (_build_context_*), que coleta os indicadores financeiros já
calculados pelo sistema e os formata como texto agregado. O texto
resultante é inserido no prompt_template do AnalysisTemplate antes de
ser enviado à IA.
"""

import calendar
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.cash.services import build_summary
from apps.payables.models import Payable
from apps.receivables.models import Receivable

from .models import AIInteraction, AnalysisTemplate


WEEKDAY_NAMES = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']


class GeminiUnavailableError(Exception):
    """Lançada quando a IA está desabilitada ou indisponível."""


def is_ai_enabled():
    return bool(settings.GEMINI_ENABLED and settings.GEMINI_API_KEY)


# --- Funções de montagem de contexto por tipo de análise ---------------

def _build_context_monthly_summary(business):
    """Resumo geral do mês atual."""
    today = timezone.localdate()
    start = today.replace(day=1)
    summary = build_summary(business, start, today)

    overdue_count = Payable.objects.filter(
        business=business, due_date__lt=today
    ).exclude(status__in=[Payable.STATUS_PAID, Payable.STATUS_CANCELLED]).count()

    open_recv_count = Receivable.objects.filter(
        business=business, status=Receivable.STATUS_OPEN
    ).count()

    return (
        f'Período: {start:%d/%m/%Y} a {today:%d/%m/%Y}.\n'
        f'Vendas realizadas: R$ {summary["sales"]:.2f}.\n'
        f'Recebimentos efetivos: R$ {summary["receipts"]:.2f}.\n'
        f'Despesas pagas: R$ {summary["paid_expenses"]:.2f}.\n'
        f'Saldo em aberto de clientes (fiado): R$ {summary["pending_receivables"]:.2f} '
        f'({open_recv_count} cliente(s) com saldo).\n'
        f'Contas a pagar em aberto: R$ {summary["pending_payables"]:.2f} '
        f'({overdue_count} conta(s) vencida(s) sem pagamento).'
    )


def _build_context_month_comparison(business):
    """Comparação entre este mês e o mês anterior."""
    today = timezone.localdate()
    start_this = today.replace(day=1)
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1
    _, last_day_prev = calendar.monthrange(prev_year, prev_month)
    start_prev = date(prev_year, prev_month, 1)
    end_prev = date(prev_year, prev_month, last_day_prev)

    this = build_summary(business, start_this, today)
    prev = build_summary(business, start_prev, end_prev)

    def pct(current, previous):
        if previous == 0:
            return 'N/A'
        return f'{((current - previous) / previous * 100):+.1f}%'

    return (
        f'--- Mês atual ({start_this:%d/%m/%Y} a {today:%d/%m/%Y}) ---\n'
        f'Vendas: R$ {this["sales"]:.2f}\n'
        f'Recebimentos: R$ {this["receipts"]:.2f}\n'
        f'Despesas pagas: R$ {this["paid_expenses"]:.2f}\n\n'
        f'--- Mês anterior ({start_prev:%d/%m/%Y} a {end_prev:%d/%m/%Y}) ---\n'
        f'Vendas: R$ {prev["sales"]:.2f}\n'
        f'Recebimentos: R$ {prev["receipts"]:.2f}\n'
        f'Despesas pagas: R$ {prev["paid_expenses"]:.2f}\n\n'
        f'--- Variação ---\n'
        f'Vendas: {pct(this["sales"], prev["sales"])}\n'
        f'Recebimentos: {pct(this["receipts"], prev["receipts"])}\n'
        f'Despesas pagas: {pct(this["paid_expenses"], prev["paid_expenses"])}'
    )


def _build_context_expenses_increase(business):
    """Variação das despesas entre este mês e o mês anterior."""
    return _build_context_month_comparison(business)


def _build_context_plan_vs_actual(business):
    """Comparação de Planejado vs. Realizado do mês atual (Faturamento e Gastos)."""
    from apps.planning.models import FinancialPlan
    from apps.planning.services import build_comparison
    from apps.planning.views import _expenses_actuals_by_date, _revenue_actuals_by_date

    today = timezone.localdate()
    year, month = today.year, today.month

    rev_actuals = _revenue_actuals_by_date(business, year, month)
    exp_actuals = _expenses_actuals_by_date(business, year, month)

    rev_comparison = build_comparison(
        business, FinancialPlan.INDICATOR_REVENUE, year, month, rev_actuals
    )
    exp_comparison = build_comparison(
        business, FinancialPlan.INDICATOR_PAID_EXPENSES, year, month, exp_actuals,
        allow_pending=False,
    )

    total_rev_planned = sum(e['planned'] for e in rev_comparison)
    total_rev_actual = sum(e['actual'] for e in rev_comparison if not e['is_pending'])
    total_exp_planned = sum(e['planned'] for e in exp_comparison)
    total_exp_actual = sum(e['actual'] for e in exp_comparison)

    lines = [
        f'Mês: {month:02d}/{year}',
        '',
        '--- Faturamento ---',
        f'Total planejado: R$ {total_rev_planned:.2f}',
        f'Total realizado: R$ {total_rev_actual:.2f}',
        f'Diferença: R$ {(total_rev_actual - total_rev_planned):.2f}',
        '',
        '--- Gastos ---',
        f'Total planejado: R$ {total_exp_planned:.2f}',
        f'Total realizado: R$ {total_exp_actual:.2f}',
        f'Diferença: R$ {(total_exp_actual - total_exp_planned):.2f}',
        '',
        '--- Detalhe por dia (data, faturamento planejado/realizado, gastos planejado/realizado) ---',
    ]
    for rev_e, exp_e in zip(rev_comparison, exp_comparison):
        rev_actual_str = 'Pendente' if rev_e['is_pending'] else f'R$ {rev_e["actual"]:.2f}'
        lines.append(
            f'{rev_e["date"]:%d/%m}: '
            f'Fat. Plan R$ {rev_e["planned"]:.2f} / Real {rev_actual_str} | '
            f'Gas. Plan R$ {exp_e["planned"]:.2f} / Real R$ {exp_e["actual"]:.2f}'
        )

    return '\n'.join(lines)


def _build_context_alerts(business):
    """Resumo de contas vencidas e clientes com fiado em aberto."""
    today = timezone.localdate()

    overdue = Payable.objects.filter(
        business=business, due_date__lt=today
    ).exclude(status__in=[Payable.STATUS_PAID, Payable.STATUS_CANCELLED]).order_by('due_date')

    open_receivables = Receivable.objects.filter(
        business=business, status=Receivable.STATUS_OPEN
    ).order_by('-created_at')

    lines = [
        f'Data de hoje: {today:%d/%m/%Y}',
        '',
        f'--- Contas a pagar vencidas: {overdue.count()} ---',
    ]
    if overdue.exists():
        for p in overdue[:10]:
            lines.append(
                f'  - "{p.description}" | Vencida em {p.due_date:%d/%m/%Y} | '
                f'Saldo: R$ {p.balance:.2f}'
            )
        if overdue.count() > 10:
            lines.append(f'  ... e mais {overdue.count() - 10} conta(s).')
    else:
        lines.append('  Nenhuma conta vencida.')

    lines += [
        '',
        f'--- Clientes com fiado em aberto: {open_receivables.count()} ---',
    ]
    total_recv = Decimal('0.00')
    for r in open_receivables[:10]:
        total_recv += r.balance
        lines.append(f'  - Saldo: R$ {r.balance:.2f}')
    if open_receivables.count() > 10:
        extra = open_receivables.count() - 10
        lines.append(f'  ... e mais {extra} cliente(s).')

    lines.append(f'\nTotal de fiado em aberto: R$ {total_recv:.2f}')
    return '\n'.join(lines)


def _build_context_weekday_suggestion(business):
    """
    Histórico de faturamento e gastos por dia da semana dos últimos 3 meses,
    para a IA sugerir metas por dia da semana.
    """
    from apps.cash.services import paid_expenses_total, receipts_total

    today = timezone.localdate()

    # Últimos 3 meses completos
    months = []
    year, month = today.year, today.month
    for _ in range(3):
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
        _, last_day = calendar.monthrange(year, month)
        months.append((year, month, last_day))

    # Agregar por dia da semana
    rev_by_weekday = {i: Decimal('0.00') for i in range(7)}
    exp_by_weekday = {i: Decimal('0.00') for i in range(7)}
    count_by_weekday = {i: 0 for i in range(7)}

    for y, m, last_d in months:
        for d in range(1, last_d + 1):
            current = date(y, m, d)
            weekday = current.weekday()
            rev = receipts_total(business, current, current)
            exp = paid_expenses_total(business, current, current)
            if rev > 0 or exp > 0:
                rev_by_weekday[weekday] += rev
                exp_by_weekday[weekday] += exp
                count_by_weekday[weekday] += 1

    lines = [
        'Histórico médio por dia da semana (últimos 3 meses completos):',
        '',
        f'{"Dia":<12} | {"Faturamento médio":>20} | {"Gastos médios":>15}',
        '-' * 55,
    ]
    for i, name in enumerate(WEEKDAY_NAMES):
        count = count_by_weekday[i] or 1
        avg_rev = rev_by_weekday[i] / count
        avg_exp = exp_by_weekday[i] / count
        lines.append(f'{name:<12} | R$ {avg_rev:>17.2f} | R$ {avg_exp:>12.2f}')

    return '\n'.join(lines)


# Mapa de tipo de análise → função de contexto
CONTEXT_BUILDERS = {
    AnalysisTemplate.TYPE_MONTHLY_SUMMARY: _build_context_monthly_summary,
    AnalysisTemplate.TYPE_MONTH_COMPARISON: _build_context_month_comparison,
    AnalysisTemplate.TYPE_EXPENSES_INCREASE: _build_context_expenses_increase,
    AnalysisTemplate.TYPE_PLAN_VS_ACTUAL: _build_context_plan_vs_actual,
    AnalysisTemplate.TYPE_ALERTS: _build_context_alerts,
    AnalysisTemplate.TYPE_WEEKDAY_SUGGESTION: _build_context_weekday_suggestion,
}


# --- Envio à IA e registro -------------------------------------------

def _call_gemini(prompt):
    """
    Chama a API do Gemini com timeout configurado.

    Isolado em função própria para facilitar testes (mock) e para que
    qualquer biblioteca cliente seja usada apenas aqui.
    """
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    # request_options aceita timeout em segundos (int/float)
    response = model.generate_content(
        prompt,
        request_options={'timeout': int(settings.GEMINI_TIMEOUT_SECONDS)},
    )
    return response.text


def ask(business, user, prompt, analysis_type=''):
    """
    Envia um prompt à IA e registra a interação.

    Nunca lança exceção para o chamador além de GeminiUnavailableError
    quando a IA está desabilitada; outras falhas são registradas e
    retornadas como mensagem amigável, sem interromper o sistema.

    Conexões antigas só são descartadas fora de transações ativas.
    """
    from django.db import close_old_connections, connection

    if not is_ai_enabled():
        raise GeminiUnavailableError(
            'A assistente de IA está desativada nesta instalação.'
        )

    # Não fechar a conexão de uma transação em andamento.
    if not connection.in_atomic_block:
        close_old_connections()

    try:
        answer = _call_gemini(prompt)
    except Exception as exc:  # noqa: BLE001
        if not connection.in_atomic_block:
            close_old_connections()
        try:
            AIInteraction.objects.create(
                business=business,
                user=user,
                interaction_type=AIInteraction.TYPE_ANALYSIS,
                analysis_type=analysis_type,
                prompt=prompt,
                response='',
                success=False,
                error_message=str(exc),
            )
        except Exception:  # noqa: BLE001
            pass  # Não impede o retorno da mensagem de erro
        return (
            'Não foi possível obter uma resposta da assistente de IA agora. '
            'Os dados financeiros continuam disponíveis normalmente nas '
            'demais telas do sistema.'
        )

    if not connection.in_atomic_block:
        close_old_connections()
    AIInteraction.objects.create(
        business=business,
        user=user,
        interaction_type=AIInteraction.TYPE_ANALYSIS,
        analysis_type=analysis_type,
        prompt=prompt,
        response=answer,
        success=True,
    )
    return answer


def run_analysis(business, user, template):
    """
    Executa uma análise pré-programada a partir de um AnalysisTemplate.

    Monta o contexto financeiro adequado ao tipo da análise, substitui
    {dados} no prompt_template pelo contexto e envia à IA.
    """
    if not is_ai_enabled():
        raise GeminiUnavailableError(
            'A assistente de IA está desativada nesta instalação.'
        )

    context_fn = CONTEXT_BUILDERS.get(template.analysis_type)
    if context_fn is None:
        return 'Tipo de análise não reconhecido.'

    dados = context_fn(business)

    if '{dados}' in template.prompt_template:
        prompt = template.prompt_template.replace('{dados}', dados)
    else:
        prompt = template.prompt_template + '\n\n' + dados

    return ask(business, user, prompt, analysis_type=template.analysis_type)
