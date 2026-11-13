from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.businesses.mixins import BusinessRequiredMixin

from .models import AnalysisTemplate
from .services import GeminiUnavailableError, is_ai_enabled, run_analysis


class AnalysisListView(BusinessRequiredMixin, TemplateView):
    """
    Tela principal do Assistente IA.

    Exibe os cartões das análises pré-programadas ativas.
    O usuário clica em um botão e a análise é gerada naquele momento.
    """

    template_name = 'ai_assistant/analysis_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ai_enabled'] = is_ai_enabled()
        context['templates'] = AnalysisTemplate.objects.filter(is_active=True).order_by(
            'sort_order', 'name'
        )
        return context


class RunAnalysisView(BusinessRequiredMixin, View):
    """
    Executa uma análise pré-programada e redireciona para a tela de resultado.
    """

    def post(self, request, analysis_type):
        from django.db import close_old_connections

        # Garante conexão fresca antes de fazer as queries de contexto,
        # pois o NeonDB fecha conexões ociosas rapidamente.
        close_old_connections()

        template = get_object_or_404(
            AnalysisTemplate, analysis_type=analysis_type, is_active=True
        )
        try:
            result = run_analysis(self.business, request.user, template)
        except GeminiUnavailableError as exc:
            messages.warning(request, str(exc))
            return redirect('ai_assistant:analysis_list')

        request.session[f'ai_result_{analysis_type}'] = result
        return redirect(
            reverse('ai_assistant:analysis_result', kwargs={'analysis_type': analysis_type})
        )


class AnalysisResultView(BusinessRequiredMixin, TemplateView):
    """Exibe o resultado de uma análise específica."""

    template_name = 'ai_assistant/analysis_result.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        analysis_type = self.kwargs['analysis_type']
        template = get_object_or_404(
            AnalysisTemplate, analysis_type=analysis_type, is_active=True
        )
        result = self.request.session.pop(f'ai_result_{analysis_type}', None)
        context['template'] = template
        context['result'] = result
        context['ai_enabled'] = is_ai_enabled()
        return context
