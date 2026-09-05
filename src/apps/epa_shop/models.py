from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from apps.companies.models import Company
from decimal import Decimal


User = get_user_model()

# ============================================
# BRANCH / STORE LOCATION
# ============================================

class Branch(models.Model):
    """Physical store locations/branches"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_branches')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_branches')
    
    # Currency fields
    currency = models.CharField(max_length=10, default='KES', help_text="Currency code (KES, USD, EUR, etc.)")
    currency_symbol = models.CharField(max_length=10, default='KSh', help_text="Currency symbol (KSh, $, €, etc.)")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_branches'
        ordering = ['name']
        unique_together = ['company', 'code']

    def __str__(self):
        return f"{self.name} ({self.code})"


# ============================================
# PRODUCT CATEGORIES
# ============================================

class Category(models.Model):
    """Product categories like Electronics, Phones, Accessories"""
    CATEGORY_TYPES = (
        ('electronics', 'Electronics'),
        ('phones', 'Phones'),
        ('accessories', 'Accessories'),
        ('parts', 'Parts & Components'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_categories')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='categories', null=True, blank=True)
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_categories'
        ordering = ['name']
        unique_together = ['company', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category_type})"


# ============================================
# SUPPLIER MODEL
# ============================================

class Supplier(models.Model):
    """Product suppliers/vendors"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_suppliers')
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True, verbose_name="Tax ID")
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_suppliers'
        ordering = ['name']

    def __str__(self):
        return self.name


# ============================================
# OWNER MODEL (For tracking product ownership)
# ============================================

