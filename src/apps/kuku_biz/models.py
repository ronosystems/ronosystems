"""
Kuku Biz — Poultry Farming Models

Supports:
- Layer hens (egg production)
- Broilers (meat production)
- Multiple concurrent flocks
- Per-flock egg tracking
- Egg sales in trays, crates, or individual eggs
- Feed, health, mortality, expenses
- Inventory and price tracking
- Branch-scoped records (per farm / depot)
- Multi-tenant (each record belongs to a Company)
"""

from decimal import Decimal, InvalidOperation

from django.db import models
from django.conf import settings
from django.utils import timezone


User = settings.AUTH_USER_MODEL


# ============================================================
# CHOICES
# ============================================================

FLOCK_TYPE_CHOICES = [
    ('layer', 'Layers (Egg Production)'),
    ('broiler', 'Broilers (Meat Production)'),
    ('mixed', 'Mixed'),
]

FLOCK_STATUS_CHOICES = [
    ('active', 'Active'),
    ('retired', 'Retired'),
    ('sold', 'Sold'),
    ('depleted', 'Depleted'),
]

EGG_UNIT_CHOICES = [
    ('egg', 'Individual Egg'),
    ('tray', 'Tray (30 eggs)'),
    ('crate', 'Crate (360 eggs)'),
]

SALE_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('paid', 'Paid'),
    ('partial', 'Partially Paid'),
    ('credit', 'On Credit'),
    ('cancelled', 'Cancelled'),
]

HEALTH_TYPE_CHOICES = [
    ('vaccination', 'Vaccination'),
    ('treatment', 'Treatment'),
    ('deworming', 'Deworming'),
    ('vitamin', 'Vitamin / Supplement'),
    ('vet_visit', 'Vet Visit'),
    ('other', 'Other'),
]

MORTALITY_CAUSE_CHOICES = [
    ('disease', 'Disease'),
    ('predator', 'Predator'),
    ('culled', 'Culled'),
    ('accident', 'Accident'),
    ('unknown', 'Unknown'),
]

EXPENSE_CATEGORY_CHOICES = [
    ('feed', 'Feed'),
    ('labour', 'Labour'),
    ('utilities', 'Utilities'),
    ('equipment', 'Equipment'),
    ('transport', 'Transport'),
    ('veterinary', 'Veterinary'),
    ('chicks', 'Chick Purchase'),
    ('other', 'Other'),
]

INVENTORY_ITEM_TYPE_CHOICES = [
    ('egg_tray', 'Egg Tray'),
    ('egg_crate', 'Egg Crate'),
    ('feed_bag', 'Feed Bag'),
    ('medicine', 'Medicine'),
    ('equipment', 'Equipment'),
    ('other', 'Other'),
]


# ============================================================
# HELPERS
# ============================================================

def _to_decimal(value, default='0'):
    """
    Safely convert any value to Decimal.

    Handles: None, empty string, strings with commas, currency symbols,
    already-Decimal, int, float. Falls back to `default` on any error.
    """
    if value is None or value == '':
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        clean = str(value).strip().replace(',', '').replace('KES', '').strip()
        if not clean:
            return Decimal(default)
        return Decimal(clean)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


# ============================================================
# FLOCK
# ============================================================

class Flock(models.Model):
    """
    A batch of birds. You can have as many flocks as you want.

    Example:
      - "Batch A - Layers 2026 Q1"  (type=layer, count=500)
      - "Batch B - Broilers Mar"    (type=broiler, count=300)
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_flocks',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_flocks',
        help_text="Which branch/farm houses this flock",
    )
    name = models.CharField(max_length=100)
    flock_type = models.CharField(
        max_length=20, choices=FLOCK_TYPE_CHOICES, default='layer'
    )
    breed = models.CharField(
        max_length=100, blank=True,
        help_text="e.g. Isa Brown, Kuroiler, Kenbro",
    )

    date_acquired = models.DateField(default=timezone.now)
    initial_count = models.PositiveIntegerField(default=0)
    current_count = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20, choices=FLOCK_STATUS_CHOICES, default='active'
    )
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_flocks_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_acquired', 'name']
        verbose_name = 'Flock'
        verbose_name_plural = 'Flocks'

    def __str__(self):
        return f"{self.name} ({self.get_flock_type_display()})"

    # ---------- Computed ----------

    @property
    def age_in_days(self):
        return (timezone.now().date() - self.date_acquired).days

    @property
    def age_in_weeks(self):
        return self.age_in_days // 7

    @property
    def mortality_count(self):
        return max(self.initial_count - self.current_count, 0)

    @property
    def mortality_rate(self):
        if not self.initial_count:
            return 0
        return round((self.mortality_count / self.initial_count) * 100, 2)


# ============================================================
# EGG PRODUCTION (daily, per flock)
# ============================================================

class EggProduction(models.Model):
    """
    Daily egg collection record per flock.

    One row per (flock, date).
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_egg_production',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_egg_production',
        help_text="Which branch produced these eggs",
    )
    flock = models.ForeignKey(
        Flock, on_delete=models.CASCADE,
        related_name='egg_production',
    )
    date = models.DateField(default=timezone.now)

    eggs_collected = models.PositiveIntegerField(default=0)
    eggs_cracked = models.PositiveIntegerField(default=0)
    eggs_broken = models.PositiveIntegerField(default=0)
    eggs_consumed = models.PositiveIntegerField(
        default=0, help_text="Kept for home/farm use"
    )
    eggs_discarded = models.PositiveIntegerField(default=0)

    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_egg_records',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'flock__name']
        unique_together = [('flock', 'date')]
        verbose_name = 'Egg Production'
        verbose_name_plural = 'Egg Production'

    def __str__(self):
        return f"{self.flock.name} — {self.date} — {self.eggs_collected} eggs"

    @property
    def good_eggs(self):
        """Eggs that are good for sale."""
        return self.eggs_collected - self.eggs_cracked - self.eggs_broken

    @property
    def lay_rate(self):
        """Percentage of hens that laid an egg this day."""
        if not self.flock.current_count:
            return 0
        return round((self.eggs_collected / self.flock.current_count) * 100, 2)


