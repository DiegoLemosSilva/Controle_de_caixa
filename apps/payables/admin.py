from django.contrib import admin

from .models import Payable, PayablePayment


class PayablePaymentInline(admin.TabularInline):
    model = PayablePayment
    extra = 0


@admin.register(Payable)
class PayableAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'description', 'original_amount', 'due_date', 'status')
    list_filter = ('business', 'status')
    inlines = [PayablePaymentInline]
