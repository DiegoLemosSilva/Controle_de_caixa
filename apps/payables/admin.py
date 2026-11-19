from django.contrib import admin

from .models import Payable, PayablePayment, PayableSeries


class PayablePaymentInline(admin.TabularInline):
    model = PayablePayment
    extra = 0


@admin.register(Payable)
class PayableAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'description', 'original_amount', 'due_date', 'status', 'series')
    list_filter = ('business', 'status')
    inlines = [PayablePaymentInline]


@admin.register(PayableSeries)
class PayableSeriesAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'description', 'kind', 'amount', 'is_active')
    list_filter = ('business', 'kind', 'is_active')
