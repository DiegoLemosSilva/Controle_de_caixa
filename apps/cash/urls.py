from django.urls import path

from . import views

app_name = 'cash'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('abrir/', views.OpenCashSessionView.as_view(), name='open_session'),
    path('conferencia/', views.CashCountView.as_view(), name='cash_count'),
    path('conferencia/fechar/', views.CloseDayView.as_view(), name='close_day'),
    path('conferencia/reabrir/', views.ReopenDayView.as_view(), name='reopen_day'),
    path(
        'conferencia/<str:payment_method>/',
        views.CashCountDetailView.as_view(),
        name='cash_count_detail',
    ),
]
