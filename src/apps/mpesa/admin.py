from django.contrib import admin

from .models import MpesaConfig, MpesaTransaction


@admin.register(MpesaConfig)
class MpesaConfigAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'branch', 'provider',
        'shortcode', 'kopokopo_till_number',
        'environment', 'shortcode_type',
        'is_active', 'updated_at',
    )
    list_filter = (
        'provider', 'environment', 'shortcode_type',
        'is_active', 'company',
    )
    search_fields = (
        'company__name', 'label',
        'shortcode', 'kopokopo_till_number',
    )
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': (
                'provider', 'company', 'branch', 'label',
                'is_active', 'environment',
            ),
        }),
        ('Daraja', {
            'classes': ('collapse',),
            'fields': (
                'consumer_key', 'consumer_secret',
                'shortcode', 'passkey',
                'shortcode_type', 'account_reference',
            ),
        }),
        ('Kopokopo', {
            'classes': ('collapse',),
            'fields': (
                'kopokopo_client_id', 'kopokopo_client_secret',
                'kopokopo_till_number', 'kopokopo_webhook_secret',
            ),
        }),
        ('Callback', {
            'fields': ('callback_url',),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'company', 'provider',
        'mpesa_code', 'provider_ref',
        'phone', 'amount', 'status', 'created_at',
    )
    list_filter = ('status', 'provider', 'company')
    search_fields = (
        'mpesa_code', 'provider_ref',
        'phone', 'account_reference',
        'merchant_request_id',
    )
    readonly_fields = ('raw_callback', 'created_at', 'updated_at')
    list_select_related = ('company', 'branch', 'mpesa_config')
    date_hierarchy = 'created_at'