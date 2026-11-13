"""Verificações da configuração de implantação sem acessar o banco."""

import os
import subprocess
import sys

from django.test import SimpleTestCase


class DeploymentConfigurationTests(SimpleTestCase):
    def run_config(self, **overrides):
        env = os.environ.copy()
        env.update({
            'DATABASE_URL': 'postgresql://user:pass@example.invalid/test',
            'DJANGO_DEBUG': 'False',
            'DJANGO_SECRET_KEY': 'test-secret-not-for-production',
            'DJANGO_ALLOWED_HOSTS': 'test.onrender.com',
            'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://test.onrender.com',
            'DJANGO_TRUST_PROXY_HTTPS': 'True',
            'DJANGO_SECURE_COOKIES': 'True',
            'DJANGO_SECURE_SSL_REDIRECT': 'True',
            'GEMINI_ENABLED': 'False',
        })
        env.update(overrides)
        code = (
            'from config import settings as s; '
            'print(s.ALLOWED_HOSTS); '
            'print(s.CSRF_TRUSTED_ORIGINS); '
            'print(getattr(s, "SECURE_PROXY_SSL_HEADER", None)); '
            'print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE); '
            'print(s.MIDDLEWARE); '
            'print(s.STORAGES["staticfiles"]["BACKEND"])'
        )
        return subprocess.run(
            [sys.executable, '-c', code], env=env, capture_output=True,
            text=True, timeout=30,
        )

    def test_production_configuration(self):
        result = self.run_config()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('test.onrender.com', result.stdout)
        self.assertIn('https://test.onrender.com', result.stdout)
        self.assertIn('HTTP_X_FORWARDED_PROTO', result.stdout)
        self.assertIn('True True', result.stdout)
        self.assertIn('whitenoise.middleware.WhiteNoiseMiddleware', result.stdout)
        self.assertIn('whitenoise.storage.CompressedStaticFilesStorage', result.stdout)

    def test_default_secret_rejected_in_production(self):
        result = self.run_config(
            DJANGO_SECRET_KEY='django-insecure-dev-only-change-in-production',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr)

    def test_proxy_header_is_opt_in(self):
        result = self.run_config(DJANGO_TRUST_PROXY_HTTPS='False')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\nNone\n', result.stdout)