class Owner(models.Model):
    """Product owner/customer who purchased the product"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_owners')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='owners')
    
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Owner details
    id_number = models.CharField(max_length=50, blank=True, verbose_name="ID Number")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=(
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ), blank=True)
    
    # Purchase history
    total_purchases = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purchase_count = models.IntegerField(default=0)
    last_purchase_date = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_owners'
        ordering = ['name']
        indexes = [
            models.Index(fields=['company', 'phone']),
            models.Index(fields=['company', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.phone})"


# ============================================
# BASE PRODUCT MODEL WITH COMPANY-WIDE UNIQUE CODES
# ============================================

class BaseProduct(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    product_code = models.CharField(
        max_length=20, 
        db_index=True, 
        unique=False, 
        null=True, 
        blank=True,
        help_text="Unique product code within the company (auto-generated)"
    )
    
    class Meta:
        abstract = True
    
    def get_company_prefix(self):
        if self.company and self.company.name:
            return self.company.name[0].upper()
        return "X"
    
    def generate_unique_product_code(self):
        from .models import Phone, Electronic, Accessory
        
        prefix = self.get_company_prefix()
        
        # Get ALL existing product codes for this company across ALL models
        all_existing_codes = set()
        for model in [Phone, Electronic, Accessory]:
            codes = model.objects.filter(
                company=self.company
            ).exclude(
                product_code__isnull=True
            ).exclude(
                product_code=''
            ).values_list('product_code', flat=True)
            all_existing_codes.update(codes)
        
        # Extract numbers from existing codes
        existing_numbers = []
        for code in all_existing_codes:
            if code and code.startswith(prefix):
                try:
                    num_str = code.replace(prefix, '')
                    if num_str.isdigit():
                        existing_numbers.append(int(num_str))
                except (ValueError, TypeError):
                    pass
        
        # Find the next available number (fill gaps)
        if existing_numbers:
            existing_numbers.sort()
            next_number = 1
            for num in existing_numbers:
                if num == next_number:
                    next_number += 1
                elif num > next_number:
                    break
        else:
            next_number = 1
        
        return f"{prefix}{str(next_number).zfill(6)}"
    
    def save(self, *args, **kwargs):
        # Check if we should skip auto-generation
        skip_auto_generate = kwargs.pop('skip_auto_generate', False)
        
        if skip_auto_generate:
            super().save(*args, **kwargs)
            return
        
        if not self.product_code:
            for attempt in range(20):
                new_code = self.generate_unique_product_code()
                
                from .models import Phone, Electronic, Accessory
                code_exists = False
                for model in [Phone, Electronic, Accessory]:
                    if model.objects.filter(
                        company=self.company,
                        product_code=new_code
                    ).exclude(pk=self.pk).exists():
                        code_exists = True
                        break
                
                if not code_exists:
                    self.product_code = new_code
                    break
            else:
                import time
                timestamp = int(time.time() * 1000) % 1000000
                self.product_code = f"{self.get_company_prefix()}{str(timestamp).zfill(6)}"
        
        super().save(*args, **kwargs)
    
    @property
    def display_id(self):
        return self.product_code or "N/A"

        

# ============================================
# PHONE MODEL
# ============================================

class Phone(BaseProduct):
    """Mobile phones and smartphones"""
    CONDITION_CHOICES = (
        ('new', 'New'),
        ('used', 'Used'),
        ('refurbished', 'Refurbished'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_phone_products')
    
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='phones')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='phones')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones')
    
    # Basic Info
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    imei = models.CharField(max_length=15, db_index=True, null=True, blank=True)
    
    # Specifications
    color = models.CharField(max_length=50)
    storage_capacity = models.CharField(max_length=50)
    ram = models.CharField(max_length=20)
    screen_size = models.CharField(max_length=20)
    battery_capacity = models.CharField(max_length=20)
    
    # Condition
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    
    # Pricing
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Stock
    quantity_in_stock = models.IntegerField(default=0)
    minimum_stock_level = models.IntegerField(default=3)
    maximum_stock_level = models.IntegerField(default=30, null=True, blank=True)
    
    # Images
    image = models.ImageField(upload_to='epa/phones/%Y/%m/', blank=True, null=True)
    
    # Warranty
    warranty_period_months = models.IntegerField(default=12)
    warranty_expiry = models.DateField(null=True, blank=True)
    
    # Owner
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones')
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generic relation for sale items
    sale_items = GenericRelation('SaleItem', content_type_field='content_type', object_id_field='object_id')
    
    # Add these new fields for Feature Phone support
    PHONE_TYPE_CHOICES = (
        ('smartphone', 'Smartphone'),
        ('feature', 'Feature Phone'),
    )
    
    NETWORK_CHOICES = (
        ('2g', '2G'),
        ('3g', '3G'),
        ('4g', '4G'),
        ('dual_sim', 'Dual SIM'),
    )
    
    MEMORY_CARD_CHOICES = (
        ('yes', 'Yes'),
        ('no', 'No'),
    )
    
    # Feature phone specific fields
    phone_type = models.CharField(max_length=20, choices=PHONE_TYPE_CHOICES, default='smartphone')
    network_type = models.CharField(max_length=20, choices=NETWORK_CHOICES, blank=True, null=True)
    memory_card = models.CharField(max_length=10, choices=MEMORY_CARD_CHOICES, default='no')
    features = models.TextField(blank=True, null=True, help_text="Feature phone features like FM Radio, Torch, etc.")

    class Meta:
        db_table = 'epa_phones'
        ordering = ['-created_at']
        unique_together = ['company', 'product_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['imei']),
            models.Index(fields=['owner']),
            models.Index(fields=['product_code']),
        ]
    
    def __str__(self):
        return f"{self.product_code} - {self.brand} {self.model} ({self.storage_capacity})"
    
    @property
    def is_in_stock(self):
        return self.quantity_in_stock > 0
    
    @property
    def profit_margin_percentage(self):
        if self.purchase_price > 0:
            return (float(self.selling_price - self.purchase_price) / float(self.purchase_price)) * 100
        return 0


# ============================================
# ELECTRONIC MODEL
# ============================================

class Electronic(BaseProduct):
    """Electronic products like laptops, desktops, tablets"""
    TYPE_CHOICES = (
        ('laptop', 'Laptop'),
        ('desktop', 'Desktop'),
        ('tablet', 'Tablet'),
        ('monitor', 'Monitor'),
        ('printer', 'Printer'),
        ('camera', 'Camera'),
        ('audio', 'Audio Equipment'),
        ('other', 'Other'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_electronic_products')
    
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='electronics')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='electronics')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='electronics')
    
    # Basic Info
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    model_number = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    
    # Technical Specs
    device_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    processor = models.CharField(max_length=200, blank=True)
    ram = models.CharField(max_length=50, blank=True)
    storage = models.CharField(max_length=100, blank=True)
    screen_size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=50, blank=True)
    
    # Pricing
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Stock
    quantity_in_stock = models.IntegerField(default=0)
    minimum_stock_level = models.IntegerField(default=5)
    maximum_stock_level = models.IntegerField(default=50, null=True, blank=True)
    
    # Images
    image = models.ImageField(upload_to='epa/electronics/%Y/%m/', blank=True, null=True)
    
    # Warranty
    warranty_period_months = models.IntegerField(default=12)
    warranty_expiry = models.DateField(null=True, blank=True)
    
    # Owner
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='electronics')
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    sale_items = GenericRelation('SaleItem', content_type_field='content_type', object_id_field='object_id')
    
    class Meta:
        db_table = 'epa_electronics'
        ordering = ['-created_at']
        unique_together = ['company', 'product_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['serial_number']),
            models.Index(fields=['owner']),
            models.Index(fields=['product_code']),
        ]
    
    def __str__(self):
        return f"{self.product_code} - {self.brand} {self.name} ({self.model_number})"
    
    @property
    def is_in_stock(self):
        return self.quantity_in_stock > 0
    
    @property
    def profit_margin(self):
        if self.purchase_price:
            return float(self.selling_price - self.purchase_price)
        return 0
    
    @property
    def profit_margin_percentage(self):
        if self.purchase_price > 0:
            return (float(self.selling_price - self.purchase_price) / float(self.purchase_price)) * 100
        return 0


# ============================================
# ACCESSORY MODEL
# ============================================

class Accessory(BaseProduct):
    """Accessories like cases, chargers, headphones"""
    ACCESSORY_TYPES = (
        ('electronic accessory', 'Electronic Accessory'),
        ('phone accessory', 'Phone Accessory'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_accessory_products')
    
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='accessories')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='accessories')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='accessories')
    
    # Basic Info
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    accessory_type = models.CharField(max_length=20, choices=ACCESSORY_TYPES)
    model = models.CharField(max_length=100, blank=True)
    
    # Compatibility
    compatible_phone_models = models.TextField(help_text="Comma-separated list of phone models", blank=True)
    
    # Pricing
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Stock
    quantity_in_stock = models.IntegerField(default=0)
    minimum_stock_level = models.IntegerField(default=10)
    maximum_stock_level = models.IntegerField(default=100, null=True, blank=True)
    
    # Images
    image = models.ImageField(upload_to='epa/accessories/%Y/%m/', blank=True, null=True)
    
    # Warranty
    warranty_period_months = models.IntegerField(default=6)
    
    # Owner
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='accessories')
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    sale_items = GenericRelation('SaleItem', content_type_field='content_type', object_id_field='object_id')
    
    class Meta:
        db_table = 'epa_accessories'
        ordering = ['-created_at']
        unique_together = ['company', 'product_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['owner']),
            models.Index(fields=['product_code']),
        ]
    
    def __str__(self):
        return f"{self.product_code} - {self.brand} {self.name} ({self.accessory_type})"
    
    @property
    def is_in_stock(self):
        return self.quantity_in_stock > 0


# ============================================
# UNIT MODEL - For IMEI/Serial Numbers
# ============================================

class Unit(models.Model):
    """Individual units with IMEI/Serial numbers"""
    
    UNIT_TYPES = (
        ('imei', 'IMEI Number'),
        ('serial', 'Serial Number'),
    )
    
    STATUS_CHOICES = (
        ('available', 'Available'),
        ('sold', 'Sold'),
        ('reserved', 'Reserved'),
        ('repair', 'Repair'),
    )
    
    # Product reference (Generic relationship)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    product = GenericForeignKey('content_type', 'object_id')
    
    # Or direct reference (simpler approach)
    phone = models.ForeignKey(Phone, on_delete=models.CASCADE, null=True, blank=True, related_name='units')
    electronic = models.ForeignKey(Electronic, on_delete=models.CASCADE, null=True, blank=True, related_name='units')
    
    # Unit details
    identifier = models.CharField(max_length=100, unique=True, db_index=True)
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES, default='imei')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Owner tracking
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='units')
    
    # Legacy owner fields
    owner_name = models.CharField(max_length=200, blank=True, null=True)
    owner_phone = models.CharField(max_length=20, blank=True, null=True)
    sold_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_units'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['identifier']),
            models.Index(fields=['phone', 'status']),
            models.Index(fields=['electronic', 'status']),
            models.Index(fields=['owner']),
        ]
    
    def __str__(self):
        return f"{self.identifier} ({self.status})"
    
    @property
    def product_name(self):
        if self.phone:
            return self.phone.name
        elif self.electronic:
            return self.electronic.name
        return "Unknown"
    
    @property
    def product_brand(self):
        if self.phone:
            return self.phone.brand
        elif self.electronic:
            return self.electronic.brand
        return "Unknown"
    
    @property
    def product_code(self):
        if self.phone:
            return self.phone.product_code
        elif self.electronic:
            return self.electronic.product_code
        return None


# ============================================
# SALE MODELS
# ============================================

class Sale(models.Model):
    """Sales transactions"""
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
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_sales')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='sales')
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    
    # Company-specific sale number (auto-incremented per company)
    sale_number = models.PositiveIntegerField(default=1, editable=False, help_text="Sequential number per company")
    company_sale_id = models.CharField(max_length=50, unique=True, blank=True, editable=False, help_text="Company prefix + sale number")
    
    # Denormalized customer info (snapshot at time of sale)
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True)
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD)
    
    sold_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='epa_sales_created')
    
    sale_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_sales'
        ordering = ['-sale_date']
        indexes = [
            models.Index(fields=['company', 'sale_date']),
            models.Index(fields=['branch', 'sale_date']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['company', 'sale_number']),  # Index for company-specific sale number
            models.Index(fields=['company_sale_id']),  # Index for the combined ID
        ]
        # Ensure sale_number is unique per company
        unique_together = [['company', 'sale_number']]
    
    def __str__(self):
        return f"Sale #{self.company_sale_id} - {self.customer_name} ({self.net_amount})"
    
    @property
    def item_count(self):
        return self.items.count()
    
    def save(self, *args, **kwargs):
        if not self.company_sale_id:
            # Get the last sale number for this company
            last_sale = Sale.objects.filter(company=self.company).order_by('-sale_number').first()
            
            if last_sale:
                self.sale_number = last_sale.sale_number + 1
            else:
                self.sale_number = 1
            
            # Create company-specific sale ID
            company_prefix = self.company.name[:3].upper() if self.company and self.company.name else "COM"
            self.company_sale_id = f"{company_prefix}-{str(self.sale_number).zfill(6)}"
        
        super().save(*args, **kwargs)


class SaleItem(models.Model):
    """Individual items in a sale using GenericForeignKey"""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to={
        'app_label': 'epa_shop',
        'model__in': ['electronic', 'phone', 'accessory']
    })
    object_id = models.PositiveIntegerField(db_index=True)
    item = GenericForeignKey('content_type', 'object_id')
    
    # Reference to the specific unit sold
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_items')
    
    # Denormalized data (snapshot at time of sale)
    item_name = models.CharField(max_length=200)
    item_sku = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'epa_sale_items'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['unit']),
        ]
    
    def __str__(self):
        return f"{self.quantity}x {self.item_name}"


# ============================================
# STOCK MOVEMENT
# ============================================

class StockMovement(models.Model):
    """Track all inventory movements (in/out)"""
    MOVEMENT_TYPES = (
        ('purchase', 'Purchase Order'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Branch Transfer'),
        ('damage', 'Damaged/Write-off'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_movements')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='stock_movements', null=True, blank=True)
    
    # Generic foreign key to product
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    product = GenericForeignKey('content_type', 'object_id')
    
    # Reference to specific unit
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()  # Positive for in, negative for out
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    
    # Reference to related records
    reference_id = models.CharField(max_length=100, blank=True)
    reference_model = models.CharField(max_length=50, blank=True)
    
    notes = models.TextField(blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'epa_stock_movements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'movement_type']),
            models.Index(fields=['branch', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['unit']),
        ]
    
    def __str__(self):
        return f"{self.movement_type}: {self.quantity} of {self.product}"

        

# ============================================
# PURCHASE ORDER
# ============================================

class PurchaseOrder(models.Model):
    """Purchase orders from suppliers"""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('partially_received', 'Partially Received'),
        ('cancelled', 'Cancelled'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_orders')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    
    order_number = models.CharField(max_length=50, unique=True)
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchase_orders_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_purchase_orders'
        ordering = ['-order_date']
    
    def __str__(self):
        return f"PO #{self.order_number} - {self.supplier.name}"


class PurchaseOrderItem(models.Model):
    """Items in a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    
    # Generic foreign key to product
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    product = GenericForeignKey('content_type', 'object_id')
    
    product_name = models.CharField(max_length=200)
    quantity_ordered = models.IntegerField()
    quantity_received = models.IntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_purchase_order_items'
    
    def __str__(self):
        return f"{self.quantity_ordered}x {self.product_name}"


