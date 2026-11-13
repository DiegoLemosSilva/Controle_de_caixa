"""Ensaio concorrente em schema descartável no PostgreSQL configurado.

Cria e confirma um schema de teste e o remove ao final. Se o processo for
interrompido abruptamente, o schema impresso pode exigir remoção manual.
Não executa operações no schema da aplicação.
"""
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import psycopg
from dotenv import dotenv_values

if '--confirmar-schema-temporario' not in sys.argv:
    raise SystemExit('Informe --confirmar-schema-temporario para executar.')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_APP_DATABASE_URL_FILE'] = ''
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.db import DatabaseError, IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.businesses.models import Business
from apps.customers.models import Customer

schema = 'teste_concorrencia_limpeza_' + uuid.uuid4().hex
quoted_schema = connection.ops.quote_name(schema)
created = False


def use_test_schema():
    """Limita todas as consultas à transação e valida o schema."""
    if not connection.in_atomic_block:
        raise RuntimeError('O schema de teste exige transação explícita.')
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL search_path TO ' + quoted_schema + ', pg_catalog')
        cursor.execute('SELECT current_schema()')
        if cursor.fetchone()[0] != schema:
            raise RuntimeError('O schema isolado de teste não está ativo.')


def holder(operation, ready, release):
    try:
        with transaction.atomic():
            use_test_schema()
            operation()
            ready.set()
            if not release.wait(20):
                raise TimeoutError('A operação concorrente não foi liberada.')
            transaction.set_rollback(True)
    finally:
        connections.close_all()


def expect_timeout(operation):
    try:
        with transaction.atomic():
            use_test_schema()
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '2s'")
            operation()
    except DatabaseError as exc:
        if getattr(exc.__cause__, 'sqlstate', None) != '55P03':
            raise
    else:
        raise AssertionError('A operação concorrente deveria aguardar um bloqueio.')


def run_scenario(holding_operation, blocked_operation):
    ready, release = Event(), Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(holder, holding_operation, ready, release)
        try:
            if not ready.wait(20):
                if future.done():
                    future.result()
                raise TimeoutError('A primeira conexão não adquiriu o bloqueio.')
            expect_timeout(blocked_operation)
        finally:
            release.set()
        future.result(timeout=20)


def run_committed_scenario(first_operation, second_operation):
    ready, release, attempted = Event(), Event(), Event()

    def first():
        try:
            with transaction.atomic():
                use_test_schema()
                first_operation()
                ready.set()
                if not release.wait(20):
                    raise TimeoutError('A primeira transação não foi liberada.')
        finally:
            connections.close_all()

    def second():
        try:
            if not ready.wait(20):
                raise TimeoutError('A primeira operação não iniciou.')
            with transaction.atomic():
                use_test_schema()
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '10s'")
                attempted.set()
                second_operation()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first)
        second_future = executor.submit(second)
        try:
            if not attempted.wait(20):
                if first_future.done():
                    first_future.result()
                if second_future.done():
                    second_future.result()
                raise TimeoutError('A segunda operação não iniciou.')
        finally:
            release.set()
        first_future.result(timeout=20)
        return second_future


def delete_business(pk):
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM businesses_business WHERE id = %s', [pk])


def insert_customer(pk, name):
    Customer.objects.create(business_id=pk, name=name)
    with connection.cursor() as cursor:
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')


