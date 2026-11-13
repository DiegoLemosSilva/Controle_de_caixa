from django.contrib import admin

from .models import Receivable, ReceivablePayment


class ReceivablePaymentInline(admin.TabularInline):
    model = ReceivablePayment
    extra = 0


@admin.register(Receivable)
class ReceivableAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'customer', 'original_amount', 'status')
    list_filter = ('business', 'status')
    inlines = [ReceivablePaymentInline]
