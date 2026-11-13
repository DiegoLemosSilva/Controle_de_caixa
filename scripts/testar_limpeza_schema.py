"""Teste transacional do rascunho SQL em schema PostgreSQL isolado.

Execute apenas com --confirmar-schema-temporario. Usa DATABASE_URL administrativa;
cria um schema aleatório e faz rollback de toda a transação.
"""
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

if '--confirmar-schema-temporario' not in sys.argv:
    raise SystemExit('Use --confirmar-schema-temporario para autorizar o teste.')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_APP_DATABASE_URL_FILE'] = ''
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.ai_assistant.models import AIInteraction
from apps.businesses.models import Business, BusinessOwner
from apps.cash.models import CashCountAdjustment, CashSession, CashSessionEvent
from apps.customers.models import Customer
from apps.payables.models import Payable, PayablePayment
from apps.planning.models import FinancialPlan
from apps.products.models import Product
from apps.receivables.models import Receivable, ReceivablePayment
from apps.sales.models import Comanda, ComandaItem, ComandaPayment, Sale, SalePayment

schema = 'teste_limpeza_' + uuid.uuid4().hex
script = (ROOT / 'sql' / 'limpeza_empresa.sql').read_text(encoding='utf-8')

with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute('CREATE SCHEMA ' + connection.ops.quote_name(schema))
        cursor.execute(
            'SET LOCAL search_path TO ' + connection.ops.quote_name(schema) + ', pg_catalog'
        )
        cursor.execute('SELECT current_schema()')
        if cursor.fetchone()[0] != schema:
            raise RuntimeError('Schema isolado não está ativo.')

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())

    with connection.cursor() as cursor:
        cursor.execute('SELECT current_schema()')
        if cursor.fetchone()[0] != schema:
            raise RuntimeError('A migração alterou o schema de teste.')
        cursor.execute(script)

    User = get_user_model()
    user_a = User.objects.create_user(username='limpeza_a')
    user_b = User.objects.create_user(username='limpeza_b')
    business_a = Business.objects.create(name='Empresa fictícia A')
    business_b = Business.objects.create(name='Empresa fictícia B')
    BusinessOwner.objects.create(user=user_a, business=business_a)
    BusinessOwner.objects.create(user=user_b, business=business_b)
    customer_a = Customer.objects.create(business=business_a, name='Cliente A')
    customer_b = Customer.objects.create(business=business_b, name='Cliente B')
    sale_a = Sale.objects.create(
        business=business_a, customer=customer_a, created_by=user_a,
        total_amount=Decimal('10.00'), sold_at=timezone.now(),
    )
    receivable = Receivable.objects.create(
        business=business_a, customer=customer_a, sale=sale_a,
        original_amount=Decimal('5.00'),
    )
    now = timezone.now()
    today = timezone.localdate()
    records = [
        SalePayment.objects.create(sale=sale_a, method='pix', amount=Decimal('5'), received_at=now),
        ReceivablePayment.objects.create(receivable=receivable, method='pix', amount=Decimal('2'), paid_at=now, received_by=user_a),
        Product.objects.create(business=business_a, name='Produto fictício', price=Decimal('10')),
        FinancialPlan.objects.create(business=business_a, indicator='sales', date=today, planned_amount=Decimal('10')),
        AIInteraction.objects.create(business=business_a, user=user_a, prompt='Fictício'),
        CashCountAdjustment.objects.create(business=business_a, date=today, payment_method='pix', expected_amount=Decimal('0'), counted_amount=Decimal('0'), reason='Teste', created_by=user_a),
    ]
    comanda = Comanda.objects.create(business=business_a, customer=customer_a, sale=sale_a, opened_by=user_a)
    records.extend([
        ComandaItem.objects.create(comanda=comanda, description='Fictício', quantity=1, unit_price=Decimal('10')),
        ComandaPayment.objects.create(comanda=comanda, method='pix', amount=Decimal('10'), received_by=user_a),
    ])
    payable = Payable.objects.create(business=business_a, description='Fictício', original_amount=Decimal('10'), due_date=today, created_by=user_a)
    records.append(PayablePayment.objects.create(payable=payable, amount=Decimal('5'), method='pix', paid_at=now, paid_by=user_a))
    cash_session = CashSession.objects.create(business=business_a, date=today, opening_amount=Decimal('0'), opened_at=now, opened_by=user_a)
    records.append(CashSessionEvent.objects.create(session=cash_session, event_type='opened', performed_by=user_a))
    group = Group.objects.create(name='Grupo fictício')
    user_a.groups.add(group)
    session_a = SessionStore()
    session_a['_auth_user_id'] = str(user_a.pk)
    session_a['dados_empresa'] = 'fictícios'
    session_a.save()
    session_b = SessionStore()
    session_b['_auth_user_id'] = str(user_b.pk)
    session_b.save()
    sale_b = Sale.objects.create(
        business=business_b, customer=customer_b, created_by=user_a,
        total_amount=Decimal('10.00'), sold_at=timezone.now(),
    )
    content_type = ContentType.objects.create(app_label='businesses', model='business')
    LogEntry.objects.create(
        user=user_b, content_type=content_type, object_id=str(business_a.pk),
        object_repr='Empresa fictícia A', action_flag=1,
    )
    with connection.cursor() as cursor:
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        cursor.execute(
            "SELECT rolname FROM pg_roles WHERE rolname LIKE 'caixa_app_%' "
            "AND pg_has_role(current_user, oid, 'SET')"
        )
        roles = cursor.fetchall()
        if len(roles) == 1:
            role = connection.ops.quote_name(roles[0][0])
            cursor.execute('GRANT USAGE ON SCHEMA ' + connection.ops.quote_name(schema) + ' TO ' + role)
            cursor.execute('GRANT SELECT, DELETE ON businesses_business TO ' + role)
        else:
            role = None

    if role is None:
        print('PENDENTE: teste de papel restrito não executado; SET ROLE indisponível.')
    else:
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET LOCAL ROLE ' + role)
                    cursor.execute('DELETE FROM businesses_business WHERE id = %s', [business_a.pk])
        except DatabaseError as exc:
            if 'A limpeza requer papel administrativo' not in str(exc):
                raise
            print('OK: papel restrito não pode executar a limpeza.')
        else:
            raise AssertionError('O papel restrito não deveria executar a limpeza.')
        assert Business.objects.filter(pk=business_a.pk).exists()

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM customers_customer WHERE id = %s', [customer_a.pk])
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
    except IntegrityError:
        print('OK: exclusão isolada de cliente com venda foi bloqueada.')
    else:
        raise AssertionError('A exclusão isolada do cliente deveria ser bloqueada.')

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    'DELETE FROM businesses_business WHERE id = %s', [business_a.pk]
                )
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
    except IntegrityError:
        print('OK: referência de outra empresa bloqueou e reverteu a exclusão.')
    else:
        raise AssertionError('Referência cruzada não bloqueou a exclusão.')

    assert Business.objects.filter(pk=business_a.pk).exists()
    assert User.objects.filter(pk=user_a.pk).exists()
    assert Receivable.objects.filter(sale=sale_a).exists()

    Sale.objects.filter(pk=sale_b.pk).update(created_by=user_b)
    customer_type = ContentType.objects.create(app_label='customers', model='customer')
    own_orphan_log = LogEntry.objects.create(
        user=user_a, content_type=customer_type, object_id='999999998',
        object_repr='Cliente fictício removido', action_flag=3,
    )
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM businesses_business WHERE id = %s', [business_a.pk])
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
    except IntegrityError:
        print('OK: log sem objeto associado ao usuário bloqueou a exclusão.')
    else:
        raise AssertionError('O log associado ao usuário deveria bloquear a exclusão.')
    assert Business.objects.filter(pk=business_a.pk).exists()
    assert User.objects.filter(pk=user_a.pk).exists()
    assert LogEntry.objects.filter(pk=own_orphan_log.pk).exists()
    own_orphan_log.delete()

    orphan_log = LogEntry.objects.create(
        user=user_b, content_type=customer_type, object_id='999999999',
        object_repr='Cliente fictício removido', action_flag=3,
    )
    external_log = LogEntry.objects.create(
        user=user_a, content_type=content_type, object_id=str(business_b.pk),
        object_repr='Empresa fictícia B', action_flag=1,
    )
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM businesses_business WHERE id = %s', [business_a.pk])
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
    except IntegrityError:
        print('OK: log de outra empresa bloqueou a exclusão e foi preservado.')
    else:
        raise AssertionError('O log externo deveria bloquear a exclusão.')
    assert Business.objects.filter(pk=business_a.pk).exists()
    assert LogEntry.objects.filter(pk=external_log.pk).exists()
    external_log.delete()

    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM businesses_business WHERE id = %s', [business_a.pk])
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    assert not Business.objects.filter(pk=business_a.pk).exists()
    assert not User.objects.filter(pk=user_a.pk).exists()
    assert not Customer.objects.filter(pk=customer_a.pk).exists()
    assert not Sale.objects.filter(pk=sale_a.pk).exists()
    assert not Receivable.objects.filter(sale_id=sale_a.pk).exists()
    for record in records + [comanda, payable, cash_session]:
        assert not type(record).objects.filter(pk=record.pk).exists(), type(record).__name__
    assert Group.objects.filter(pk=group.pk).exists()
    assert not LogEntry.objects.filter(content_type=content_type, object_id=str(business_a.pk)).exists()
    assert Business.objects.filter(pk=business_b.pk).exists()
    assert User.objects.filter(pk=user_b.pk).exists()
    assert Customer.objects.filter(pk=customer_b.pk).exists()
    assert Sale.objects.filter(pk=sale_b.pk).exists()
    assert Session.objects.filter(session_key=session_a.session_key).exists()
    assert Session.objects.filter(session_key=session_b.session_key).exists()
    assert LogEntry.objects.filter(pk=orphan_log.pk).exists()
    print('OK: log sem objeto de outro usuário foi preservado.')
    print('LIMITAÇÃO: a sessão serializada de A permanece após a exclusão.')
    print('OK: exclusão dos dados de A e preservação de B nos modelos testados.')
    transaction.set_rollback(True)

print('Transação revertida; schema temporário não foi mantido.')
