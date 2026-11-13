from django.contrib import admin

from .models import FinancialPlan


@admin.register(FinancialPlan)
class FinancialPlanAdmin(admin.ModelAdmin):
    list_display = ('business', 'indicator', 'date', 'planned_amount')
    list_filter = ('business', 'indicator')
