from django.contrib import admin

from .models import Business, BusinessOwner


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'document', 'phone', 'is_active', 'created_at')
    search_fields = ('name', 'document')
    list_filter = ('is_active',)


@admin.register(BusinessOwner)
class BusinessOwnerAdmin(admin.ModelAdmin):
    list_display = ('user', 'business', 'created_at')
    search_fields = ('user__username', 'business__name')
    autocomplete_fields = ('user', 'business')
