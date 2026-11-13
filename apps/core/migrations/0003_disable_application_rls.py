"""Desativa o RLS experimental nas tabelas dos aplicativos do projeto.

As políticas permanecem registradas, porém inativas. Esta migração não altera
linhas financeiras nem afeta tabelas de outros aplicativos no mesmo schema.
O isolamento passa a depender das verificações da aplicação.
"""

from django.db import migrations


APPLICATION_PREFIXES = (
    'ai_assistant', 'businesses', 'cash', 'core', 'customers', 'payables',
    'planning', 'products', 'receivables', 'sales',
)


def disable_application_rls(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    # O namespace vem da conexão ativa e os nomes de tabelas vêm do catálogo,
    # não de parâmetros fornecidos pelo usuário.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT n.nspname, c.relname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relkind IN ('r', 'p')
              AND (c.relrowsecurity OR c.relforcerowsecurity)
              AND EXISTS (
                  SELECT 1 FROM unnest(%s::text[]) AS prefix
                  WHERE left(c.relname, length(prefix) + 1) = prefix || '_'
              )
            ORDER BY n.nspname, c.relname
            """,
            [list(APPLICATION_PREFIXES)],
        )
        tables = cursor.fetchall()

    quote = schema_editor.quote_name
    for schema, table in tables:
        qualified = f'{quote(schema)}.{quote(table)}'
        schema_editor.execute(f'ALTER TABLE {qualified} NO FORCE ROW LEVEL SECURITY')
        schema_editor.execute(f'ALTER TABLE {qualified} DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_financial_rls'),
    ]

    # Não reativa políticas automaticamente ao reverter: seu estado anterior
    # pode variar entre bancos e exigiria uma revisão explícita.
    operations = [migrations.RunPython(disable_application_rls)]
