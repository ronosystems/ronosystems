# apps/workshop/admin.py

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    JobMaterial,
    JobNote,
    JobPayment,
    RepairCategory,
    TechnicianPayout,
    TechnicianRate,
    WorkshopCustomer,
    WorkshopJob,
)


# ================================================================
# INLINES
# ================================================================

class JobMaterialInline(admin.TabularInline):
    model = JobMaterial
    extra = 0
    fields = ['name', 'quantity', 'unit_cost', 'total_cost', 'source', 'fund_source']
    readonly_fields = ['total_cost']


class JobPaymentInline(admin.TabularInline):
    model = JobPayment
    extra = 0
    fields = ['amount', 'method', 'reference', 'received_at']


class JobNoteInline(admin.TabularInline):
    model = JobNote
    extra = 0
    fields = ['note', 'is_customer_visible', 'created_by', 'created_at']
    readonly_fields = ['created_at']


# ================================================================
# REPAIR CATEGORY
# ================================================================

@admin.register(RepairCategory)
class RepairCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'slug', 'is_active', 'order']
    list_filter = ['is_active', 'company']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['company', 'order', 'name']


# ================================================================
# CUSTOMER
# ================================================================

@admin.register(WorkshopCustomer)
class WorkshopCustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'company', 'jobs_count', 'created_at']
    list_filter = ['company']
    search_fields = ['name', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at']

    def jobs_count(self, obj):
        return obj.jobs.count()
    jobs_count.short_description = 'Jobs'


# ================================================================
# JOB
# ================================================================

@admin.register(WorkshopJob)
class WorkshopJobAdmin(admin.ModelAdmin):
    list_display = [
        'job_number', 'device_name', 'customer', 'status',
        'repair_category', 'assigned_technician',
        'final_amount', 'amount_paid', 'created_at',
    ]
    list_filter = [
        'status', 'repair_category', 'work_source', 'priority',
        'company', 'branch',
    ]
    search_fields = [
        'job_number', 'device_name', 'device_serial',
        'customer__name', 'customer__phone',
    ]
    readonly_fields = [
        'job_number', 'actual_material_cost', 'amount_paid',
        'created_at', 'updated_at', 'profit_display',
    ]
    inlines = [JobMaterialInline, JobPaymentInline, JobNoteInline]
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    fieldsets = (
        ('Identification', {
            'fields': ('job_number', 'company', 'branch', 'priority', 'status')
        }),
        ('Classification', {
            'fields': ('repair_category', 'work_source')
        }),
        ('Customer', {
            'fields': ('customer',)
        }),
        ('Device', {
            'fields': (
                'device_name', 'device_brand', 'device_model',
                'device_serial', 'device_password', 'device_accessories',
            )
        }),
        ('Problem & Diagnosis', {
            'fields': ('reported_problem', 'diagnosis', 'work_summary')
        }),
        ('Money', {
            'fields': (
                'estimated_material_cost', 'actual_material_cost',
                'quoted_amount', 'final_amount', 'amount_paid',
                'profit_display',
            )
        }),
        ('People', {
            'fields': ('received_by', 'assigned_technician', 'completed_by')
        }),
        ('Dates', {
            'fields': (
                'received_at', 'diagnosed_at', 'approved_at',
                'started_at', 'completed_at', 'delivered_at',
                'expected_delivery',
            )
        }),
        ('Warranty', {
            'fields': ('warranty_days', 'warranty_expires_at')
        }),
        ('Notes', {
            'fields': ('internal_notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def profit_display(self, obj):
        return f"{obj.profit}"
    profit_display.short_description = 'Profit'


# ================================================================
# MATERIAL
# ================================================================

@admin.register(JobMaterial)
class JobMaterialAdmin(admin.ModelAdmin):
    list_display = ['name', 'job', 'quantity', 'unit_cost', 'total_cost', 'source']
    list_filter = ['source', 'fund_source']
    search_fields = ['name', 'job__job_number']
    readonly_fields = ['total_cost', 'created_at']


# ================================================================
# PAYMENT
# ================================================================

@admin.register(JobPayment)
class JobPaymentAdmin(admin.ModelAdmin):
    list_display = ['job', 'amount', 'method', 'reference', 'received_by', 'received_at']
    list_filter = ['method']
    search_fields = ['job__job_number', 'reference']
    date_hierarchy = 'received_at'


# ================================================================
# NOTE
# ================================================================

@admin.register(JobNote)
class JobNoteAdmin(admin.ModelAdmin):
    list_display = ['job', 'short_note', 'is_customer_visible', 'created_by', 'created_at']
    list_filter = ['is_customer_visible']
    search_fields = ['job__job_number', 'note']

    def short_note(self, obj):
        return (obj.note[:60] + '...') if len(obj.note) > 60 else obj.note
    short_note.short_description = 'Note'


# ================================================================
# TECHNICIAN RATE
# ================================================================

@admin.register(TechnicianRate)
class TechnicianRateAdmin(admin.ModelAdmin):
    list_display = [
        'technician', 'repair_category_display', 'percentage',
        'basis', 'is_active', 'company',
    ]
    list_filter = ['is_active', 'basis', 'company']
    search_fields = ['technician__username', 'technician__first_name']

    def repair_category_display(self, obj):
        return obj.repair_category or 'All Categories'
    repair_category_display.short_description = 'Category'


# ================================================================
# TECHNICIAN PAYOUT
# ================================================================

@admin.register(TechnicianPayout)
class TechnicianPayoutAdmin(admin.ModelAdmin):
    list_display = [
        'job', 'technician', 'basis', 'percentage', 'basis_amount',
        'amount', 'status_badge', 'paid_at',
    ]
    list_filter = ['status', 'basis', 'payment_method']
    search_fields = [
        'job__job_number', 'technician__username',
        'technician__first_name', 'technician__last_name',
    ]
    readonly_fields = [
        'job', 'technician', 'basis', 'percentage', 'basis_amount',
        'computed_by', 'created_at', 'updated_at',
    ]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Job & Technician', {
            'fields': ('job', 'technician')
        }),
        ('Computation (auto)', {
            'fields': ('basis', 'percentage', 'basis_amount', 'computed_by')
        }),
        ('Amount (editable)', {
            'fields': ('amount', 'notes')
        }),
        ('Payment', {
            'fields': (
                'status', 'paid_at', 'paid_by',
                'payment_method', 'payment_reference',
            )
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def status_badge(self, obj):
        colors = {
            'pending': '#f0ad4e',   # orange
            'paid': '#5cb85c',      # green
            'cancelled': '#d9534f', # red
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'