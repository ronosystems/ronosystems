from django.contrib import admin
from .models import Company, BusinessType

@admin.register(BusinessType)
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('is_active',)



@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_id', 'custom_domain', 'domain_verified', 'status')
    list_filter = ('status', 'domain_verified', 'business_type')
    search_fields = ('name', 'company_id', 'custom_domain', 'email')
    readonly_fields = ('company_id', 'created_at', 'updated_at')
    fieldsets = (
        ('Identity', {
            'fields': ('company_id', 'name', 'business_type', 'registration_number')
        }),
        ('Address', {
            'fields': ('address', 'city', 'state', 'country', 'postal_code')
        }),
        ('Contact', {
            'fields': ('email', 'phone', 'website')
        }),
        ('Branding', {
            'fields': ('logo', 'favicon', 'primary_color', 'accent_color', 'system_name')
        }),
        ('Custom Domain', {
            'fields': ('custom_domain', 'domain_verified'),
            'description': 'Enter just the hostname, e.g. myshop.co.ke. '
                           'DNS must point to ronosystems.onrender.com first.'
        }),
        ('Subscription', {
            'fields': ('plan', 'subscription_start', 'subscription_end', 'status', 'is_active')
        }),
    )



