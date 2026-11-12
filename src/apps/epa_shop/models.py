from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.conf import settings
from django.conf import settings as django_settings
from apps.companies.models import Company
from decimal import Decimal


User = get_user_model()


# ============================================
# HELPER — build Cloudinary URL from a public_id
# ============================================

def _build_cloudinary_url(field_value, resource_type='image'):
    if not field_value:
        return None
    key = getattr(field_value, 'name', None) or str(field_value)
    key = key.strip().lstrip('/')
    if not key:
        return None
    if key.startswith('media/'):
        key = key[len('media/'):]
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    cloud_name = cfg.get('CLOUD_NAME', '')
    if cloud_name:
        return f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/{key}"
    media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
    if not media_url.endswith('/'):
        media_url += '/'
    return f"{media_url}{key}"


# ============================================
# PRODUCT CATEGORIES
# ============================================

class Category(models.Model):
    CATEGORY_TYPES = (
        ('electronics', 'Electronics'),
        ('phones', 'Phones'),
        ('accessories', 'Accessories'),
        ('parts', 'Parts & Components'),
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_categories')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='categories', null=True, blank=True)
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
# SUPPLIER
# ============================================

class Supplier(models.Model):
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
# OWNER
# ============================================

class Owner(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_owners')
    branch = models.ForeignKey('company.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='owners')
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    id_number = models.CharField(max_length=50, blank=True, verbose_name="ID Number")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=(('male', 'Male'), ('female', 'Female'), ('other', 'Other')), blank=True)
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
# BASE PRODUCT
# ============================================

class BaseProduct(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    product_code = models.CharField(max_length=20, db_index=True, unique=False, null=True, blank=True)
    barcode = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        abstract = True

    def get_company_prefix(self):
        if self.company and self.company.name:
            return self.company.name[0].upper()
        return "X"

    def generate_unique_product_code(self):
        from .models import Phone, Electronic, Accessory
        prefix = self.get_company_prefix()
        all_existing_codes = set()
        for model in [Phone, Electronic, Accessory]:
            codes = model.objects.filter(company=self.company).exclude(product_code__isnull=True).exclude(product_code='').values_list('product_code', flat=True)
            all_existing_codes.update(codes)
        existing_numbers = []
        for code in all_existing_codes:
            if code and code.startswith(prefix):
                try:
                    num_str = code.replace(prefix, '')
                    if num_str.isdigit():
                        existing_numbers.append(int(num_str))
                except (ValueError, TypeError):
                    pass
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
        skip_auto_generate = kwargs.pop('skip_auto_generate', False)
        if skip_auto_generate:
            super().save(*args, **kwargs)
            return
        if not self.product_code:
            for _ in range(20):
                new_code = self.generate_unique_product_code()
                from .models import Phone, Electronic, Accessory
                code_exists = False
                for model in [Phone, Electronic, Accessory]:
                    if model.objects.filter(company=self.company, product_code=new_code).exclude(pk=self.pk).exists():
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

    def stock_at(self, branch):
        return self.branch_stocks.filter(branch=branch).first()

    def available_at(self, branch):
        s = self.stock_at(branch)
        return s.quantity_in_stock if s else 0

    def total_stock(self):
        return self.branch_stocks.aggregate(t=__import__('django.db.models', fromlist=['Sum']).Sum('quantity_in_stock'))['t'] or 0


# ============================================
# BRANCH STOCK (Fully fixed for SQLite)
# ============================================

class BranchStock(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branch_stocks')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='branch_stocks')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    product = GenericForeignKey('content_type', 'object_id')
    quantity_in_stock = models.IntegerField(default=0)
    minimum_stock_level = models.IntegerField(default=2)
    maximum_stock_level = models.IntegerField(default=100, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_branch_stocks'

    def __str__(self):
        return f"{self.product} @ {self.branch}: {self.quantity_in_stock}"

# ============================================
# STOCK TRANSFER (Fully fixed for SQLite)
# ============================================

# ============================================
# STOCK TRANSFER (Fully fixed for SQLite)
# ============================================

class StockTransfer(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='stock_transfers'
    )
    from_branch = models.ForeignKey(
        'company.Branch', on_delete=models.CASCADE,
        related_name='stock_transfers_from'
    )
    to_branch = models.ForeignKey(
        'company.Branch', on_delete=models.CASCADE,
        related_name='stock_transfers_to'
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    product = GenericForeignKey('content_type', 'object_id')
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    transfer_number = models.CharField(
        max_length=50, unique=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='stock_transfers_created'
    )
    completed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_transfers_completed'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'epa_stock_transfers'
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"Transfer {self.transfer_number or '—'}: "
            f"{self.quantity}× {self.product} → {self.to_branch}"
        )

    # ------------------------------------------------------------
    # Auto-generate transfer_number
    # ------------------------------------------------------------
    # Mirrors PurchaseRecord.save(): a per-company, per-day sequence
    # like TRF-20260112-0001, TRF-20260112-0002, ...
    #
    # Wrapped in a bounded retry loop because two concurrent saves
    # can read the same "last" row and compute the same next number.
    # The UNIQUE constraint catches the loser and we retry with the
    # next number. This is the only reliable approach on SQLite,
    # which has no row-level locking for select_for_update().
    # ------------------------------------------------------------
    def save(self, *args, **kwargs):
        if self.transfer_number:
            # Already set — normal save, no generation needed.
            return super().save(*args, **kwargs)

        from datetime import datetime
        from django.db import IntegrityError

        date_str = datetime.now().strftime('%Y%m%d')
        prefix = f'TRF-{date_str}-'

        last_error = None
        for attempt in range(10):
            last = (
                StockTransfer.objects
                .filter(
                    company=self.company,
                    transfer_number__startswith=prefix,
                )
                .order_by('-transfer_number')
                .first()
            )

            next_num = 1
            if last:
                try:
                    next_num = (
                        int(last.transfer_number.rsplit('-', 1)[-1]) + 1 + attempt
                    )
                except (ValueError, IndexError):
                    # Malformed existing number — start from attempt+1
                    next_num = 1 + attempt

            self.transfer_number = f"{prefix}{str(next_num).zfill(4)}"

            try:
                return super().save(*args, **kwargs)
            except IntegrityError as exc:
                # Another worker grabbed this number; try the next one.
                last_error = exc
                self.transfer_number = ''
                continue

        # Exhausted retries — surface the last error cleanly.
        raise last_error

        
# ============================================
# PHONE
# ============================================

class Phone(BaseProduct):
    CONDITION_CHOICES = (('new', 'New'), ('used', 'Used'), ('refurbished', 'Refurbished'))
    PHONE_TYPE_CHOICES = (('smartphone', 'Smartphone'), ('feature', 'Feature Phone'))
    NETWORK_CHOICES = (('2g', '2G'), ('3g', '3G'), ('4g', '4G'), ('dual_sim', 'Dual SIM'))
    MEMORY_CARD_CHOICES = (('yes', 'Yes'), ('no', 'No'))

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_phone_products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='phones')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones')

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    imei = models.CharField(max_length=15, db_index=True, null=True, blank=True)
    color = models.CharField(max_length=50)
    storage_capacity = models.CharField(max_length=50)
    ram = models.CharField(max_length=20)
    screen_size = models.CharField(max_length=20)
    battery_capacity = models.CharField(max_length=20)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    best_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    total_quantity_in_stock = models.IntegerField(default=0)

    image = models.ImageField(upload_to='epa/phones/%Y/%m/', blank=True, null=True, max_length=500)
    warranty_period_months = models.IntegerField(default=12)
    warranty_expiry = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones')
    phone_type = models.CharField(max_length=20, choices=PHONE_TYPE_CHOICES, default='smartphone')
    network_type = models.CharField(max_length=20, choices=NETWORK_CHOICES, blank=True, null=True)
    memory_card = models.CharField(max_length=10, choices=MEMORY_CARD_CHOICES, default='no')
    features = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    sale_items = GenericRelation('SaleItem', content_type_field='content_type', object_id_field='object_id')
    branch_stocks = GenericRelation('BranchStock', content_type_field='content_type', object_id_field='object_id', related_query_name='phone')

    class Meta:
        db_table = 'epa_phones'
        ordering = ['-created_at']
        unique_together = ['company', 'product_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['imei']),
            models.Index(fields=['owner']),
            models.Index(fields=['product_code']),
            models.Index(fields=['company', 'barcode']),
        ]

    def __str__(self):
        return f"{self.product_code} - {self.brand} {self.model}"

    @property
    def image_url(self):
        return _build_cloudinary_url(self.image, resource_type='image')


# ============================================
# ELECTRONIC
# ============================================

class Electronic(BaseProduct):
    TYPE_CHOICES = (
        ('laptop', 'Laptop'), ('desktop', 'Desktop'), ('tablet', 'Tablet'), ('monitor', 'Monitor'),
        ('printer', 'Printer'), ('camera', 'Camera'), ('audio', 'Audio Equipment'), ('other', 'Other'),
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_electronic_products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='electronics')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='electronics')

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    model_number = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    device_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    processor = models.CharField(max_length=200, blank=True)
    ram = models.CharField(max_length=50, blank=True)
    storage = models.CharField(max_length=100, blank=True)
    screen_size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=50, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    best_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    total_quantity_in_stock = models.IntegerField(default=0)

    image = models.ImageField(upload_to='epa/electronics/%Y/%m/', blank=True, null=True, max_length=500)
    warranty_period_months = models.IntegerField(default=12)
    warranty_expiry = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='electronics')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    sale_items = GenericRelation('SaleItem', content_type_field='content_type', object_id_field='object_id')
    branch_stocks = GenericRelation('BranchStock', content_type_field='content_type', object_id_field='object_id', related_query_name='electronic')

    class Meta:
        db_table = 'epa_electronics'
        ordering = ['-created_at']
        unique_together = ['company', 'product_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['serial_number']),
            models.Index(fields=['owner']),
            models.Index(fields=['product_code']),
            models.Index(fields=['company', 'barcode']),
        ]

    def __str__(self):
        return f"{self.product_code} - {self.brand} {self.name}"

    @property
    def image_url(self):
        return _build_cloudinary_url(self.image, resource_type='image')


# ============================================
# ACCESSORY
# ============================================

class Accessory(BaseProduct):
    ACCESSORY_TYPES = (('electronic accessory', 'Electronic Accessory'), ('phone accessory', 'Phone Accessory'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_accessory_products')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='accessories')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='accessories')

    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    accessory_type = models.CharField(max_length=20, choices=ACCESSORY_TYPES)
    model = models.CharField(max_length=100, blank=True)
    compatible_phone_models = models.TextField(help_text="Comma-separated list of phone models", blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    best_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    total_quantity_in_stock = models.IntegerField(default=0)

    image = models.ImageField(upload_to='epa/accessories/%Y/%m/', blank=True, null=True, max_length=500)
    warranty_period_months = models.IntegerField(default=6)
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='accessories')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    sale_items = GenericRelation('SaleItem', content_type_field='content_type', object_id_field='object_id')
    branch_stocks = GenericRelation('BranchStock', content_type_field='content_type', object_id_field='object_id', related_query_name='accessory')

    class Meta:
        db_table = 'epa_accessories'
        ordering = ['-created_at']
        unique_together = ['company', 'product_code']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['owner']),
            models.Index(fields=['product_code']),
            models.Index(fields=['company', 'barcode']),
        ]

    def __str__(self):
        return f"{self.product_code} - {self.brand} {self.name}"

    @property
    def image_url(self):
        return _build_cloudinary_url(self.image, resource_type='image')


# ============================================
# UNIT
# ============================================

class Unit(models.Model):
    UNIT_TYPES = (('imei', 'IMEI Number'), ('serial', 'Serial Number'))
    STATUS_CHOICES = (('available', 'Available'), ('sold', 'Sold'), ('reserved', 'Reserved'), ('repair', 'Repair'))

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    product = GenericForeignKey('content_type', 'object_id')

    phone = models.ForeignKey(Phone, on_delete=models.CASCADE, null=True, blank=True, related_name='units')
    electronic = models.ForeignKey(Electronic, on_delete=models.CASCADE, null=True, blank=True, related_name='units')
    branch = models.ForeignKey('company.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='units')

    identifier = models.CharField(max_length=100, unique=True, db_index=True)
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPES, default='imei')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name='units')
    owner_name = models.CharField(max_length=200, blank=True, null=True)
    owner_phone = models.CharField(max_length=20, blank=True, null=True)
    sold_date = models.DateTimeField(null=True, blank=True)
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
            models.Index(fields=['branch', 'status']),
        ]

    def __str__(self):
        return f"{self.identifier} ({self.status})"


