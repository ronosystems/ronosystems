from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import (
    Category, Electronic, Phone, Accessory, 
    Sale, SaleItem, Customer, Branch, Supplier,
    StockMovement, PurchaseOrder, PurchaseOrderItem,
    Warranty, Repair
)

# ============================================
# BRANCH SERIALIZERS
# ============================================

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'company', 'name', 'code', 'address', 'phone', 
                  'email', 'manager', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class BranchDetailSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    
    class Meta:
        model = Branch
        fields = ['id', 'company', 'name', 'code', 'address', 'phone', 
                  'email', 'manager', 'manager_name', 'is_active', 
                  'created_at', 'updated_at']

# ============================================
# SUPPLIER SERIALIZERS
# ============================================

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'company', 'name', 'contact_person', 'phone', 
                  'email', 'address', 'tax_id', 'website', 'is_active', 
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

# ============================================
# CATEGORY SERIALIZERS
# ============================================

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'company', 'branch', 'name', 'category_type', 
                  'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

# ============================================
# PRODUCT SERIALIZERS
# ============================================

class ElectronicSerializer(serializers.ModelSerializer):
    profit_margin = serializers.ReadOnlyField()
    profit_margin_percentage = serializers.ReadOnlyField()
    is_in_stock = serializers.ReadOnlyField()
    
    class Meta:
        model = Electronic
        fields = [
            'id', 'company', 'branch', 'category', 'supplier',
            'name', 'brand', 'model_number', 'serial_number',
            'device_type', 'processor', 'ram', 'storage', 'screen_size', 'color',
            'purchase_price', 'selling_price',
            'quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level',
            'image', 'warranty_period_months', 'warranty_expiry',
            'is_active', 'created_at', 'updated_at',
            'is_in_stock', 'profit_margin', 'profit_margin_percentage'
        ]
        read_only_fields = ['created_at', 'updated_at']

class PhoneSerializer(serializers.ModelSerializer):
    is_in_stock = serializers.ReadOnlyField()
    profit_margin_percentage = serializers.ReadOnlyField()
    
    class Meta:
        model = Phone
        fields = [
            'id', 'company', 'branch', 'category', 'supplier',
            'name', 'brand', 'model', 'imei',
            'color', 'storage_capacity', 'ram', 'screen_size', 'battery_capacity',
            'condition', 'purchase_price', 'selling_price',
            'quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level',
            'image', 'warranty_period_months', 'warranty_expiry',
            'is_active', 'created_at', 'updated_at',
            'is_in_stock', 'profit_margin_percentage'
        ]
        read_only_fields = ['created_at', 'updated_at']

class AccessorySerializer(serializers.ModelSerializer):
    is_in_stock = serializers.ReadOnlyField()
    
    class Meta:
        model = Accessory
        fields = [
            'id', 'company', 'branch', 'category', 'supplier',
            'name', 'brand', 'accessory_type', 'model', 'compatible_phone_models',
            'purchase_price', 'selling_price',
            'quantity_in_stock', 'minimum_stock_level', 'maximum_stock_level',
            'image', 'warranty_period_months',
            'is_active', 'created_at', 'updated_at',
            'is_in_stock'
        ]
        read_only_fields = ['created_at', 'updated_at']

# ============================================
# SALE SERIALIZERS
# ============================================

class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = ['id', 'sale', 'content_type', 'object_id', 
                  'item_name', 'item_sku', 'quantity', 'unit_price', 'total_price']
        read_only_fields = ['total_price']

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    item_count = serializers.ReadOnlyField()
    customer_name_display = serializers.CharField(source='customer_name', read_only=True)
    
    class Meta:
        model = Sale
        fields = [
            'id', 'company', 'branch', 'customer',
            'customer_name', 'customer_phone', 'customer_email',
            'total_amount', 'discount', 'tax', 'net_amount',
            'payment_status', 'payment_method',
            'sold_by', 'sale_date',
            'created_at', 'updated_at',
            'items', 'item_count', 'customer_name_display'
        ]
        read_only_fields = ['created_at', 'updated_at', 'net_amount']

class SaleCreateSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    
    class Meta:
        model = Sale
        fields = [
            'company', 'branch', 'customer',
            'customer_name', 'customer_phone', 'customer_email',
            'discount', 'tax', 'payment_method',
            'items'
        ]
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        sale = Sale.objects.create(**validated_data)
        
        total_amount = 0
        for item_data in items_data:
            item_data['sale'] = sale
            item_data['total_price'] = item_data['quantity'] * item_data['unit_price']
            SaleItem.objects.create(**item_data)
            total_amount += item_data['total_price']
        
        sale.total_amount = total_amount
        sale.net_amount = total_amount - sale.discount + sale.tax
        sale.save()
        
        return sale

# ============================================
# CUSTOMER SERIALIZERS
# ============================================

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'company', 'branch', 'name', 'phone', 'email', 'address',
            'total_purchases', 'visit_count', 'last_visit', 'loyalty_points',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'total_purchases', 'visit_count']

# ============================================
# STOCK MOVEMENT SERIALIZERS
# ============================================

class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product', read_only=True)
    
    class Meta:
        model = StockMovement
        fields = [
            'id', 'company', 'branch', 'content_type', 'object_id',
            'product_name', 'movement_type', 'quantity',
            'previous_quantity', 'new_quantity',
            'reference_id', 'reference_model', 'notes',
            'performed_by', 'created_at'
        ]
        read_only_fields = ['created_at', 'previous_quantity', 'new_quantity']

class StockMovementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = [
            'company', 'branch', 'content_type', 'object_id',
            'movement_type', 'quantity', 'reference_id', 'reference_model', 'notes'
        ]
    
    def create(self, validated_data):
        # Get the product and update its stock
        content_type = validated_data['content_type']
        object_id = validated_data['object_id']
        quantity = validated_data['quantity']
        
        # Get the product model
        model_class = content_type.model_class()
        product = model_class.objects.get(id=object_id)
        
        # Store previous quantity
        validated_data['previous_quantity'] = product.quantity_in_stock
        
        # Update product stock
        product.quantity_in_stock += quantity
        product.save()
        
        # Store new quantity
        validated_data['new_quantity'] = product.quantity_in_stock
        
        return super().create(validated_data)

# ============================================
# PURCHASE ORDER SERIALIZERS
# ============================================

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product', read_only=True)
    
    class Meta:
        model = PurchaseOrderItem
        fields = [
            'id', 'purchase_order', 'content_type', 'object_id',
            'product_name', 'quantity_ordered', 'quantity_received',
            'unit_price', 'total_price', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'company', 'branch', 'supplier', 'supplier_name',
            'order_number', 'order_date', 'expected_delivery_date',
            'received_date', 'subtotal', 'tax', 'total_amount',
            'status', 'notes', 'created_by', 'created_by_name',
            'created_at', 'updated_at', 'items'
        ]
        read_only_fields = ['created_at', 'updated_at']

# ============================================
# WARRANTY SERIALIZERS
# ============================================

class WarrantySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = Warranty
        fields = [
            'id', 'company', 'branch', 'sale', 'customer', 'customer_name',
            'content_type', 'object_id', 'product_name', 'serial_number',
            'warranty_number', 'start_date', 'end_date', 'status',
            'terms_conditions', 'notes', 'created_at', 'updated_at',
            'is_expired'
        ]
        read_only_fields = ['created_at', 'updated_at', 'warranty_number']

# ============================================
# REPAIR SERIALIZERS
# ============================================

class RepairSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Repair
        fields = [
            'id', 'company', 'branch', 'customer', 'customer_name',
            'warranty', 'content_type', 'object_id', 'product_name',
            'serial_number', 'repair_number', 'issue_description',
            'diagnosis', 'solution', 'status', 'priority',
            'estimated_cost', 'actual_cost',
            'received_date', 'completed_date',
            'assigned_to', 'assigned_to_name',
            'created_by', 'created_by_name',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'repair_number']