# ============================================
# WARRANTY
# ============================================

class Warranty(models.Model):
    """Warranty tracking for products"""
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('claimed', 'Claimed'),
        ('void', 'Void'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='warranties')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='warranties')
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='warranties', null=True, blank=True)
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='warranties')
    
    # Generic foreign key to product
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    product = GenericForeignKey('content_type', 'object_id')
    
    # Reference to specific unit
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='warranties')
    
    product_name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, blank=True)
    
    warranty_number = models.CharField(max_length=50, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    terms_conditions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_warranties'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['end_date']),
            models.Index(fields=['unit']),
        ]
    
    def __str__(self):
        return f"Warranty #{self.warranty_number} - {self.product_name}"
    
    @property
    def is_expired(self):
        return timezone.now().date() > self.end_date


# ============================================
# REPAIR / SERVICE
# ============================================

class Repair(models.Model):
    """Product repair and service tracking"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('waiting_parts', 'Waiting for Parts'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='repairs')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='repairs')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='repairs')
    warranty = models.ForeignKey(Warranty, on_delete=models.SET_NULL, null=True, blank=True, related_name='repairs')
    
    # Generic foreign key to product
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    product = GenericForeignKey('content_type', 'object_id')
    
    # Reference to specific unit
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='repairs')
    
    product_name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, blank=True)
    
    repair_number = models.CharField(max_length=50, unique=True)
    issue_description = models.TextField()
    diagnosis = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=(
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ), default='medium')
    
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    received_date = models.DateTimeField(default=timezone.now)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_repairs')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_repairs')
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_repairs'
        ordering = ['-received_date']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['branch', 'status']),
            models.Index(fields=['unit']),
        ]
    
    def __str__(self):
        return f"Repair #{self.repair_number} - {self.product_name} ({self.status})"


# ============================================
# CUSTOMER MODELS
# ============================================

class Customer(models.Model):
    """Customer profiles for loyalty and tracking"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_customers')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='customers', null=True, blank=True)
    
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, db_index=True)  # REMOVED unique=True
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # === FIELDS ===
    id_number = models.CharField(max_length=50, blank=True, db_index=True, verbose_name="ID Number")
    next_of_keen_name = models.CharField(max_length=200, blank=True, verbose_name="Next of Keen Name")
    next_of_keen_phone = models.CharField(max_length=20, blank=True, verbose_name="Next of Keen Phone")
    # === END FIELDS ===
    
    total_purchases = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    visit_count = models.IntegerField(default=0)
    last_visit = models.DateTimeField(null=True, blank=True)
    
    # Loyalty
    loyalty_points = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'epa_customers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['phone']),
            models.Index(fields=['id_number']),
            models.Index(fields=['company', 'phone']),  # Index for faster lookups
        ]
        # DO NOT use unique_together - customers can have multiple purchases
    
    def __str__(self):
        return f"{self.name} ({self.phone})"
    
    @property
    def full_name(self):
        return self.name
    
    @property
    def customer_id(self):
        return self.id_number or '-'