# ============================================================
# CUSTOMERS
# ============================================================

class Customer(models.Model):
    """Egg buyers — shops, hotels, individuals, wholesalers."""

    CUSTOMER_TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('retail', 'Retail Shop'),
        ('hotel', 'Hotel / Restaurant'),
        ('wholesale', 'Wholesaler'),
        ('institution', 'Institution (School, Hospital)'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_customers',
    )
    name = models.CharField(max_length=150)
    customer_type = models.CharField(
        max_length=20, choices=CUSTOMER_TYPE_CHOICES, default='individual'
    )
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_customers_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return self.name


# ============================================================
# EGG SALES
# ============================================================

class EggSale(models.Model):
    """A sale of eggs. Can contain multiple items (trays + individual eggs)."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_egg_sales',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_egg_sales',
        help_text="Which branch/depot made this sale",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='egg_sales',
    )
    invoice_number = models.CharField(max_length=50, blank=True)
    sale_date = models.DateField(default=timezone.now)

    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=SALE_STATUS_CHOICES, default='pending'
    )
    payment_method = models.CharField(
        max_length=30, blank=True,
        help_text="cash, mpesa, bank, credit",
    )
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_egg_sales_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-sale_date', '-created_at']
        verbose_name = 'Egg Sale'
        verbose_name_plural = 'Egg Sales'

    def __str__(self):
        cust = self.customer.name if self.customer else 'Walk-in'
        return f"Sale {self.invoice_number or self.pk} — {cust} — KES {self.total_amount}"

    @property
    def balance(self):
        return _to_decimal(self.total_amount) - _to_decimal(self.amount_paid)

    def recalc_total(self):
        """Recompute total from line items."""
        total = sum(
            (_to_decimal(item.subtotal) for item in self.items.all()),
            Decimal('0'),
        )
        self.total_amount = total
        self.save(update_fields=['total_amount'])
        return total

    def recompute_status(self):
        """Auto-set status from amount_paid vs. total_amount."""
        paid = _to_decimal(self.amount_paid)
        total = _to_decimal(self.total_amount)

        if paid <= 0:
            self.status = 'credit'
        elif paid < total:
            self.status = 'partial'
        else:
            self.status = 'paid'
        self.save(update_fields=['status'])
        return self.status


class EggSaleItem(models.Model):
    """
    One line in an EggSale — e.g. '5 trays @ KES 360 each'
    or '30 eggs @ KES 15 each'.
    """

    sale = models.ForeignKey(
        EggSale, on_delete=models.CASCADE,
        related_name='items',
    )
    unit = models.CharField(
        max_length=10, choices=EGG_UNIT_CHOICES, default='tray'
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Egg Sale Item'
        verbose_name_plural = 'Egg Sale Items'

    def __str__(self):
        return f"{self.quantity} {self.unit}(s) @ {self.unit_price}"

    def save(self, *args, **kwargs):
        # Safely compute subtotal — never crash on bad input
        try:
            qty = int(self.quantity or 0)
            price = _to_decimal(self.unit_price)
            self.subtotal = Decimal(qty) * price
        except (InvalidOperation, ValueError, TypeError):
            self.subtotal = Decimal('0')
        super().save(*args, **kwargs)

    @property
    def eggs_count(self):
        """How many eggs this line item represents."""
        if self.unit == 'tray':
            return self.quantity * 30
        if self.unit == 'crate':
            return self.quantity * 360
        return self.quantity  # 'egg'


# ============================================================
# FEED
# ============================================================

class FeedType(models.Model):
    """Different feeds — layers mash, growers mash, broiler starter, etc."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_feed_types',
    )
    name = models.CharField(max_length=100)
    brand = models.CharField(max_length=100, blank=True)
    protein_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="e.g. 18.00 for 18% protein",
    )
    cost_per_kg = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Feed Type'
        verbose_name_plural = 'Feed Types'

    def __str__(self):
        return f"{self.name}" + (f" ({self.brand})" if self.brand else "")


