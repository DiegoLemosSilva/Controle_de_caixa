"""URLs raiz do projeto Controle de Caixa."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core.views import service_worker

urlpatterns = [
    path('service-worker.js', service_worker, name='service_worker'),
    path('admin/', admin.site.urls),

    path(
        'login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('', include('apps.cash.urls')),
    path('clientes/', include('apps.customers.urls')),
    path('produtos/', include('apps.products.urls')),
    path('vendas/', include('apps.sales.urls')),
    path('contas-a-pagar/', include('apps.payables.urls')),
    path('planejamento/', include('apps.planning.urls')),
    path('assistente/', include('apps.ai_assistant.urls')),
]
