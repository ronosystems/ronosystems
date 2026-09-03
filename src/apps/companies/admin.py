from django.contrib import admin
from .models import Company, BusinessType

@admin.register(BusinessType)
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('is_active',)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'business_type', 'plan', 'status', 'is_active', 'created_at')
    list_filter = ('plan', 'status', 'is_active', 'business_type')
    search_fields = ('name', 'email', 'registration_number')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Company Information', {
            'fields': ('name', 'business_type', 'registration_number', 'email', 'phone', 'website')
        }),
        ('Address', {
            'fields': ('address', 'city', 'state', 'country', 'postal_code')
        }),
        ('Subscription', {
            'fields': ('plan', 'subscription_start', 'subscription_end')
        }),
        ('Status', {
            'fields': ('status', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_by', 'logo', 'created_at', 'updated_at')
        }),
    )
