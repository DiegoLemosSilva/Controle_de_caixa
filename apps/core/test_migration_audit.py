"""Testes da auditoria parcial antes da migração."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase

from apps.businesses.models import Business, BusinessOwner


class MigrationAuditTests(TransactionTestCase):
    def setUp(self):
        self.business = Business.objects.create(name='Empresa A')
        self.other = Business.objects.create(name='Empresa B')
        self.user = get_user_model().objects.create_user(username='auditoria')
        BusinessOwner.objects.create(user=self.user, business=self.business)

    def audit(self):
        output = StringIO()
        call_command('audit_database_migration', stdout=output, no_color=True)
        return output.getvalue()

    def test_clean_database(self):
        output = self.audit()
        self.assertIn('Nenhuma inconsistência encontrada', output)
        self.assertIn('verificações adicionais', output)

    @patch('apps.core.management.commands.audit_database_migration.count_duplicate_open_sessions')
    def test_duplicate_open_sessions_are_reported(self, count_duplicates):
        count_duplicates.return_value = 1
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('audit_database_migration', stdout=output, no_color=True)
        self.assertIn('Empresas com mais de um caixa aberto: 1', output.getvalue())
        count_duplicates.assert_called_once_with('default')
