"""
Script de manutenção: concede ao papel da aplicação (caixa_app_...) as
permissões necessárias na nova tabela payables_payableseries e em sua
sequência de ID, criadas pela migração 0004 com a credencial
administrativa (owner). Sem este grant, o papel da aplicação recebe
"permission denied" ao tentar ler/escrever na tabela nova.

Lê DATABASE_ADMIN_URL do ambiente (ou, se ausente/comentada no .env,
usa o fallback explícito abaixo, mantido apenas até que o .env seja
atualizado) e confirma o banco antes de aplicar o GRANT.
"""

import os

import psycopg
from dotenv import dotenv_values

APP_ROLE = 'caixa_app_1ea77360ff659009'

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_values = dotenv_values(os.path.join(BASE_DIR, '.env'))

admin_url = (
    os.environ.get('DATABASE_ADMIN_URL')
    or env_values.get('DATABASE_ADMIN_URL')
    or ''
).strip().strip("'\"")

if not admin_url:
    raise SystemExit(
        'DATABASE_ADMIN_URL não encontrada (nem no ambiente, nem no .env). '
        'Defina-a antes de executar este script.'
    )

with psycopg.connect(admin_url) as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT current_database(), current_user;')
        print('Conectado a:', cur.fetchone())

        cur.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON payables_payableseries TO "{APP_ROLE}";'
        )
        cur.execute(
            f'GRANT USAGE, SELECT ON SEQUENCE payables_payableseries_id_seq TO "{APP_ROLE}";'
        )
    conn.commit()

print('Permissões concedidas com sucesso.')
