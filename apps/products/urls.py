from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('', views.ProductListView.as_view(), name='product_list'),
    path('novo/', views.ProductCreateView.as_view(), name='product_create'),
    path('<int:pk>/editar/', views.ProductUpdateView.as_view(), name='product_update'),
    path('<int:pk>/alternar/', views.ProductToggleActiveView.as_view(), name='product_toggle_active'),
    path('<int:pk>/excluir/', views.ProductDeleteView.as_view(), name='product_delete'),
]
