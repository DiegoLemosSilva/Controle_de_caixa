from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.businesses.models import Business, BusinessOwner

from .models import AIInteraction, AnalysisTemplate
from .services import ask

User = get_user_model()


class AIAssistantFailureHandlingTests(TestCase):
    """
    Garante que falhas da API Gemini sejam tratadas sem interromper o
    funcionamento financeiro do sistema (AGENTS.md seção 14).
    """

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='operador', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)

    @patch('apps.ai_assistant.services.settings')
    def test_ask_raises_when_disabled(self, mock_settings):
        mock_settings.GEMINI_ENABLED = False
        mock_settings.GEMINI_API_KEY = ''

        from .services import GeminiUnavailableError

        with self.assertRaises(GeminiUnavailableError):
            ask(self.business, self.user, 'Pergunta de teste')

    @patch('django.db.close_old_connections')
    @patch('apps.ai_assistant.services._call_gemini', return_value='Resposta fictícia')
    @patch('apps.ai_assistant.services.is_ai_enabled', return_value=True)
    def test_ask_preserves_active_transaction(self, _mock_enabled, _mock_call, mock_close):
        answer = ask(self.business, self.user, 'Pergunta de teste')
        self.assertEqual(answer, 'Resposta fictícia')
        mock_close.assert_not_called()
        self.assertTrue(AIInteraction.objects.filter(business=self.business, success=True).exists())

    @patch('apps.ai_assistant.services._call_gemini')
    @patch('apps.ai_assistant.services.is_ai_enabled', return_value=True)
    def test_api_failure_is_logged_and_does_not_raise(self, _mock_enabled, mock_call):
        mock_call.side_effect = Exception('Timeout simulado da API')

        answer = ask(self.business, self.user, 'Pergunta de teste')

        self.assertIn('Não foi possível obter uma resposta', answer)

        interaction = AIInteraction.objects.get(business=self.business)
        self.assertFalse(interaction.success)
        self.assertIn('Timeout simulado', interaction.error_message)


class AnalysisTemplateSeededTests(TestCase):
    """
    Garante que as análises iniciais foram criadas pela migração de dados
    e que o admin pode gerenciá-las.
    """

    def test_all_initial_templates_exist(self):
        expected = [
            AnalysisTemplate.TYPE_MONTHLY_SUMMARY,
            AnalysisTemplate.TYPE_MONTH_COMPARISON,
            AnalysisTemplate.TYPE_EXPENSES_INCREASE,
            AnalysisTemplate.TYPE_PLAN_VS_ACTUAL,
            AnalysisTemplate.TYPE_ALERTS,
            AnalysisTemplate.TYPE_WEEKDAY_SUGGESTION,
        ]
        for analysis_type in expected:
            self.assertTrue(
                AnalysisTemplate.objects.filter(analysis_type=analysis_type).exists(),
                f'Template {analysis_type} não encontrado.',
            )

    def test_all_initial_templates_are_active_by_default(self):
        self.assertEqual(
            AnalysisTemplate.objects.filter(is_active=True).count(),
            6,
        )


class AnalysisListViewTests(TestCase):
    """Garante que a tela do Assistente IA exibe as análises disponíveis."""

    def setUp(self):
        self.business = Business.objects.create(name='Empresa Teste')
        self.user = User.objects.create_user(username='gerente', password='senha12345')
        BusinessOwner.objects.create(user=self.user, business=self.business)
        self.client = Client()
        self.client.login(username='gerente', password='senha12345')

    def test_analysis_list_view_loads(self):
        response = self.client.get(reverse('ai_assistant:analysis_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('templates', response.context)

    def test_all_active_templates_shown(self):
        response = self.client.get(reverse('ai_assistant:analysis_list'))
        self.assertEqual(
            response.context['templates'].count(),
            AnalysisTemplate.objects.filter(is_active=True).count(),
        )

    def test_inactive_template_not_shown(self):
        tpl = AnalysisTemplate.objects.first()
        tpl.is_active = False
        tpl.save()

        response = self.client.get(reverse('ai_assistant:analysis_list'))
        for t in response.context['templates']:
            self.assertNotEqual(t.analysis_type, tpl.analysis_type)

        tpl.is_active = True
        tpl.save()
