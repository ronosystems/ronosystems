from django.contrib import admin
from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'setting_type', 'category', 'updated_at')
    list_filter = ('category', 'setting_type')
    search_fields = ('key', 'value', 'label')
    ordering = ('category', 'order', 'key')