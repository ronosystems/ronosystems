from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import F
from .models import (
    # Original models
    Category, Electronic, Phone, Accessory, 
    Sale, SaleItem, Customer,
    # New models
    Branch, Supplier, StockMovement, 
    PurchaseOrder, PurchaseOrderItem,
    Warranty, Repair
)

# ============================================
# REGISTER CONTENTTYPE FOR AUTOCOMPLETE
# ============================================

@admin.register(ContentType)
class ContentTypeAdmin(admin.ModelAdmin):
    list_display = ('app_label', 'model', 'id')
    search_fields = ('app_label', 'model')
    list_filter = ('app_label',)

# ============================================
# INLINE ADMIN CLASSES
# ============================================

class SaleItemInline(GenericTabularInline):
    """Inline for Sale items using GenericForeignKey"""
    model = SaleItem
    extra = 1
    fields = ('content_type', 'object_id', 'item_name', 'quantity', 'unit_price', 'total_price')
    # Removed raw_id_fields and autocomplete_fields as they don't work well with GFK
    # Use select widgets instead (they'll show all available content types)
    classes = ('collapse',)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class PurchaseOrderItemInline(GenericTabularInline):
    """Inline for Purchase Order items"""
    model = PurchaseOrderItem
    extra = 1
    fields = ('content_type', 'object_id', 'product_name', 'quantity_ordered', 'quantity_received', 'unit_price', 'total_price')
    classes = ('collapse',)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class StockMovementInline(GenericTabularInline):
    """Inline for Stock Movements"""
    model = StockMovement
    extra = 0
    fields = ('movement_type', 'quantity', 'previous_quantity', 'new_quantity', 'notes')
    readonly_fields = ('previous_quantity', 'new_quantity')
    can_delete = False
    show_change_link = True
    classes = ('collapse',)

class WarrantyInline(GenericTabularInline):
    """Inline for Warranties"""
    model = Warranty
    extra = 0
    fields = ('warranty_number', 'start_date', 'end_date', 'status')
    readonly_fields = ('warranty_number',)
    can_delete = False
    show_change_link = True
    classes = ('collapse',)

