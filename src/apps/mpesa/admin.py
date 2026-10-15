from django.contrib import admin
from .models import MpesaConfig, MpesaTransaction


@admin.register(MpesaConfig)
class MpesaConfigAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'branch', 'shortcode', 'environment',
        'shortcode_type', 'is_active', 'updated_at',
    )
    list_filter = ('environment', 'shortcode_type', 'is_active', 'company')
    search_fields = ('company__name', 'shortcode', 'label')


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'mpesa_code', 'phone', 'amount',
        'status', 'created_at',
    )
    list_filter = ('status', 'company')
    search_fields = ('mpesa_code', 'checkout_request_id', 'phone')
    readonly_fields = ('raw_callback', 'created_at', 'updated_at')