from rest_framework import serializers
from .models import (
    Category, Supplier, Product, PriceHistory, Inventory,
    PurchaseOrder, PurchaseOrderItem, Sale, SaleItem,
    Customer, Discount, ShelfLocation
)

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'company', 'name', 'category_type', 'description', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'company', 'name', 'contact_person', 'phone', 'email', 
                  'address', 'tax_id', 'payment_terms', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class ProductSerializer(serializers.ModelSerializer):
    is_in_stock = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    profit_margin = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'company', 'category', 'supplier',
            'name', 'barcode', 'sku', 'description',
            'unit', 'weight', 'purchase_price', 'selling_price',
            'quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level',
            'aisle', 'shelf', 'image',
            'is_active', 'is_perishable', 'expiry_date',
            'created_at', 'updated_at',
            'is_in_stock', 'is_low_stock', 'profit_margin'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = Inventory
        fields = ['id', 'company', 'product', 'product_name', 'transaction_type', 
                  'quantity', 'previous_quantity', 'new_quantity', 'notes', 
                  'reference', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_at']

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'purchase_order', 'product', 'product_name',
                  'quantity', 'unit_price', 'total_price', 'received_quantity']

class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = ['id', 'company', 'supplier', 'supplier_name',
                  'order_number', 'order_date', 'expected_delivery',
                  'total_amount', 'status', 'notes', 'created_by',
                  'created_by_username', 'created_at', 'updated_at', 'items']
        read_only_fields = ['id', 'created_at', 'updated_at']

class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = SaleItem
        fields = ['id', 'sale', 'product', 'product_name',
                  'quantity', 'unit_price', 'total_price', 'created_at']
        read_only_fields = ['id', 'created_at']

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    sold_by_username = serializers.CharField(source='sold_by.username', read_only=True)
    
    class Meta:
        model = Sale
        fields = [
            'id', 'company', 'customer_name', 'customer_phone',
            'customer_email', 'subtotal', 'discount', 'tax',
            'total_amount', 'payment_status', 'payment_method',
            'sold_by', 'sold_by_username', 'sale_date',
            'created_at', 'updated_at', 'items', 'item_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'sale_date']

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'company', 'name', 'phone', 'email', 'address',
            'loyalty_points', 'total_purchases', 'visit_count', 'last_visit',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 
                           'loyalty_points', 'total_purchases', 'visit_count']

class DiscountSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True, allow_null=True)
    
    class Meta:
        model = Discount
        fields = [
            'id', 'company', 'product', 'product_name',
            'name', 'discount_type', 'value',
            'buy_quantity', 'get_quantity',
            'start_date', 'end_date', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class ShelfLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShelfLocation
        fields = ['id', 'company', 'aisle', 'shelf', 'section', 'description', 'is_active']
        read_only_fields = ['id']