# ============================================
# MODEL ADMIN CLASSES
# ============================================

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'phone', 'manager', 'is_active')
    list_filter = ('company', 'is_active')
    search_fields = ('name', 'code', 'address', 'phone')
    raw_id_fields = ('manager',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'name', 'code')
        }),
        ('Contact Details', {
            'fields': ('address', 'phone', 'email')
        }),
        ('Management', {
            'fields': ('manager', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_type', 'company', 'branch', 'is_active')
    list_filter = ('category_type', 'is_active', 'company', 'branch')
    search_fields = ('name', 'description')
    list_editable = ('is_active',)
    raw_id_fields = ('company', 'branch')
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'branch', 'name', 'category_type')
        }),
        ('Details', {
            'fields': ('description', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'tax_id', 'is_active')
    list_filter = ('company', 'is_active')
    search_fields = ('name', 'contact_person', 'phone', 'email', 'tax_id')
    list_editable = ('is_active',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'name', 'contact_person')
        }),
        ('Contact Details', {
            'fields': ('phone', 'email', 'address')
        }),
        ('Business Details', {
            'fields': ('tax_id', 'website', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Electronic)
class ElectronicAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'device_type', 'selling_price', 'quantity_in_stock', 'branch', 'is_active')
    list_filter = ('device_type', 'brand', 'is_active', 'company', 'branch')
    search_fields = ('name', 'brand', 'model_number', 'serial_number')
    list_editable = ('selling_price', 'quantity_in_stock', 'is_active')
    raw_id_fields = ('company', 'branch', 'category', 'supplier')
    readonly_fields = ('created_at', 'updated_at', 'profit_margin_display')
    inlines = [StockMovementInline, WarrantyInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'branch', 'category', 'supplier', 'name', 'brand', 'model_number', 'serial_number')
        }),
        ('Technical Specifications', {
            'fields': ('device_type', 'processor', 'ram', 'storage', 'screen_size', 'color')
        }),
        ('Pricing & Stock', {
            'fields': ('purchase_price', 'selling_price', 'quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level')
        }),
        ('Warranty', {
            'fields': ('warranty_period_months', 'warranty_expiry')
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def profit_margin_display(self, obj):
        if obj.purchase_price > 0:
            margin = obj.profit_margin_percentage
            color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, margin
            )
        return 'N/A'
    profit_margin_display.short_description = 'Profit Margin'

@admin.register(Phone)
class PhoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'model', 'storage_capacity', 'selling_price', 'quantity_in_stock', 'condition', 'branch')
    list_filter = ('brand', 'condition', 'is_active', 'company', 'branch')
    search_fields = ('name', 'brand', 'model', 'imei')
    list_editable = ('selling_price', 'quantity_in_stock')
    raw_id_fields = ('company', 'branch', 'category', 'supplier')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [StockMovementInline, WarrantyInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'branch', 'category', 'supplier', 'name', 'brand', 'model', 'imei')
        }),
        ('Specifications', {
            'fields': ('color', 'storage_capacity', 'ram', 'screen_size', 'battery_capacity')
        }),
        ('Condition & Pricing', {
            'fields': ('condition', 'purchase_price', 'selling_price')
        }),
        ('Stock Management', {
            'fields': ('quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level')
        }),
        ('Warranty', {
            'fields': ('warranty_period_months', 'warranty_expiry')
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(Accessory)
class AccessoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'accessory_type', 'selling_price', 'quantity_in_stock', 'branch')
    list_filter = ('accessory_type', 'brand', 'is_active', 'company', 'branch')
    search_fields = ('name', 'brand', 'model')
    list_editable = ('selling_price', 'quantity_in_stock')
    raw_id_fields = ('company', 'branch', 'category', 'supplier')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [StockMovementInline, WarrantyInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'branch', 'category', 'supplier', 'name', 'brand', 'accessory_type', 'model')
        }),
        ('Compatibility', {
            'fields': ('compatible_phone_models',)
        }),
        ('Pricing & Stock', {
            'fields': ('purchase_price', 'selling_price', 'quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level')
        }),
        ('Warranty', {
            'fields': ('warranty_period_months',)
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'customer_phone', 'branch', 'total_amount', 'payment_status', 'payment_method', 'sale_date')
    list_filter = ('payment_status', 'payment_method', 'company', 'branch', 'sale_date')
    search_fields = ('customer_name', 'customer_phone', 'customer_email', 'id')
    readonly_fields = ('created_at', 'updated_at', 'item_count_display')
    raw_id_fields = ('company', 'branch', 'customer', 'sold_by')
    inlines = [SaleItemInline]
    date_hierarchy = 'sale_date'
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('company', 'branch', 'customer', 'customer_name', 'customer_phone', 'customer_email')
        }),
        ('Sale Details', {
            'fields': ('total_amount', 'discount', 'tax', 'net_amount')
        }),
        ('Payment', {
            'fields': ('payment_status', 'payment_method')
        }),
        ('Sales Staff', {
            'fields': ('sold_by',)
        }),
        ('Timestamps', {
            'fields': ('sale_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def item_count_display(self, obj):
        return obj.items.count()
    item_count_display.short_description = 'Total Items'

@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'item_name', 'quantity', 'unit_price', 'total_price')
    list_filter = ('sale__payment_status', 'sale__branch')
    search_fields = ('item_name', 'item_sku', 'sale__customer_name')
    raw_id_fields = ('sale',)  # Only sale is a real FK
    readonly_fields = ('created_at',)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('product_display', 'movement_type', 'quantity', 'previous_quantity', 'new_quantity', 'branch', 'created_at')
    list_filter = ('movement_type', 'company', 'branch', 'created_at')
    search_fields = ('reference_id', 'notes')
    raw_id_fields = ('company', 'branch', 'performed_by')
    readonly_fields = ('created_at', 'previous_quantity', 'new_quantity')
    date_hierarchy = 'created_at'
    
    def product_display(self, obj):
        if obj.product:
            return str(obj.product)
        return 'Deleted Product'
    product_display.short_description = 'Product'
    
    fieldsets = (
        ('Product Information', {
            'fields': ('company', 'branch', 'content_type', 'object_id')
        }),
        ('Movement Details', {
            'fields': ('movement_type', 'quantity', 'previous_quantity', 'new_quantity')
        }),
        ('Reference', {
            'fields': ('reference_id', 'reference_model')
        }),
        ('Notes', {
            'fields': ('notes', 'performed_by')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'supplier', 'branch', 'total_amount', 'status', 'order_date')
    list_filter = ('status', 'company', 'branch', 'order_date')
    search_fields = ('order_number', 'supplier__name', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('company', 'branch', 'supplier', 'created_by')
    inlines = [PurchaseOrderItemInline]
    date_hierarchy = 'order_date'
    
    fieldsets = (
        ('Order Information', {
            'fields': ('company', 'branch', 'supplier', 'order_number')
        }),
        ('Dates', {
            'fields': ('order_date', 'expected_delivery_date', 'received_date')
        }),
        ('Financial', {
            'fields': ('subtotal', 'tax', 'total_amount')
        }),
        ('Status', {
            'fields': ('status', 'notes')
        }),
        ('Creator', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['mark_as_ordered', 'mark_as_received', 'mark_as_cancelled']
    
    def mark_as_ordered(self, request, queryset):
        updated = queryset.update(status='ordered')
        self.message_user(request, f'{updated} purchase orders marked as Ordered.')
    mark_as_ordered.short_description = 'Mark selected orders as Ordered'
    
    def mark_as_received(self, request, queryset):
        updated = queryset.update(status='received', received_date=timezone.now().date())
        self.message_user(request, f'{updated} purchase orders marked as Received.')
    mark_as_received.short_description = 'Mark selected orders as Received'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} purchase orders marked as Cancelled.')
    mark_as_cancelled.short_description = 'Mark selected orders as Cancelled'

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'product_name', 'quantity_ordered', 'quantity_received', 'unit_price', 'total_price')
    list_filter = ('purchase_order__status',)
    search_fields = ('product_name', 'purchase_order__order_number')
    raw_id_fields = ('purchase_order',)  # Only purchase_order is a real FK
    readonly_fields = ('created_at', 'updated_at')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Warranty)
class WarrantyAdmin(admin.ModelAdmin):
    list_display = ('warranty_number', 'product_name', 'customer', 'start_date', 'end_date', 'status', 'is_expired_display')
    list_filter = ('status', 'company', 'branch', 'start_date', 'end_date')
    search_fields = ('warranty_number', 'product_name', 'serial_number', 'customer__name', 'customer__phone')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('company', 'branch', 'sale', 'customer')
    date_hierarchy = 'start_date'
    
    def is_expired_display(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: red;">Expired</span>')
        return format_html('<span style="color: green;">Active</span>')
    is_expired_display.short_description = 'Status'
    
    fieldsets = (
        ('Warranty Information', {
            'fields': ('company', 'branch', 'warranty_number')
        }),
        ('Product Details', {
            'fields': ('content_type', 'object_id', 'product_name', 'serial_number')
        }),
        ('Customer & Sale', {
            'fields': ('customer', 'sale')
        }),
        ('Validity Period', {
            'fields': ('start_date', 'end_date', 'status')
        }),
        ('Terms & Notes', {
            'fields': ('terms_conditions', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Repair)
class RepairAdmin(admin.ModelAdmin):
    list_display = ('repair_number', 'product_name', 'customer', 'status', 'priority', 'estimated_cost', 'received_date')
    list_filter = ('status', 'priority', 'company', 'branch', 'received_date')
    search_fields = ('repair_number', 'product_name', 'serial_number', 'customer__name', 'customer__phone')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('company', 'branch', 'customer', 'warranty', 'assigned_to', 'created_by')
    date_hierarchy = 'received_date'
    
    fieldsets = (
        ('Repair Information', {
            'fields': ('company', 'branch', 'repair_number')
        }),
        ('Product Details', {
            'fields': ('content_type', 'object_id', 'product_name', 'serial_number')
        }),
        ('Customer & Warranty', {
            'fields': ('customer', 'warranty')
        }),
        ('Issue & Solution', {
            'fields': ('issue_description', 'diagnosis', 'solution')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority')
        }),
        ('Cost Details', {
            'fields': ('estimated_cost', 'actual_cost')
        }),
        ('Dates', {
            'fields': ('received_date', 'completed_date')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'created_by')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['mark_as_in_progress', 'mark_as_completed', 'mark_as_cancelled']
    
    def mark_as_in_progress(self, request, queryset):
        updated = queryset.update(status='in_progress')
        self.message_user(request, f'{updated} repairs marked as In Progress.')
    mark_as_in_progress.short_description = 'Mark selected repairs as In Progress'
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed', completed_date=timezone.now())
        self.message_user(request, f'{updated} repairs marked as Completed.')
    mark_as_completed.short_description = 'Mark selected repairs as Completed'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} repairs marked as Cancelled.')
    mark_as_cancelled.short_description = 'Mark selected repairs as Cancelled'
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'content_type':
            kwargs['limit_choices_to'] = {
                'app_label': 'epa_shop',  # Replace with your actual app name
                'model__in': ['electronic', 'phone', 'accessory']
            }
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'company', 'branch', 'total_purchases', 'visit_count', 'loyalty_points', 'is_active')
    search_fields = ('name', 'phone', 'email', 'address')
    list_filter = ('is_active', 'company', 'branch', 'created_at')
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('company', 'branch')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('company', 'branch', 'name', 'phone', 'email', 'address')
        }),
        ('Purchase Statistics', {
            'fields': ('total_purchases', 'visit_count', 'last_visit')
        }),
        ('Loyalty', {
            'fields': ('loyalty_points',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['activate_customers', 'deactivate_customers']
    
    def activate_customers(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} customers activated.')
    activate_customers.short_description = 'Activate selected customers'
    
    def deactivate_customers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} customers deactivated.')
    deactivate_customers.short_description = 'Deactivate selected customers'

# ============================================
# CUSTOM ADMIN SITE CONFIGURATION (Optional)
# ============================================

class EPAAdminSite(admin.AdminSite):
    site_header = 'EPA Management System'
    site_title = 'Electronics, Phones & Accessories Admin'
    index_title = 'Dashboard'

# Uncomment to use custom admin site
# admin_site = EPAAdminSite(name='epa_admin')
# admin_site.register(Branch, BranchAdmin)
# admin_site.register(Supplier, SupplierAdmin)
# admin_site.register(Category, CategoryAdmin)
# admin_site.register(Electronic, ElectronicAdmin)
# admin_site.register(Phone, PhoneAdmin)
# admin_site.register(Accessory, AccessoryAdmin)
# admin_site.register(Sale, SaleAdmin)
# admin_site.register(SaleItem, SaleItemAdmin)
# admin_site.register(StockMovement, StockMovementAdmin)
# admin_site.register(PurchaseOrder, PurchaseOrderAdmin)
# admin_site.register(PurchaseOrderItem, PurchaseOrderItemAdmin)
# admin_site.register(Warranty, WarrantyAdmin)
# admin_site.register(Repair, RepairAdmin)
# admin_site.register(Customer, CustomerAdmin)