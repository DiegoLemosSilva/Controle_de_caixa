"""
Funções auxiliares para obter a empresa autorizada do usuário autenticado.

Regra de ouro (AGENTS.md seção 5): nunca confiar em um business_id enviado
pelo navegador. A empresa sempre deve ser derivada do usuário autenticado.
"""

def get_business_for_user(user):
    """
    Retorna a Business vinculada ao usuário autenticado, ou None.

    Não lança exceção para permitir que a camada de views decida como
    tratar um usuário sem empresa vinculada.
    """
    if not user or not user.is_authenticated:
        return None

    owner = getattr(user, 'business_owner', None)
    if owner is None:
        return None

    business = owner.business
    if not business.is_active:
        return None

    return business


OPERATOR_GROUP_NAME = 'Operador'


def user_is_operator(user):
    """
    Retorna True se o usuário autenticado pertencer ao grupo "Operador".

    Usuários no grupo Operador têm acesso restrito apenas às
    funcionalidades do Caixa (vendas, comandas e conferência de caixa).
    Superusuários nunca são tratados como Operador, mesmo que estejam
    no grupo, para nunca perderem acesso administrativo.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    return user.groups.filter(name=OPERATOR_GROUP_NAME).exists()
