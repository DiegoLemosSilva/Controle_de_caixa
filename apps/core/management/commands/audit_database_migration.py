"""Auditoria parcial e somente leitura antes da migração de banco."""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, models, transaction
from django.db.models import Count, F
from django.db.models.functions import Length

from apps.cash.models import CashSession
from apps.receivables.models import Receivable
from apps.sales.models import Comanda, ComandaPayment, Sale


def count_duplicate_open_sessions(alias):
    """Conta empresas com sessões abertas duplicadas em bancos legados."""
    return (
        CashSession.objects.using(alias)
        .filter(status=CashSession.STATUS_OPEN)
        .values('business_id')
        .annotate(total=Count('pk'))
        .filter(total__gt=1)
        .count()
    )


class Command(BaseCommand):
    help = 'Audita parcialmente a integridade dos dados antes da migração.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database', default='default', help='Alias do banco a ser auditado.'
        )

    def handle(self, *args, **options):
        alias = options['database']
        connection = connections[alias]
        issues = []

        with transaction.atomic(using=alias):
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')

            def record(label, count):
                self.stdout.write(f'{label}: {count}')
                if count:
                    issues.append(label)

            self.stdout.write(
                'Chaves estrangeiras: verificação específica do banco ainda necessária.'
            )

            duplicate_sessions = count_duplicate_open_sessions(alias)
            record('Empresas com mais de um caixa aberto', duplicate_sessions)

            checks = [
                ('Vendas com cliente de outra empresa', Sale, 'customer__business_id', 'business_id'),
                ('Comandas com cliente de outra empresa', Comanda, 'customer__business_id', 'business_id'),
                ('Comandas com venda de outra empresa', Comanda, 'sale__business_id', 'business_id'),
                ('Pagamentos de comanda com cliente de outra empresa', ComandaPayment, 'customer__business_id', 'comanda__business_id'),
                ('Recebíveis com cliente de outra empresa', Receivable, 'customer__business_id', 'business_id'),
                ('Recebíveis com venda de outra empresa', Receivable, 'sale__business_id', 'business_id'),
            ]
            for label, model, related_business, own_business in checks:
                count = (
                    model.objects.using(alias)
                    .filter(**{f'{related_business}__isnull': False})
                    .exclude(**{related_business: F(own_business)})
                    .count()
                )
                record(label, count)

            for model in apps.get_models():
                if model._meta.proxy or not model._meta.managed:
                    continue
                for field in model._meta.local_fields:
                    if not isinstance(field, models.CharField) or field.max_length is None:
                        continue
                    count = (
                        model._base_manager.using(alias)
                        .annotate(_audit_length=Length(field.name))
                        .filter(_audit_length__gt=field.max_length)
                        .count()
                    )
                    if count:
                        record(f'Texto acima do limite em {model._meta.label}.{field.name}', count)

        self.stdout.write(
            'Auditoria parcial: valores monetários, totais financeiros, datas, '
            'sequências e permissões/RLS exigem verificações adicionais.'
        )
        if issues:
            raise CommandError(f'Auditoria encontrou {len(issues)} categoria(s) de inconsistências.')
        self.stdout.write(self.style.SUCCESS('Nenhuma inconsistência encontrada nas verificações executadas.'))
