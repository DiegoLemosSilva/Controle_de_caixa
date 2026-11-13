"""
Configurações do projeto Controle de Caixa.

Sistema de controle financeiro empresarial (MVP) construído com Django,
Django Templates, Bootstrap 5 e PostgreSQL.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega variáveis de ambiente do arquivo .env (não versionado).
load_dotenv(BASE_DIR / '.env')


def _env_str(name, default=''):
    """Lê uma variável de ambiente removendo aspas inseridas manualmente no .env."""
    value = os.environ.get(name, default)
    if value is None:
        return default
    return value.strip().strip("'\"")


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    # Remove aspas inseridas manualmente no .env (ex: GEMINI_ENABLED='True')
    return value.strip().strip("'\"").lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=''):
    value = os.environ.get(name, default)
    return [item.strip().strip("'\"") for item in value.split(',') if item.strip()]


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-dev-only-change-in-production',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool('DJANGO_DEBUG', default=True)

ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

if not DEBUG and (not SECRET_KEY or SECRET_KEY == 'django-insecure-dev-only-change-in-production'):
    raise ValueError('Configure DJANGO_SECRET_KEY com uma chave segura em produção.')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Aplicativos do domínio (ordem reflete dependências entre módulos).
    'apps.core',
    'apps.businesses',
    'apps.customers',
    'apps.products',
    'apps.sales',
    'apps.receivables',
    'apps.payables',
    'apps.cash',
    'apps.planning',
    'apps.ai_assistant',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.businesses.context_processors.active_business',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

import dj_database_url

database_url = os.environ.get('DATABASE_URL', '').strip()
if not database_url:
    raise ValueError('DATABASE_URL é obrigatória para conectar ao PostgreSQL.')
DATABASES = {'default': dj_database_url.parse(database_url, conn_max_age=0)}
# Verifica a saúde da conexão antes de reutilizá-la — garante que
# conexões ociosas (ex.: NeonDB serverless) sejam descartadas ao invés
# de lançar "SSL connection has been closed unexpectedly".
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ValueError('DATABASE_URL deve apontar para um banco PostgreSQL.')


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Autenticação
# https://docs.djangoproject.com/en/5.2/topics/auth/default/

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'cash:dashboard'
LOGOUT_REDIRECT_URL = 'login'


# Segurança adicional para produção (controlada via variáveis de ambiente).
# Em desenvolvimento (DEBUG=True) esses valores permanecem desabilitados.

CSRF_COOKIE_SECURE = _env_bool('DJANGO_SECURE_COOKIES', default=not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('DJANGO_SECURE_COOKIES', default=not DEBUG)
SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT', default=False)
# Ative apenas atrás de um proxy confiável que defina X-Forwarded-Proto.
if _env_bool('DJANGO_TRUST_PROXY_HTTPS', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '3600'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# Integração com a API do Google Gemini.
# A chave nunca deve ser versionada nem exposta ao navegador.

GEMINI_API_KEY = _env_str('GEMINI_API_KEY', '')
GEMINI_ENABLED = _env_bool('GEMINI_ENABLED', default=bool(GEMINI_API_KEY))
GEMINI_MODEL = _env_str('GEMINI_MODEL', 'gemini-2.5-flash')
GEMINI_TIMEOUT_SECONDS = int(_env_str('GEMINI_TIMEOUT_SECONDS', '15'))


# Performance da suíte de testes
# ---------------------------------------------------------------------------
# O Django usa PBKDF2 por padrão para hashear senhas (centenas de ms por
# hash, intencionalmente lento para resistir a ataques de força bruta em
# produção). A suíte de testes cria dezenas de usuários via
# `User.objects.create_user(...)` em `setUp()`, pagando esse custo a cada
# teste — isso não traz nenhum benefício de segurança em um banco de teste
# descartável, e é a causa principal da lentidão da suíte completa.
#
# MD5PasswordHasher é ~100x mais rápido e é usado SOMENTE quando `test` é
# o comando do manage.py (detectado via sys.argv), nunca em produção ou
# durante o uso normal do sistema.
if 'test' in sys.argv or 'pytest' in sys.modules:
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]
