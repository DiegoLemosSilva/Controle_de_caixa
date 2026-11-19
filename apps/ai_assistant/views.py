from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.businesses.mixins import BusinessRequiredMixin

from .models import AnalysisTemplate
from .services import generate_prompt


class AnalysisListView(BusinessRequiredMixin, TemplateView):
    """
    Tela principal do Assistente IA.

    Exibe os cartões das análises pré-programadas ativas. O usuário
    clica em um botão e o sistema monta um prompt com os dados
    financeiros relevantes, para o usuário copiar e colar na IA de
    sua preferência (ChatGPT, Gemini, Copilot etc.).
    """

    template_name = 'ai_assistant/analysis_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['templates'] = AnalysisTemplate.objects.filter(is_active=True).order_by(
            'sort_order', 'name'
        )
        return context


class RunAnalysisView(BusinessRequiredMixin, View):
    """
    Monta o prompt de uma análise pré-programada e redireciona para a
    tela de resultado, onde o usuário pode copiá-lo.

    Não faz nenhuma chamada a serviços externos de IA.
    """

    def post(self, request, analysis_type):
        from django.db import close_old_connections

        # Garante conexão fresca antes de fazer as queries de contexto,
        # pois o NeonDB fecha conexões ociosas rapidamente.
        close_old_connections()

        template = get_object_or_404(
            AnalysisTemplate, analysis_type=analysis_type, is_active=True
        )
        prompt = generate_prompt(self.business, request.user, template)

        request.session[f'ai_result_{analysis_type}'] = prompt
        return redirect(
            reverse('ai_assistant:analysis_result', kwargs={'analysis_type': analysis_type})
        )


class AnalysisResultView(BusinessRequiredMixin, TemplateView):
    """Exibe o prompt gerado para uma análise específica, para cópia manual."""

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
        return context
