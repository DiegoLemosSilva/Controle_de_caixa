"""Testes da configuração do banco de dados (PostgreSQL e SQLite) sem conexão externa."""

import os
import subprocess
import sys
from django.test import SimpleTestCase


class DatabaseConfigurationTests(SimpleTestCase):
    def run_settings(self, database_url, gemini='False', admin_url='', app_file=''):
        env = os.environ.copy()
        env['DATABASE_URL'] = database_url
        env['DATABASE_ADMIN_URL'] = admin_url
        env['GEMINI_ENABLED'] = gemini
        env['DJANGO_APP_DATABASE_URL_FILE'] = app_file
        return subprocess.run(
            [
                sys.executable, '-c',
                'from config.settings import DATABASES, MIDDLEWARE; '
                'db = DATABASES["default"]; '
                'print(db["ENGINE"]); '
                'print(db.get("USER", "")); '
                'print(db.get("OPTIONS", {})); '
                'print(MIDDLEWARE)',
            ],
            env=env, capture_output=True, text=True, timeout=30,
        )

    def test_postgres_url_preserves_tls_options(self):
        result = self.run_settings(
            'postgresql://user:password@example.invalid/db'
            '?sslmode=require&channel_binding=require',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('django.db.backends.postgresql', result.stdout)
        self.assertIn("'sslmode': 'require'", result.stdout)
        self.assertIn("'channel_binding': 'require'", result.stdout)

    def test_application_url_takes_precedence_over_admin_and_legacy_file(self):
        result = self.run_settings(
            'postgresql://app_user:pass@example.invalid/db',
            admin_url='postgresql://admin_user:pass@example.invalid/db',
            app_file='arquivo-inexistente.env',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('app_user', result.stdout)
        self.assertNotIn('admin_user', result.stdout)

    def test_missing_application_url_does_not_fallback_to_admin(self):
        result = self.run_settings(
            '', admin_url='postgresql://admin_user:pass@example.invalid/db',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DATABASE_URL é obrigatória', result.stderr)

    def test_postgres_requires_url(self):
        result = self.run_settings('')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DATABASE_URL é obrigatória', result.stderr)

    def test_non_postgres_non_sqlite_url_is_rejected(self):
        result = self.run_settings('mysql://user:pass@example.invalid/db')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DATABASE_URL deve apontar para um banco PostgreSQL', result.stderr)

    def test_gemini_can_be_enabled(self):
        result = self.run_settings(
            'postgresql://user:password@example.invalid/db', gemini='True',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sqlite_url_is_accepted_for_development(self):
        result = self.run_settings('sqlite:///db-teste-config.sqlite3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('django.db.backends.sqlite3', result.stdout)

    def test_sqlite_memory_url_is_accepted(self):
        result = self.run_settings('sqlite://:memory:')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('django.db.backends.sqlite3', result.stdout)