# ============================================
# SALE
# ============================================

class Sale(models.Model):
    PAYMENT_STATUS = (('pending', 'Pending'), ('paid', 'Paid'), ('partially_paid', 'Partially Paid'), ('refunded', 'Refunded'))
    PAYMENT_METHOD = (('cash', 'Cash'), ('m-pesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer'), ('card', 'Card'), ('credit', 'Credit'))

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_sales')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='sales')
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')

    sale_number = models.PositiveIntegerField(default=1, editable=False)
    company_sale_id = models.CharField(max_length=50, unique=True, blank=True, editable=False)
    barcode_number = models.CharField(max_length=50, unique=True, null=True, blank=True, db_index=True, editable=False)

    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    cogs_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

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
            models.Index(fields=['company', 'sale_number']),
            models.Index(fields=['company_sale_id']),
            models.Index(fields=['barcode_number']),
        ]
        unique_together = [['company', 'sale_number']]

    def __str__(self):
        return f"Sale #{self.company_sale_id} - {self.customer_name}"

    def save(self, *args, **kwargs):
        # 1. If we're creating a new sale, auto-generate the sale_number
        if self._state.adding:
            last_sale = Sale.objects.filter(company=self.company).order_by('-sale_number').first()
            self.sale_number = (last_sale.sale_number + 1) if last_sale else 1

        # 2. Always generate company_sale_id from the actual sale_number
        self.company_sale_id = f"SALE-{str(self.sale_number).zfill(5)}"

        # 3. Auto-generate the scannable barcode (BAR-000001 matching the sale_number)
        if not self.barcode_number:
            self.barcode_number = f"BAR-{str(self.sale_number).zfill(6)}"

        # 4. Retry loop to handle race conditions
        from django.db import IntegrityError
        for attempt in range(5):
            try:
                super().save(*args, **kwargs)
                return  # ✅ Success
            except IntegrityError:
                # Number collision — bump and retry
                self.sale_number += 1
                self.company_sale_id = f"SALE-{str(self.sale_number).zfill(5)}"
                self.barcode_number = f"BAR-{str(self.sale_number).zfill(6)}"
                if attempt == 4:
                    raise  # Give up after 5 tries

    @property
    def item_count(self):
        """Total number of items (sum of quantities) across all sale lines."""
        from django.db.models import Sum
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to={'app_label': 'epa_shop', 'model__in': ['electronic', 'phone', 'accessory']})
    object_id = models.PositiveIntegerField(db_index=True)
    item = GenericForeignKey('content_type', 'object_id')
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_items')

    item_name = models.CharField(max_length=200)
    item_sku = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cogs_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'epa_sale_items'
        indexes = [models.Index(fields=['content_type', 'object_id']), models.Index(fields=['unit'])]


class ReturnItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='returns')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, related_name='return_items')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    refund_method = models.CharField(max_length=30, default='cash')
    reason = models.CharField(max_length=255, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-processed_at']

    def __str__(self):
        return f'Return #{self.id} — Sale #{self.sale_id} — {self.quantity}×'

# ============================================
# STOCK MOVEMENT
# ============================================

class StockMovement(models.Model):
    MOVEMENT_TYPES = (('purchase', 'Purchase Order'), ('sale', 'Sale'), ('return', 'Return'), ('adjustment', 'Adjustment'), ('transfer', 'Branch Transfer'), ('damage', 'Damaged/Write-off'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_movements')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='stock_movements', null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    product = GenericForeignKey('content_type', 'object_id')
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')

    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reference_id = models.CharField(max_length=100, blank=True)
    reference_model = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'epa_stock_movements'
        ordering = ['-created_at']

    @property
    def product_name(self):
        if self.product:
            # Try 'name' (Phones/Electronics/Accessories)
            if hasattr(self.product, 'name'):
                return self.product.name
            # Try 'display_name' (some apps use this)
            if hasattr(self.product, 'display_name'):
                return self.product.display_name
            # Fallback to string representation
            return str(self.product)
        return "Unknown Product"

    @property
    def product_code(self):
        if self.product:
            # Try 'product_code' (Phones/Electronics/Accessories)
            if hasattr(self.product, 'product_code'):
                return self.product.product_code or f"ID: {self.object_id}"
            # Fallback to the object's PK
            return f"ID: {self.object_id}"
        return "-"

# ============================================
# PURCHASE ORDER
# ============================================

class PurchaseOrder(models.Model):
    STATUS_CHOICES = (('draft', 'Draft'), ('ordered', 'Ordered'), ('received', 'Received'), ('partially_received', 'Partially Received'), ('cancelled', 'Cancelled'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_orders')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='purchase_orders')
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


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
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


# ============================================
# WARRANTY
# ============================================

class Warranty(models.Model):
    STATUS_CHOICES = (('active', 'Active'), ('expired', 'Expired'), ('claimed', 'Claimed'), ('void', 'Void'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='warranties')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='warranties')
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='warranties', null=True, blank=True)
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='warranties')

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    product = GenericForeignKey('content_type', 'object_id')
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


# ============================================
# REPAIR
# ============================================

class Repair(models.Model):
    STATUS_CHOICES = (('pending', 'Pending'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('waiting_parts', 'Waiting for Parts'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='repairs')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='repairs')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='repairs')
    warranty = models.ForeignKey(Warranty, on_delete=models.SET_NULL, null=True, blank=True, related_name='repairs')

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    product = GenericForeignKey('content_type', 'object_id')
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='repairs')

    product_name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, blank=True)
    repair_number = models.CharField(max_length=50, unique=True)
    issue_description = models.TextField()
    diagnosis = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=(('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')), default='medium')
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