class FeedRecord(models.Model):
    """Feed purchased or consumed by a flock."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_feed_records',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_feed_records',
        help_text="Which branch/depot used this feed",
    )
    flock = models.ForeignKey(
        Flock, on_delete=models.CASCADE,
        related_name='feed_records',
    )
    feed_type = models.ForeignKey(
        FeedType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='records',
    )
    date = models.DateField(default=timezone.now)
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    supplier = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_feed_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Feed Record'
        verbose_name_plural = 'Feed Records'

    def __str__(self):
        return f"{self.flock.name} — {self.quantity_kg}kg on {self.date}"


# ============================================================
# HEALTH
# ============================================================

class HealthRecord(models.Model):
    """Vaccinations, treatments, deworming, vet visits."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_health_records',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_health_records',
        help_text="Which branch/depot recorded this",
    )
    flock = models.ForeignKey(
        Flock, on_delete=models.CASCADE,
        related_name='health_records',
    )
    date = models.DateField(default=timezone.now)
    record_type = models.CharField(
        max_length=20, choices=HEALTH_TYPE_CHOICES, default='vaccination'
    )
    product_used = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    administered_by = models.CharField(max_length=150, blank=True)
    next_due_date = models.DateField(null=True, blank=True)

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_health_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Health Record'
        verbose_name_plural = 'Health Records'

    def __str__(self):
        return f"{self.flock.name} — {self.get_record_type_display()} on {self.date}"


# ============================================================
# MORTALITY
# ============================================================

class Mortality(models.Model):
    """Deaths and culling."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_mortality',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_mortality',
        help_text="Which branch/depot recorded this",
    )
    flock = models.ForeignKey(
        Flock, on_delete=models.CASCADE,
        related_name='mortality_records',
    )
    date = models.DateField(default=timezone.now)
    count = models.PositiveIntegerField(default=0)
    cause = models.CharField(
        max_length=20, choices=MORTALITY_CAUSE_CHOICES, default='unknown'
    )
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_mortality_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Mortality Record'
        verbose_name_plural = 'Mortality Records'

    def __str__(self):
        return f"{self.flock.name} — {self.count} on {self.date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_flock_count()

    def delete(self, *args, **kwargs):
        flock = self.flock
        super().delete(*args, **kwargs)
        if flock:
            self._sync_flock_count(flock)

    def _sync_flock_count(self, flock=None):
        """Recompute the flock's current_count from all mortality records."""
        flock = flock or self.flock
        if not flock:
            return
        total_deaths = (
            flock.mortality_records
            .aggregate(total=models.Sum('count'))['total'] or 0
        )
        flock.current_count = max(flock.initial_count - total_deaths, 0)
        flock.save(update_fields=['current_count'])


# ============================================================
# EXPENSES
# ============================================================

class Expense(models.Model):
    """General farm expenses."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_expenses',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_expenses',
        help_text="Which branch/depot incurred this expense",
    )
    flock = models.ForeignKey(
        Flock, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses',
        help_text="Optional — leave blank for general farm expenses",
    )
    date = models.DateField(default=timezone.now)
    category = models.CharField(
        max_length=20, choices=EXPENSE_CATEGORY_CHOICES, default='other'
    )
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_to = models.CharField(max_length=150, blank=True)
    payment_method = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kuku_expenses_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'

    def __str__(self):
        return f"{self.get_category_display()} — KES {self.amount} on {self.date}"


# ============================================================
# INVENTORY
# ============================================================

class InventoryItem(models.Model):
    """Egg trays, feed bags, crates, equipment — track stock levels per branch."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_inventory',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_inventory',
        help_text="Which branch/depot holds this stock",
    )

    name = models.CharField(max_length=100)
    item_type = models.CharField(
        max_length=20, choices=INVENTORY_ITEM_TYPE_CHOICES, default='other'
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit = models.CharField(
        max_length=20, blank=True,
        help_text="pcs, kg, bags, trays, etc.",
    )
    reorder_level = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Alert when quantity falls below this",
    )
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Inventory Item'
        verbose_name_plural = 'Inventory'
        # Optional: prevent duplicate item names per branch
        # unique_together = [('company', 'branch', 'name', 'item_type')]

    def __str__(self):
        loc = f" @ {self.branch.name}" if self.branch else ""
        return f"{self.name}{loc} — {self.quantity} {self.unit}"

    @property
    def needs_reorder(self):
        return self.quantity <= self.reorder_level


# ============================================================
# PRICE HISTORY
# ============================================================

class PriceHistory(models.Model):
    """
    Egg price tracking over time — useful for seeing how market
    prices move and adjusting your selling strategy.

    Scoped to the company (prices are typically company-wide,
    not per branch). Add a `branch` FK here if you want per-branch
    pricing.
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_price_history',
    )
    unit = models.CharField(
        max_length=10, choices=EGG_UNIT_CHOICES, default='tray'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField(default=timezone.now)
    notes = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date']
        verbose_name = 'Price History'
        verbose_name_plural = 'Price History'

    def __str__(self):
        return f"{self.get_unit_display()} — KES {self.price} from {self.effective_date}"