try:
    if connection.vendor != 'postgresql':
        raise RuntimeError('Este teste exige PostgreSQL.')
    print('Schema temporário:', schema, flush=True)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA ' + quoted_schema)
        use_test_schema()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        use_test_schema()
        with connection.cursor() as cursor:
            cursor.execute((ROOT / 'sql' / 'limpeza_empresa.sql').read_text(encoding='utf-8'))
        business_id = Business.objects.create(name='Empresa fictícia para concorrência').pk
    created = True

    env = dotenv_values(ROOT / '.env')
    credential_file = env.get('DJANGO_APP_DATABASE_URL_FILE')
    if not credential_file:
        raise RuntimeError('Arquivo de credenciais da aplicação não configurado.')
    app_url = dotenv_values(ROOT / credential_file).get('DATABASE_URL')
    if not app_url:
        raise RuntimeError('URL da aplicação não configurada.')
    with psycopg.connect(app_url) as app_connection:
        with app_connection.cursor() as app_cursor:
            app_cursor.execute("SELECT current_user, current_database(), rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            app_role, app_database, is_superuser, bypass_rls = app_cursor.fetchone()
            if is_superuser or bypass_rls:
                raise RuntimeError('A credencial da aplicação deve ser restrita.')
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database()')
                if cursor.fetchone()[0] != app_database:
                    raise RuntimeError('Credenciais apontam para bancos diferentes.')
                quoted_role = connection.ops.quote_name(app_role)
                cursor.execute('GRANT USAGE ON SCHEMA ' + quoted_schema + ' TO ' + quoted_role)
                cursor.execute('GRANT SELECT, DELETE ON ' + quoted_schema + '.businesses_business TO ' + quoted_role)
            app_cursor.execute('SET LOCAL search_path TO ' + quoted_schema + ', pg_catalog')
            app_cursor.execute('SELECT current_schema()')
            if app_cursor.fetchone()[0] != schema:
                raise RuntimeError('O schema de teste não está acessível pela aplicação.')
            try:
                app_cursor.execute('DELETE FROM businesses_business WHERE id = %s', [business_id])
            except psycopg.errors.RaiseException as exc:
                if 'A limpeza requer papel administrativo' not in str(exc):
                    raise
                print('OK: papel da aplicação não pode executar a limpeza.')
            else:
                raise AssertionError('A limpeza deveria ter sido negada ao papel da aplicação.')
            app_connection.rollback()

    run_scenario(
        lambda: delete_business(business_id),
        lambda: insert_customer(business_id, 'Inserção durante exclusão'),
    )
    print('OK: inserção concorrente aguarda a exclusão.')

    run_scenario(
        lambda: insert_customer(business_id, 'Inserção antes da exclusão'),
        lambda: delete_business(business_id),
    )
    print('OK: exclusão concorrente aguarda a inserção.')

    with transaction.atomic():
        use_test_schema()
        if not Business.objects.filter(pk=business_id).exists():
            raise AssertionError('A empresa fictícia deveria permanecer após rollback.')
        if Customer.objects.filter(business_id=business_id).exists():
            raise AssertionError('Os clientes fictícios deveriam ser revertidos.')
    print('OK: os dois cenários foram revertidos.')

    result = run_committed_scenario(
        lambda: insert_customer(business_id, 'Inserção confirmada'),
        lambda: delete_business(business_id),
    )
    result.result()
    with transaction.atomic():
        use_test_schema()
        if Business.objects.filter(pk=business_id).exists():
            raise AssertionError('A empresa deveria ter sido excluída.')
        if Customer.objects.filter(business_id=business_id).exists():
            raise AssertionError('A inserção confirmada deixou cliente órfão.')
        second_business_id = Business.objects.create(name='Empresa fictícia adicional').pk
    print('OK: inserção confirmada antes da exclusão não deixou registros órfãos.')

    result = run_committed_scenario(
        lambda: delete_business(second_business_id),
        lambda: insert_customer(second_business_id, 'Inserção após exclusão'),
    )
    try:
        result.result()
    except IntegrityError:
        print('OK: inserção após exclusão confirmada foi rejeitada.')
    else:
        raise AssertionError('A inserção após a exclusão deveria falhar.')
    with transaction.atomic():
        use_test_schema()
        if Business.objects.filter(pk=second_business_id).exists():
            raise AssertionError('A segunda empresa deveria ter sido excluída.')
        if Customer.objects.filter(business_id=second_business_id).exists():
            raise AssertionError('A inserção concorrente deixou cliente órfão.')
finally:
    connections.close_all()
    if created:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DROP SCHEMA ' + quoted_schema + ' CASCADE')
        connections.close_all()
        print('Schema temporário removido:', schema, flush=True)
