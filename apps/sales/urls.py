from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
    path('', views.SaleListView.as_view(), name='sale_list'),
    path('nova/', views.SaleCreateView.as_view(), name='sale_create'),
    path('<int:pk>/cancelar/', views.SaleCancelView.as_view(), name='sale_cancel'),

    path('comandas/nova/', views.ComandaCreateView.as_view(), name='comanda_create'),
    path('comandas/<int:pk>/', views.ComandaDetailView.as_view(), name='comanda_detail'),
    path('comandas/<int:pk>/finalizar/', views.ComandaFinalizeView.as_view(), name='comanda_finalize'),
]
