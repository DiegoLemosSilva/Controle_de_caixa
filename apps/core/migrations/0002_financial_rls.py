"""Migração histórica: o RLS experimental foi descontinuado.

O nome e as dependências são preservados para bancos já migrados.
Instalações novas não habilitam RLS; bancos existentes são tratados pela
migração seguinte.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_tenant_foreign_keys'),
        ('cash', '0007_unique_open_cash_session'),
        ('products', '0001_initial'),
        ('planning', '0002_alter_financialplan_indicator'),
        ('payables', '0001_initial'),
        ('ai_assistant', '0001_initial'),
    ]

    operations = [migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop)]
