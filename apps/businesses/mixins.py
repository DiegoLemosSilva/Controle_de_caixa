"""Mixins para proteger views que dependem da empresa autenticada."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .services import get_business_for_user, user_is_operator


class BusinessRequiredMixin(LoginRequiredMixin):
    """
    Garante que o usuário autenticado possua uma empresa vinculada.

    A empresa é sempre obtida a partir do usuário autenticado
    (nunca de parâmetros da URL ou do corpo da requisição), e fica
    disponível em `self.business` para uso nas views e querysets.

    Usuários no grupo "Operador" têm acesso restrito apenas às views
    que explicitamente marcam `operator_allowed = True` (normalmente
    as de Caixa, vendas e comandas). Views sem essa marcação são
    bloqueadas (403) para usuários desse grupo.
    """

    business = None
    operator_allowed = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        if user_is_operator(request.user) and not self.operator_allowed:
            raise PermissionDenied(
                'Usuários do grupo Operador só podem acessar as funcionalidades do Caixa.'
            )

        self.business = get_business_for_user(request.user)
        if self.business is None:
            raise PermissionDenied(
                'Usuário sem empresa vinculada não pode acessar dados financeiros.'
            )
        return super().dispatch(request, *args, **kwargs)
