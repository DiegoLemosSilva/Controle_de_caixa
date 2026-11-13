"""Context processor que expõe a empresa ativa para os templates."""

from .services import get_business_for_user, user_is_operator


def active_business(request):
    """
    Adiciona ao contexto de todos os templates:
    - `active_business`: a empresa vinculada ao usuário autenticado.
    - `is_operator`: True se o usuário pertencer ao grupo "Operador",
      usado para ocultar links de navegação que ele não pode acessar.
    - `open_cash_session`: a sessão de caixa atualmente aberta da
      empresa (ou None), usada para exibir no menu em qual dia o
      caixa está aberto, independentemente da tela/data que o usuário
      esteja visualizando no momento (ver AGENTS.md seção 13).

    Importa `get_open_session` localmente (lazy import) para evitar
    dependência circular entre os apps `businesses` e `cash`.
    """
    user = getattr(request, 'user', None)
    business = get_business_for_user(user) if user else None

    open_session = None
    if business is not None:
        from apps.cash.services import get_open_session
        open_session = get_open_session(business)

    return {
        'active_business': business,
        'is_operator': user_is_operator(user) if user else False,
        'open_cash_session': open_session,
    }
