from django.urls import path

from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('', views.AnalysisListView.as_view(), name='analysis_list'),
    path('executar/<str:analysis_type>/', views.RunAnalysisView.as_view(), name='run_analysis'),
    path('resultado/<str:analysis_type>/', views.AnalysisResultView.as_view(), name='analysis_result'),
]