# ============================================
# COGS ACCOUNT MODEL
# ============================================

class COGSAccount(models.Model):
    """
    Main COGS account that tracks the balance of Cost of Goods Sold.
    This account receives COGS from sales and is debited when purchases are made.
    """
    ACCOUNT_TYPES = (
        ('main', 'Main COGS Account'),
        ('branch', 'Branch COGS Account'),
        ('product', 'Product Category Account'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_accounts')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cogs_accounts', null=True, blank=True)
    
    account_name = models.CharField(max_length=200)
    account_code = models.CharField(max_length=50, unique=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='main')
    
    # Balance tracking
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_credited = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # From sales
    total_debited = models.DecimalField(max_digits=15, decimal_places=2, default=0)   # From purchases
    
    # Metadata
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'finance_cogs_accounts'
        ordering = ['account_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['account_code']),
        ]
    
    def __str__(self):
        return f"{self.account_code} - {self.account_name} (Balance: {self.current_balance})"
    
    @property
    def available_balance(self):
        """Available balance that can be used for purchases"""
        return self.current_balance
    
    def credit(self, amount, description="", reference=None, created_by=None):
        """Add COGS from sales (credit the account)"""
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        
        self.current_balance += amount
        self.total_credited += amount
        self.save()
        
        # Create transaction record
        return COGSTransaction.objects.create(
            company=self.company,
            branch=self.branch,
            cogs_account=self,
            transaction_type='credit',
            amount=amount,
            balance_after=self.current_balance,
            description=description or f"COGS credited from sales",
            reference=reference,
            created_by=created_by
        )
    
    def debit(self, amount, description="", reference=None, created_by=None):
        """Use COGS for purchases (debit the account)"""
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        
        if self.current_balance < amount:
            raise ValueError(f"Insufficient COGS balance. Available: {self.current_balance}, Required: {amount}")
        
        self.current_balance -= amount
        self.total_debited += amount
        self.save()
        
        # Create transaction record
        return COGSTransaction.objects.create(
            company=self.company,
            branch=self.branch,
            cogs_account=self,
            transaction_type='debit',
            amount=amount,
            balance_after=self.current_balance,
            description=description or f"COGS used for purchases",
            reference=reference,
            created_by=created_by
        )


# ============================================
# COGS TRANSACTION MODEL
# ============================================

class COGSTransaction(models.Model):
    """
    Individual transaction entries for COGS account
    """
    TRANSACTION_TYPES = (
        ('credit', 'Credit (From Sales)'),
        ('debit', 'Debit (Used for Purchases)'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Transfer'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_transactions')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cogs_transactions', null=True, blank=True)
    cogs_account = models.ForeignKey(COGSAccount, on_delete=models.CASCADE, related_name='transactions')
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Reference to source
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='cogs_transactions')
    # REMOVED: purchase_record field - we'll use the reverse from PurchaseRecord
    
    # Description and metadata
    description = models.TextField()
    reference = models.CharField(max_length=200, blank=True, null=True)
    notes = models.TextField(blank=True)
    
    # User who created
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cogs_transactions')
    
    # Date tracking
    transaction_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'finance_cogs_transactions'
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['company', 'transaction_date']),
            models.Index(fields=['cogs_account', 'transaction_date']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['sale']),
        ]
    
    def __str__(self):
        return f"{self.transaction_type}: {self.amount} - {self.description[:50]}"

