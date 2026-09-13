# apps/plans/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Plan, Subscription, PlanFeature


# ============================================
# INLINES
# ============================================

class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 1
    fields = ('order', 'name', 'icon', 'is_active', 'description')
    ordering = ('order',)


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0
    fields = ('plan', 'status', 'start_date', 'end_date', 'payment_method', 'payment_reference')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    can_delete = False
    show_change_link = True


# ============================================
# PLAN ADMIN
# ============================================

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        'display_name',
        'name_badge',
        'price_display',
        'billing_cycle',
        'limits_summary',
        'feature_flags_summary',
        'is_active',
        'is_featured',
        'order',
    )
    list_filter = (
        'is_active',
        'is_featured',
        'billing_cycle',
        'name',
        'has_api_access',
        'has_custom_domain',
        'has_mpesa_intergration',
    )
    search_fields = ('name', 'display_name', 'description')
    ordering = ('order', 'price')
    list_editable = ('is_active', 'is_featured', 'order')

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'display_name', 'description')
        }),
        ('Pricing', {
            'fields': ('price', 'currency', 'billing_cycle')
        }),
        ('Limits', {
            'fields': ('max_employees', 'max_companies', 'max_branches', 'max_storage'),
            'description': 'Maximum values per company on this plan.'
        }),
        ('Feature Flags', {
            'fields': (
                'has_api_access',
                'has_advanced_reports',
                'has_custom_branding',
                'has_priority_support',
                'has_bulk_import',
                'has_custom_domain',
                'has_mpesa_intergration',
            ),
            'description': 'Note: field name "has_mpesa_intergration" contains a typo — kept for DB compatibility.'
        }),
        ('Business Type Access', {
            'fields': ('allowed_business_types',),
            'description': 'Leave empty to allow all business types.'
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured', 'order')
        }),
    )

    filter_horizontal = ('allowed_business_types',)
    inlines = [PlanFeatureInline]

    # ---------- Custom columns ----------

    @admin.display(description='Type')
    def name_badge(self, obj):
        colors = {
            'free': '#6c757d',
            'basic': '#17a2b8',
            'standard': '#0d6efd',
            'premium': '#6f42c1',
            'enterprise': '#fd7e14',
        }
        color = colors.get(obj.name, '#333')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:600;">{}</span>',
            color,
            obj.get_name_display(),
        )

    @admin.display(description='Price')
    def price_display(self, obj):
        if obj.price == 0:
            return 'Free'
        return f"{obj.currency} {obj.price}"

    @admin.display(description='Limits')
    def limits_summary(self, obj):
        return f"{obj.max_employees} emp · {obj.max_branches} br · {obj.max_companies} co"

    @admin.display(description='Features')
    def feature_flags_summary(self, obj):
        flags = []
        if obj.has_api_access:
            flags.append('API')
        if obj.has_advanced_reports:
            flags.append('Reports')
        if obj.has_custom_branding:
            flags.append('Branding')
        if obj.has_priority_support:
            flags.append('Support')
        if obj.has_bulk_import:
            flags.append('Bulk')
        if obj.has_custom_domain:
            flags.append('Domain')
        if obj.has_mpesa_intergration:
            flags.append('M-Pesa')
        return ' · '.join(flags) if flags else '—'


# ============================================
# SUBSCRIPTION ADMIN
# ============================================

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'company_link',
        'plan',
        'status_badge',
        'display_state_badge',
        'start_date',
        'end_date',
        'days_remaining_display',
        'payment_method',
        'created_at',
    )
    list_filter = (
        'status',
        'plan',
        'payment_method',
        'created_at',
    )
    search_fields = (
        'company__name',
        'plan__display_name',
        'payment_reference',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    autocomplete_fields = ('company', 'plan')

    readonly_fields = (
        'created_at',
        'updated_at',
        'display_state_display',
        'days_until_expiry_display',
    )

    fieldsets = (
        ('Subscription', {
            'fields': ('company', 'plan', 'status')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date')
        }),
        ('Payment', {
            'fields': ('payment_method', 'payment_reference')
        }),
        ('Computed State', {
            'fields': ('display_state_display', 'days_until_expiry_display'),
            'description': 'Read-only computed fields (from model properties).'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    actions = ['mark_active', 'mark_expired', 'mark_cancelled']

    # ---------- Custom columns ----------

    @admin.display(description='Company', ordering='company__name')
    def company_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:companies_company_change', args=[obj.company_id])
        return format_html('<a href="{}">{}</a>', url, obj.company.name)

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'active': '#28a745',
            'inactive': '#6c757d',
            'expired': '#dc3545',
            'cancelled': '#ffc107',
            'pending': '#fd7e14',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:600;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description='Display State')
    def display_state_badge(self, obj):
        state = obj.display_state
        colors = {
            'active': '#28a745',
            'expiring': '#ffc107',
            'lifetime': '#0d6efd',
            'expired': '#dc3545',
            'pending': '#fd7e14',
            'cancelled': '#6c757d',
            'inactive': '#6c757d',
        }
        color = colors.get(state, '#333')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">{}</span>',
            color,
            state.title(),
        )

    @admin.display(description='Days Left')
    def days_remaining_display(self, obj):
        days = obj.days_until_expiry
        if days is None:
            return '—'
        if days == 0:
            return 'Today'
        if days <= 7:
            return format_html('<strong style="color:#dc3545;">{} d</strong>', days)
        return f"{days} d"

    @admin.display(description='Display state')
    def display_state_display(self, obj):
        return obj.display_state

    @admin.display(description='Days until expiry')
    def days_until_expiry_display(self, obj):
        days = obj.days_until_expiry
        return 'Lifetime' if days is None else f"{days} days"

    # ---------- Bulk actions ----------

    @admin.action(description='Mark selected as Active')
    def mark_active(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f'{updated} subscription(s) marked active.')

    @admin.action(description='Mark selected as Expired')
    def mark_expired(self, request, queryset):
        updated = queryset.update(status='expired')
        self.message_user(request, f'{updated} subscription(s) marked expired.')

    @admin.action(description='Mark selected as Cancelled')
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} subscription(s) marked cancelled.')


# ============================================
# PLAN FEATURE ADMIN
# ============================================

@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ('plan', 'order', 'name', 'icon', 'is_active')
    list_filter = ('plan', 'is_active')
    search_fields = ('name', 'description', 'plan__display_name')
    ordering = ('plan', 'order')
    list_editable = ('order', 'is_active')
    autocomplete_fields = ('plan',)