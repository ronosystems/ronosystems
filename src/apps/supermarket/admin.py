from django.contrib import admin
from .models import (
    Category, Supplier, Product, PriceHistory, Inventory,
    PurchaseOrder, PurchaseOrderItem, Sale, SaleItem,
    Customer, Discount, ShelfLocation
)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_type', 'company', 'is_active')
    list_filter = ('category_type', 'is_active', 'company')
    search_fields = ('name', 'description')

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'email', 'is_active')
    search_fields = ('name', 'contact_person', 'phone', 'email')
    list_filter = ('is_active',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'barcode', 'category', 'selling_price', 'quantity_in_stock')
    list_filter = ('category', 'unit', 'is_active', 'is_perishable')
    search_fields = ('name', 'barcode', 'sku')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'old_price', 'new_price', 'changed_at')
    list_filter = ('changed_at',)
    readonly_fields = ('changed_at',)

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'transaction_type', 'quantity', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    readonly_fields = ('created_at',)

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'supplier', 'total_amount', 'status', 'order_date')
    list_filter = ('status', 'order_date')
    search_fields = ('order_number', 'supplier__name')

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'product', 'quantity', 'unit_price', 'total_price')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'total_amount', 'payment_status', 'sale_date')
    list_filter = ('payment_status', 'payment_method', 'company')
    search_fields = ('customer_name', 'customer_phone')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'total_price')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'total_purchases', 'visit_count', 'last_visit')
    search_fields = ('name', 'phone', 'email')
    list_filter = ('is_active',)

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ('name', 'discount_type', 'value', 'start_date', 'end_date', 'is_active')
    list_filter = ('discount_type', 'is_active', 'start_date', 'end_date')

@admin.register(ShelfLocation)
class ShelfLocationAdmin(admin.ModelAdmin):
    list_display = ('aisle', 'shelf', 'section', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('aisle', 'shelf', 'section')
