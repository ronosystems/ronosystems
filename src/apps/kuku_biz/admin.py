from django.contrib import admin
from .models import (
    Flock, EggProduction, Customer, EggSale, EggSaleItem,
    FeedType, FeedRecord, HealthRecord, Mortality,
    Expense, InventoryItem, PriceHistory,
)


@admin.register(Flock)
class FlockAdmin(admin.ModelAdmin):
    list_display = ('name', 'flock_type', 'initial_count', 'current_count', 'status', 'date_acquired')
    list_filter = ('flock_type', 'status')
    search_fields = ('name', 'breed')


@admin.register(EggProduction)
class EggProductionAdmin(admin.ModelAdmin):
    list_display = ('flock', 'date', 'eggs_collected', 'eggs_cracked', 'good_eggs')
    list_filter = ('date',)
    search_fields = ('flock__name',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer_type', 'phone', 'location', 'is_active')
    list_filter = ('customer_type', 'is_active')
    search_fields = ('name', 'phone')


class EggSaleItemInline(admin.TabularInline):
    model = EggSaleItem
    extra = 1


@admin.register(EggSale)
class EggSaleAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'sale_date', 'total_amount', 'amount_paid', 'status')
    list_filter = ('status', 'sale_date')
    search_fields = ('invoice_number', 'customer__name')
    inlines = [EggSaleItemInline]


@admin.register(FeedType)
class FeedTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'protein_percent', 'cost_per_kg', 'is_active')


@admin.register(FeedRecord)
class FeedRecordAdmin(admin.ModelAdmin):
    list_display = ('flock', 'date', 'feed_type', 'quantity_kg', 'cost')
    list_filter = ('date', 'feed_type')
    search_fields = ('flock__name',)


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ('flock', 'date', 'record_type', 'product_used', 'cost')
    list_filter = ('record_type', 'date')


@admin.register(Mortality)
class MortalityAdmin(admin.ModelAdmin):
    list_display = ('flock', 'date', 'count', 'cause')
    list_filter = ('cause', 'date')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'category', 'description', 'amount', 'flock')
    list_filter = ('category', 'date')


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'item_type', 'quantity', 'unit', 'needs_reorder')
    list_filter = ('item_type',)
    search_fields = ('name',)


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('unit', 'price', 'effective_date')
    list_filter = ('unit', 'effective_date')