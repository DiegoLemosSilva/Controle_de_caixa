"""
Comando de gerenciamento para criar um usuário administrador já
vinculado a uma empresa (Business), evitando criação manual via shell.

Uso:
    python manage.py create_business_user --username dono --password SENHA \
        --business "Nome do Estabelecimento" [--email email@exemplo.com] \
        [--superuser]
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.businesses.models import Business, BusinessOwner

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Cria um usuário vinculado a uma empresa (Business). '
        'Útil para configurar o primeiro acesso de cada estabelecimento.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--business', required=True, help='Nome da empresa')
        parser.add_argument('--email', default='')
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Também concede permissões de superusuário (acesso ao /admin).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        business_name = options['business']
        email = options['email']
        is_superuser = options['superuser']

        if User.objects.filter(username=username).exists():
            raise CommandError(f'Usuário "{username}" já existe.')

        business, created = Business.objects.get_or_create(name=business_name)

        if is_superuser:
            user = User.objects.create_superuser(
                username=username, email=email, password=password
            )
        else:
            user = User.objects.create_user(
                username=username, email=email, password=password
            )

        BusinessOwner.objects.create(user=user, business=business)

        status_empresa = 'criada' if created else 'já existente'
        self.stdout.write(
            self.style.SUCCESS(
                f'Usuário "{username}" criado e vinculado à empresa '
                f'"{business_name}" ({status_empresa}).'
            )
        )
