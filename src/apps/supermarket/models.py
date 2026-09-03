from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.companies.models import Company

User = get_user_model()

# ============================================
# CATEGORY MODELS
# ============================================

class Category(models.Model):
    """Product categories like Dairy, Meat, Produce, etc."""
    CATEGORY_TYPES = (
        ('dairy', 'Dairy & Eggs'),
        ('meat', 'Meat & Poultry'),
        ('produce', 'Fresh Produce'),
        ('bakery', 'Bakery & Bread'),
        ('canned', 'Canned Goods'),
        ('frozen', 'Frozen Foods'),
        ('beverage', 'Beverages'),
        ('snacks', 'Snacks & Candy'),
        ('household', 'Household Items'),
        ('personal_care', 'Personal Care'),
        ('baby', 'Baby Products'),
        ('pet', 'Pet Supplies'),
        ('other', 'Other'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_categories')
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_categories'
        ordering = ['name']
        unique_together = ['company', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category_type})"

# ============================================
# SUPPLIER MODELS
# ============================================

class Supplier(models.Model):
    """Product suppliers/vendors"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_suppliers')
    
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField()
    
    tax_id = models.CharField(max_length=50, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)  # e.g., "Net 30"
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_suppliers'
        ordering = ['name']
    
    def __str__(self):
        return self.name

# ============================================
# PRODUCT MODELS
# ============================================

class Product(models.Model):
    """Individual products with barcodes"""
    UNIT_CHOICES = (
        ('each', 'Each'),
        ('kg', 'Kilogram'),
        ('g', 'Gram'),
        ('l', 'Liter'),
        ('ml', 'Milliliter'),
        ('pack', 'Pack'),
        ('box', 'Box'),
        ('carton', 'Carton'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, related_name='products')
    
    # Basic Info
    name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=50, unique=True)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    description = models.TextField(blank=True)
    
    # Unit & Weight
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='each')
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, help_text="Weight in kg")
    
    # Pricing
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Stock
    quantity_in_stock = models.IntegerField(default=0)
    minimum_stock_level = models.IntegerField(default=10)
    maximum_stock_level = models.IntegerField(default=100)
    
    # Shelf Location
    aisle = models.CharField(max_length=10, blank=True)
    shelf = models.CharField(max_length=10, blank=True)
    
    # Images
    image = models.ImageField(upload_to='supermarket/products/', blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_perishable = models.BooleanField(default=False)
    expiry_date = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_products'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.barcode})"
    
    @property
    def is_in_stock(self):
        return self.quantity_in_stock > 0
    
    @property
    def is_low_stock(self):
        return self.quantity_in_stock <= self.minimum_stock_level
    
    @property
    def profit_margin(self):
        if self.purchase_price:
            return float(self.selling_price - self.purchase_price)
        return 0

# ============================================
# PRICE HISTORY MODELS
# ============================================

class PriceHistory(models.Model):
    """Track price changes over time"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_history')
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'supermarket_price_history'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.product.name}: {self.old_price} -> {self.new_price}"

# ============================================
# INVENTORY MODELS
# ============================================

class Inventory(models.Model):
    """Track inventory movements"""
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer'),
        ('waste', 'Waste/Damage'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_inventory')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_records')
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    notes = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)  # e.g., PO-12345, SALE-67890
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'supermarket_inventory'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_type}: {self.quantity} of {self.product.name}"

# ============================================
# PURCHASE ORDER MODELS
# ============================================

class PurchaseOrder(models.Model):
    """Orders from suppliers"""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    
    order_number = models.CharField(max_length=50, unique=True)
    order_date = models.DateField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='supermarket_purchase_orders')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_purchase_orders'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"PO #{self.order_number} - {self.supplier.name}"

class PurchaseOrderItem(models.Model):
    """Items in a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    received_quantity = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'supermarket_purchase_order_items'
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

# ============================================
# SALE MODELS
# ============================================

class Sale(models.Model):
    """Customer sales transactions"""
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially Paid'),
        ('refunded', 'Refunded'),
    )
    
    PAYMENT_METHOD = (
        ('cash', 'Cash'),
        ('m-pesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer'),
        ('card', 'Card'),
        ('credit', 'Credit'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_sales')
    
    # Customer
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD)
    
    # Staff
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='supermarket_sales')
    
    sale_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_sales'
        ordering = ['-sale_date']
    
    def __str__(self):
        return f"Sale #{self.id} - {self.customer_name} ({self.total_amount})"
    
    @property
    def item_count(self):
        return self.items.count()

class SaleItem(models.Model):
    """Individual items in a sale"""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'supermarket_sale_items'
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

# ============================================
# CUSTOMER MODELS
# ============================================

class Customer(models.Model):
    """Customer profiles for loyalty and tracking"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_customers')
    
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    loyalty_points = models.IntegerField(default=0)
    total_purchases = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    visit_count = models.IntegerField(default=0)
    last_visit = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_customers'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.phone})"

# ============================================
# DISCOUNT MODELS
# ============================================

class Discount(models.Model):
    """Promotions and discounts"""
    DISCOUNT_TYPES = (
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
        ('buy_x_get_y', 'Buy X Get Y'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_discounts')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='discounts')
    
    name = models.CharField(max_length=200)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Percentage or fixed amount")
    
    # Buy X Get Y (for buy_x_get_y type)
    buy_quantity = models.IntegerField(null=True, blank=True)
    get_quantity = models.IntegerField(null=True, blank=True)
    
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supermarket_discounts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.discount_type})"

# ============================================
# SHELF LOCATION MODELS
# ============================================

class ShelfLocation(models.Model):
    """Store shelf/aisle locations"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supermarket_shelf_locations')
    
    aisle = models.CharField(max_length=10)
    shelf = models.CharField(max_length=10)
    section = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'supermarket_shelf_locations'
        ordering = ['aisle', 'shelf']
        unique_together = ['company', 'aisle', 'shelf']
    
    def __str__(self):
        return f"Aisle {self.aisle} - Shelf {self.shelf}"
