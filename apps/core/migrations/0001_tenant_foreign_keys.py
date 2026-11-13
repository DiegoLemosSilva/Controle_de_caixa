"""Constraints PostgreSQL para relacionamentos entre registros da mesma empresa."""

from django.db import migrations


PARENT_KEYS = (
    ('customers', 'Customer', 'tenant_customer_business_id_key'),
    ('sales', 'Sale', 'tenant_sale_business_id_key'),
)

RELATIONSHIPS = (
    ('sales', 'Sale', 'customer_id', 'customers', 'Customer', 'tenant_sale_customer_fk'),
    ('sales', 'Comanda', 'customer_id', 'customers', 'Customer', 'tenant_comanda_customer_fk'),
    ('sales', 'Comanda', 'sale_id', 'sales', 'Sale', 'tenant_comanda_sale_fk'),
    ('receivables', 'Receivable', 'customer_id', 'customers', 'Customer', 'tenant_receivable_customer_fk'),
    ('receivables', 'Receivable', 'sale_id', 'sales', 'Sale', 'tenant_receivable_sale_fk'),
)


def install_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    quote = schema_editor.quote_name
    for app_label, model_name, constraint in PARENT_KEYS:
        table = apps.get_model(app_label, model_name)._meta.db_table
        schema_editor.execute(
            f'ALTER TABLE {quote(table)} ADD CONSTRAINT {quote(constraint)} '
            f'UNIQUE ({quote("business_id")}, {quote("id")})'
        )
    for app_label, model_name, column, target_app, target_model, constraint in RELATIONSHIPS:
        table = apps.get_model(app_label, model_name)._meta.db_table
        target = apps.get_model(target_app, target_model)._meta.db_table
        schema_editor.execute(
            f'ALTER TABLE {quote(table)} ADD CONSTRAINT {quote(constraint)} '
            f'FOREIGN KEY ({quote("business_id")}, {quote(column)}) '
            f'REFERENCES {quote(target)} ({quote("business_id")}, {quote("id")}) '
            'DEFERRABLE INITIALLY DEFERRED'
        )


def remove_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    quote = schema_editor.quote_name
    for app_label, model_name, _, _, _, constraint in reversed(RELATIONSHIPS):
        table = apps.get_model(app_label, model_name)._meta.db_table
        schema_editor.execute(f'ALTER TABLE {quote(table)} DROP CONSTRAINT {quote(constraint)}')
    for app_label, model_name, constraint in reversed(PARENT_KEYS):
        table = apps.get_model(app_label, model_name)._meta.db_table
        schema_editor.execute(f'ALTER TABLE {quote(table)} DROP CONSTRAINT {quote(constraint)}')


class Migration(migrations.Migration):
    dependencies = [
        ('customers', '0002_customer_credit_limit'),
        ('sales', '0002_comandapayment'),
        ('receivables', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(install_constraints, remove_constraints),
    ]