# ============================================
# PURCHASE RECORD MODEL
# ============================================
class PurchaseRecord(models.Model):
    """
    Records of purchases made using COGS balance
    """
    PURCHASE_TYPES = (
        ('inventory', 'Inventory Purchase'),
        ('supplies', 'Supplies'),
        ('equipment', 'Equipment'),
        ('maintenance', 'Maintenance'),
        ('other', 'Other'),
    )
    
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('m-pesa', 'M-Pesa'),
        ('cheque', 'Cheque'),
        ('credit', 'Credit'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_records')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='purchase_records')
    # FIXED: Allow null and blank for cogs_account
    cogs_account = models.ForeignKey(
        COGSAccount, 
        on_delete=models.SET_NULL,  # Changed from CASCADE to SET_NULL
        null=True,  # Allow null
        blank=True,  # Allow blank in forms
        related_name='purchases'
    )
    cogs_transaction = models.ForeignKey(
        COGSTransaction, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='purchase_record'
    )
    
    # Purchase details
    purchase_number = models.CharField(max_length=50, unique=True)
    purchase_type = models.CharField(max_length=20, choices=PURCHASE_TYPES)
    purchase_date = models.DateField(default=timezone.now)
    
    # Amount
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Supplier/vendor
    supplier_name = models.CharField(max_length=200)
    supplier_contact = models.CharField(max_length=100, blank=True)
    supplier_phone = models.CharField(max_length=20, blank=True)
    
    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    
    # Description
    description = models.TextField()
    notes = models.TextField(blank=True)
    
    # Status
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Receipt/document
    receipt_image = models.ImageField(upload_to='finance/purchases/%Y/%m/', blank=True, null=True)
    receipt_number = models.CharField(max_length=100, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchase_records')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_purchases')
    approved_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'finance_purchase_records'
        ordering = ['-purchase_date']
        indexes = [
            models.Index(fields=['company', 'purchase_date']),
            models.Index(fields=['branch', 'purchase_date']),
            models.Index(fields=['status']),
            models.Index(fields=['purchase_number']),
        ]
    
    def __str__(self):
        return f"Purchase #{self.purchase_number} - {self.supplier_name} ({self.total_amount})"
    
    def save(self, *args, **kwargs):
        if not self.purchase_number:
            # Generate purchase number: PUR-YYYYMMDD-XXXX
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
            last_purchase = PurchaseRecord.objects.filter(
                company=self.company,
                purchase_number__startswith=f'PUR-{date_str}'
            ).order_by('-purchase_number').first()
            
            if last_purchase:
                last_num = int(last_purchase.purchase_number.split('-')[-1])
                next_num = last_num + 1
            else:
                next_num = 1
            
            self.purchase_number = f"PUR-{date_str}-{str(next_num).zfill(4)}"
        
        super().save(*args, **kwargs)
    
    def approve(self, user):
        """Approve the purchase"""
        self.status = 'completed'
        self.approved_by = user
        self.approved_date = timezone.now()
        self.save()

# ============================================
# COGS ALLOCATION RULES
# ============================================

class COGSAllocationRule(models.Model):
    """
    Rules for how COGS should be allocated from sales to accounts
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_rules')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cogs_rules', null=True, blank=True)
    
    rule_name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    
    # Allocation percentage per product type
    electronics_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    phones_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    accessories_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    
    # Target account for each type
    electronics_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='electronics_rules')
    phones_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones_rules')
    accessories_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='accessories_rules')
    
    # Default account for unspecified types
    default_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='default_rules')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'finance_cogs_allocation_rules'
    
    def __str__(self):
        return f"{self.rule_name} ({'Active' if self.is_active else 'Inactive'})"


# ============================================
# COGS SUMMARY BY PERIOD
# ============================================

class COGSSummary(models.Model):
    """
    Periodic summary of COGS activity
    """
    PERIOD_TYPES = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_summaries')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cogs_summaries', null=True, blank=True)
    cogs_account = models.ForeignKey(COGSAccount, on_delete=models.CASCADE, related_name='summaries')
    
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES)
    period_start = models.DateField()
    period_end = models.DateField()
    
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    total_credits = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # From sales
    total_debits = models.DecimalField(max_digits=15, decimal_places=2, default=0)   # From purchases
    net_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    transaction_count = models.IntegerField(default=0)
    sale_count = models.IntegerField(default=0)
    purchase_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'finance_cogs_summaries'
        ordering = ['-period_start']
        unique_together = ['company', 'cogs_account', 'period_type', 'period_start']
    
    def __str__(self):
        return f"{self.cogs_account.account_name} - {self.period_type} ({self.period_start} to {self.period_end})"


        