from django.contrib import admin

from .models import AIInteraction, AnalysisTemplate


@admin.register(AnalysisTemplate)
class AnalysisTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'analysis_type', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active',)
    ordering = ('sort_order', 'name')
    fields = ('analysis_type', 'name', 'description', 'prompt_template', 'is_active', 'sort_order')
    readonly_fields = ('analysis_type',)


@admin.register(AIInteraction)
class AIInteractionAdmin(admin.ModelAdmin):
    list_display = ('business', 'user', 'analysis_type', 'success', 'created_at')
    list_filter = ('business', 'analysis_type', 'success')
    readonly_fields = ('prompt', 'response', 'error_message')