# ============================================
# CUSTOMER
# ============================================

class Customer(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='epa_customers')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='customers', null=True, blank=True)
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    id_number = models.CharField(max_length=50, blank=True, db_index=True)
    next_of_keen_name = models.CharField(max_length=200, blank=True)
    next_of_keen_phone = models.CharField(max_length=20, blank=True)
    total_purchases = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    visit_count = models.IntegerField(default=0)
    last_visit = models.DateTimeField(null=True, blank=True)
    loyalty_points = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_customers'


# ============================================
# COGS
# ============================================

class COGSAccount(models.Model):
    ACCOUNT_TYPES = (
        ('main', 'Main COGS Account'),
        ('branch', 'Branch COGS Account'),
        ('product', 'Product Category Account'),
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_accounts')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='cogs_accounts', null=True, blank=True)
    account_name = models.CharField(max_length=200)
    account_code = models.CharField(max_length=50, unique=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='main')
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_credited = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_debited = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'finance_cogs_accounts'
        ordering = ['account_code']

    def __str__(self):
        return f"{self.account_code} - {self.account_name} (Balance: {self.current_balance})"

    def credit(self, amount, description="", reference=None, created_by=None):
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        self.current_balance += amount
        self.total_credited += amount
        self.save()
        return COGSTransaction.objects.create(
            company=self.company, branch=self.branch, cogs_account=self,
            transaction_type='credit', amount=amount,
            balance_after=self.current_balance,
            description=description or "COGS credited from sales",
            reference=reference, created_by=created_by,
        )

    def debit(self, amount, description="", reference=None, created_by=None):
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        if self.current_balance < amount:
            raise ValueError(f"Insufficient COGS balance. Available: {self.current_balance}, Required: {amount}")
        self.current_balance -= amount
        self.total_debited += amount
        self.save()
        return COGSTransaction.objects.create(
            company=self.company, branch=self.branch, cogs_account=self,
            transaction_type='debit', amount=amount,
            balance_after=self.current_balance,
            description=description or "COGS used for purchases",
            reference=reference, created_by=created_by,
        )


class COGSTransaction(models.Model):
    TRANSACTION_TYPES = (('credit', 'Credit (From Sales)'), ('debit', 'Debit (Used for Purchases)'), ('adjustment', 'Adjustment'), ('transfer', 'Transfer'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_transactions')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='cogs_transactions', null=True, blank=True)
    cogs_account = models.ForeignKey(COGSAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='cogs_transactions')
    description = models.TextField()
    reference = models.CharField(max_length=200, blank=True, null=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='cogs_transactions')
    transaction_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_cogs_transactions'
        ordering = ['-transaction_date']


class PurchaseRecord(models.Model):
    PURCHASE_TYPES = (('inventory', 'Inventory Purchase'), ('supplies', 'Supplies'), ('equipment', 'Equipment'), ('maintenance', 'Maintenance'), ('other', 'Other'))
    PAYMENT_METHODS = (('cash', 'Cash'), ('bank_transfer', 'Bank Transfer'), ('m-pesa', 'M-Pesa'), ('cheque', 'Cheque'), ('credit', 'Credit'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_records')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='purchase_records')
    cogs_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    cogs_transaction = models.ForeignKey(COGSTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_record')
    purchase_number = models.CharField(max_length=50, unique=True)
    purchase_type = models.CharField(max_length=20, choices=PURCHASE_TYPES)
    purchase_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    supplier_name = models.CharField(max_length=200)
    supplier_contact = models.CharField(max_length=100, blank=True)
    supplier_phone = models.CharField(max_length=20, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    description = models.TextField()
    notes = models.TextField(blank=True)
    STATUS_CHOICES = (('pending', 'Pending'), ('completed', 'Completed'), ('cancelled', 'Cancelled'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    receipt_image = models.ImageField(upload_to='finance/purchases/%Y/%m/', blank=True, null=True, max_length=500)
    receipt_number = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchase_records')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_purchases')
    approved_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'finance_purchase_records'
        ordering = ['-purchase_date']

    def __str__(self):
        return f"Purchase #{self.purchase_number} - {self.supplier_name} ({self.total_amount})"

    def save(self, *args, **kwargs):
        if not self.purchase_number:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
            last_purchase = PurchaseRecord.objects.filter(
                company=self.company,
                purchase_number__startswith=f'PUR-{date_str}',
            ).order_by('-purchase_number').first()
            next_num = int(last_purchase.purchase_number.split('-')[-1]) + 1 if last_purchase else 1
            self.purchase_number = f"PUR-{date_str}-{str(next_num).zfill(4)}"
        super().save(*args, **kwargs)

    def approve(self, user):
        self.status = 'completed'
        self.approved_by = user
        self.approved_date = timezone.now()
        self.save()

    @property
    def receipt_image_url(self):
        return _build_cloudinary_url(self.receipt_image, resource_type='image')


class COGSAllocationRule(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_rules')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='cogs_rules', null=True, blank=True)
    rule_name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    electronics_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    phones_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    accessories_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    electronics_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='electronics_rules')
    phones_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='phones_rules')
    accessories_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='accessories_rules')
    default_account = models.ForeignKey(COGSAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='default_rules')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'finance_cogs_allocation_rules'

    def __str__(self):
        return f"{self.rule_name} ({'Active' if self.is_active else 'Inactive'})"


class COGSSummary(models.Model):
    PERIOD_TYPES = (('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('yearly', 'Yearly'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cogs_summaries')
    branch = models.ForeignKey('company.Branch', on_delete=models.CASCADE, related_name='cogs_summaries', null=True, blank=True)
    cogs_account = models.ForeignKey(COGSAccount, on_delete=models.CASCADE, related_name='summaries')
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES)
    period_start = models.DateField()
    period_end = models.DateField()
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    total_credits = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_debits = models.DecimalField(max_digits=15, decimal_places=2, default=0)
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