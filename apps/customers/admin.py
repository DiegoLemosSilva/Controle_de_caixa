from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'phone', 'is_active', 'created_at')
    list_filter = ('business', 'is_active')
    search_fields = ('name', 'phone')
