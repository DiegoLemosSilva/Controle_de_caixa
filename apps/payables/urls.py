from django.urls import path

from . import views

app_name = 'payables'

urlpatterns = [
    path('', views.PayableListView.as_view(), name='payable_list'),
    path('nova/', views.PayableCreateView.as_view(), name='payable_create'),
    path('<int:pk>/', views.PayableDetailView.as_view(), name='payable_detail'),
    path('<int:pk>/editar/', views.PayableUpdateView.as_view(), name='payable_update'),
    path('<int:pk>/pagar/', views.PayableMarkAsPaidView.as_view(), name='payable_mark_paid'),
    path('<int:pk>/reabrir/', views.PayableReopenView.as_view(), name='payable_reopen'),
    path('series/<int:pk>/', views.PayableSeriesDetailView.as_view(), name='payable_series_detail'),
    path('series/<int:pk>/editar/', views.PayableSeriesUpdateView.as_view(), name='payable_series_update'),
    path('series/<int:pk>/cancelar/', views.PayableSeriesCancelView.as_view(), name='payable_series_cancel'),
]
