from django.urls import path

from . import views

app_name = 'planning'

urlpatterns = [
    path('', views.PlanDashboardView.as_view(), name='plan_dashboard'),
    path('aplicar/', views.ApplyWeekdayValuesView.as_view(), name='apply_weekday_values'),
    path('copiar-mes-anterior/', views.CopyPreviousMonthView.as_view(), name='copy_previous_month'),
    path('editar-dia/', views.SetDailyValueView.as_view(), name='set_daily_value'),
]
