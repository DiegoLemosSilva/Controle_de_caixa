from django.contrib import admin

from .models import Comanda, ComandaItem, Sale, SalePayment


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'total_amount', 'sold_at', 'status', 'customer')
    list_filter = ('business', 'status')
    search_fields = ('description',)
    inlines = [SalePaymentInline]


class ComandaItemInline(admin.TabularInline):
    model = ComandaItem
    extra = 0


@admin.register(Comanda)
class ComandaAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'identifier', 'status', 'opened_at')
    list_filter = ('business', 'status')
    inlines = [ComandaItemInline]
