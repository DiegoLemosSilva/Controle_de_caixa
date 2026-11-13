"""Instala o gatilho de limpeza exclusivamente no banco de desenvolvimento."""
import os
import sys
from pathlib import Path

if '--confirmar-desenvolvimento' not in sys.argv:
    raise SystemExit('Use --confirmar-desenvolvimento para instalar.')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_APP_DATABASE_URL_FILE'] = ''
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.db import connection, transaction

script = (ROOT / 'sql' / 'limpeza_empresa.sql').read_text(encoding='utf-8')

with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), current_user')
        if cursor.fetchone() != ('neondb', 'neondb_owner'):
            raise RuntimeError('Destino inesperado; instalação cancelada.')
        cursor.execute('SET LOCAL search_path TO public, pg_catalog')
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = %s AND p.proname = %s",
            ['public', 'limpeza_empresa_antes_delete'],
        )
        if cursor.fetchone()[0]:
            raise RuntimeError('Função existente; instalação cancelada.')
        cursor.execute(
            "SELECT count(*) FROM pg_catalog.pg_trigger "
            "WHERE tgrelid = %s::regclass AND tgname = %s",
            ['public.businesses_business', 'limpeza_empresa_antes_delete'],
        )
        if cursor.fetchone()[0]:
            raise RuntimeError('Gatilho existente; instalação cancelada.')
        cursor.execute(script)
        cursor.execute(
            "SELECT tgenabled FROM pg_catalog.pg_trigger "
            "WHERE tgrelid = %s::regclass AND tgname = %s AND NOT tgisinternal",
            ['public.businesses_business', 'limpeza_empresa_antes_delete'],
        )
        if cursor.fetchone() != ('O',):
            raise RuntimeError('Gatilho não está habilitado; instalação revertida.')

print('Função e gatilho instalados no banco de desenvolvimento; nenhum DELETE executado.')
