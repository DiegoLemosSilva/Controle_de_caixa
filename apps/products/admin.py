from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'business', 'is_active']
    list_filter = ['business', 'is_active']
    search_fields = ['name']
