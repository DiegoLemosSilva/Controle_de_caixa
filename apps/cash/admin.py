from django.contrib import admin

from .models import CashCountAdjustment, CashSession, CashSessionEvent


@admin.register(CashCountAdjustment)
class CashCountAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        'business', 'date', 'payment_method', 'expected_amount',
        'counted_amount', 'difference', 'created_by', 'created_at',
    )
    list_filter = ('business', 'payment_method', 'date')
    readonly_fields = ('created_at', 'updated_at')


class CashSessionEventInline(admin.TabularInline):
    model = CashSessionEvent
    extra = 0


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = (
        'business', 'date', 'status', 'opening_amount', 'opened_at', 'closed_at',
    )
    list_filter = ('business', 'status')
    inlines = [CashSessionEventInline]
