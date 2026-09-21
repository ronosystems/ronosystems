"""
Kuku Biz — Poultry Farming Models

Supports:
- Layer hens (egg production)
- Broilers (meat production)
- Multiple concurrent flocks
- Per-flock egg tracking
- Egg sales in trays (6/12/30/45), crates, or individual eggs
- Feed, health, mortality, expenses
- Branch-scoped inventory and price tracking
- Automatic stock deduction on sale
- Multi-tenant (each record belongs to a Company, optionally a Branch)
"""

from decimal import Decimal, InvalidOperation

from django.db import models
from django.conf import settings as django_settings
from django.utils import timezone


User = django_settings.AUTH_USER_MODEL


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

# What the customer is buying — one unit at a time
EGG_UNIT_CHOICES = [
    ('egg', 'Individual Egg'),
    ('tray', 'Tray'),
    ('crate', 'Crate (360 eggs)'),
]

# Physical tray size (how many eggs the tray holds)
TRAY_SIZE_CHOICES = [
    (0,   '— Not an egg container —'),
    (1,   '1-Egg (Individual)'),
    (6,   '6-Egg Tray'),
    (12,  '12-Egg Tray'),
    (30,  '30-Egg Tray'),
    (45,  '45-Egg Tray'),
    (360, '360-Egg Crate'),
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


def _eggs_for_unit(unit, quantity, tray_size=None):
    """
    Convert (unit, quantity) into a number of eggs.

    If tray_size is provided and unit='tray', use that tray size.
    Otherwise fall back to the standard 30.
    """
    try:
        qty = int(quantity or 0)
    except (TypeError, ValueError):
        qty = 0

    if unit == 'crate':
        return qty * 360
    if unit == 'tray':
        return qty * (tray_size or 30)
    return qty  # 'egg'


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

    # ── NEW: Purchase details ──
    supplier = models.CharField(
        max_length=150, blank=True,
        help_text="Who sold the birds (hatchery, farm, supplier name)",
    )
    purchase_price_per_bird = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Cost per bird at acquisition",
    )
    total_purchase_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Total cost of acquiring this flock",
    )
    age_at_acquisition_days = models.PositiveIntegerField(
        default=0,
        help_text="How old the birds were when acquired (in days)",
    )

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

    # ------------------------------------------------------------
    # Age helpers
    # ------------------------------------------------------------
    @property
    def age_in_days(self):
        """
        Total age in days: time since acquisition PLUS the age at which
        the birds were acquired.

        Example: bought at 7 days old, 30 days ago = 37 days old today.
        """
        return (timezone.now().date() - self.date_acquired).days + self.age_at_acquisition_days

    @property
    def age_in_weeks(self):
        return self.age_in_days // 7

    # ------------------------------------------------------------
    # Mortality helpers
    # ------------------------------------------------------------
    @property
    def mortality_count(self):
        return max(self.initial_count - self.current_count, 0)

    @property
    def mortality_rate(self):
        if not self.initial_count:
            return 0
        return round((self.mortality_count / self.initial_count) * 100, 2)

    # ------------------------------------------------------------
    # Cost helpers
    # ------------------------------------------------------------
    @property
    def cost_per_bird_at_acquisition(self):
        """
        If purchase_price_per_bird is not set but total_purchase_cost is,
        derive it. Otherwise return the stored value.
        """
        if self.purchase_price_per_bird and self.purchase_price_per_bird > 0:
            return self.purchase_price_per_bird
        if self.total_purchase_cost and self.initial_count:
            return round(self.total_purchase_cost / self.initial_count, 2)
        return 0

    @property
    def total_rearing_cost(self):
        """
        Total cost to date: purchase + all linked expenses + feed + health.

        Note: this queries related models — use sparingly in lists.
        Use `.annotate()` in views for bulk calculations.
        """
        from django.db.models import Sum

        purchase = self.total_purchase_cost or 0
        expenses = (
            self.expenses.aggregate(total=Sum('amount'))['total'] or 0
        )
        feed = (
            self.feed_records.aggregate(total=Sum('cost'))['total'] or 0
        )
        health = (
            self.health_records.aggregate(total=Sum('cost'))['total'] or 0
        )
        return purchase + expenses + feed + health

    # ------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------
    @property
    def age_display(self):
        """Human-readable age, e.g. '35 weeks' or '5 days'."""
        days = self.age_in_days
        if days < 14:
            return f"{days} day{'s' if days != 1 else ''}"
        if days < 70:
            return f"{self.age_in_weeks} week{'s' if self.age_in_weeks != 1 else ''}"
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''}"


# ============================================================
# BIRD SALES (live birds — broilers, spent hens, surplus males)
# ============================================================

class BirdSale(models.Model):
    """
    Sale of live birds (broilers, spent hens, surplus males).

    On save, automatically:
      - computes total_amount = birds_sold × unit_price
      - deducts birds_sold from the flock's current_count
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='kuku_bird_sales',
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_bird_sales',
        help_text="Which branch/depot made this sale",
    )
    flock = models.ForeignKey(
        'Flock',
        on_delete=models.CASCADE,
        related_name='bird_sales',
        help_text="Which flock the birds came from",
    )
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bird_sales',
        help_text="Optional — leave blank for walk-in buyers",
    )
    buyer_name = models.CharField(
        max_length=150, blank=True,
        help_text="Walk-in buyer name if no customer record",
    )

    date = models.DateField(default=timezone.now)

    birds_sold = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Price per bird",
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )

    payment_method = models.CharField(
        max_length=30, blank=True,
        help_text="cash, mpesa, bank, credit",
    )
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='kuku_bird_sales_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Bird Sale'
        verbose_name_plural = 'Bird Sales'

    def __str__(self):
        buyer = (
            self.customer.name
            if self.customer
            else (self.buyer_name or 'Walk-in')
        )
        return f"{self.birds_sold} birds — {buyer} — KES {self.total_amount}"

    # ------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------
    @property
    def balance(self):
        return _to_decimal(self.total_amount) - _to_decimal(self.amount_paid)

    @property
    def buyer_display(self):
        if self.customer:
            return self.customer.name
        return self.buyer_name or 'Walk-in'

    # ------------------------------------------------------------
    # Save — compute total + deduct from flock
    # ------------------------------------------------------------
    def save(self, *args, **kwargs):
        # 1) Auto-compute total from birds × unit_price
        try:
            qty = int(self.birds_sold or 0)
            price = _to_decimal(self.unit_price)
            self.total_amount = Decimal(qty) * price
        except (InvalidOperation, ValueError, TypeError):
            self.total_amount = Decimal('0')

        # 2) Auto-fill branch from the flock if not explicitly set
        if not self.branch_id and self.flock_id:
            self.branch = getattr(self.flock, 'branch', None)

        # 3) Save the row
        super().save(*args, **kwargs)

        # 4) Deduct birds from the flock's current count
        #    (only if this instance has been saved and has a flock)
        if self.flock_id and self.birds_sold:
            flock = self.flock
            new_count = max(flock.current_count - self.birds_sold, 0)
            if new_count != flock.current_count:
                flock.current_count = new_count
                flock.save(update_fields=['current_count'])
                

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
    """
    A sale of eggs. Can contain multiple items (trays of different
    sizes + individual eggs + crates).

    Invoice numbers are auto-generated per company and unique within
    the company.
    """

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

    # Human-readable invoice / receipt reference. Auto-generated per company
    # if left blank. Unique within a company.
    invoice_number = models.CharField(
        max_length=50, blank=True,
        help_text="Leave blank to auto-generate",
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'invoice_number'],
                condition=~models.Q(invoice_number=''),
                name='unique_invoice_per_company',
            ),
        ]

    def __str__(self):
        cust = self.customer.name if self.customer else 'Walk-in'
        return f"Sale {self.invoice_number or self.pk} — {cust} — KES {self.total_amount}"

    # ------------------------------------------------------------
    # Receipt number
    # ------------------------------------------------------------
    @property
    def receipt_number(self):
        """
        Receipt number shown on printouts. Falls back to KB-<company>-<pk>
        if the invoice_number is empty (shouldn't normally happen since
        save() auto-generates it, but defensive).
        """
        if self.invoice_number:
            return self.invoice_number
        if self.pk:
            return f"KB-{self.company_id}-{self.pk:05d}"
        return 'KB-PENDING'

    # ------------------------------------------------------------
    # Auto-generate invoice_number per company
    # ------------------------------------------------------------
    def save(self, *args, **kwargs):
        """
        On first save, generate an invoice_number if the caller didn't
        provide one. Format: KB-<company_id>-<sequence>.

        Also: if `branch` is empty and the recorder has a branch, use it.
        This keeps every sale branch-scoped automatically.
        """
        if not self.branch_id and self.recorded_by_id:
            self.branch = getattr(self.recorded_by, 'branch', None)

        if not self.invoice_number and self.company_id:
            self.invoice_number = self._generate_invoice_number()

        super().save(*args, **kwargs)

    def _generate_invoice_number(self):
        """Produce a unique, per-company invoice number."""
        base = EggSale.objects.filter(company_id=self.company_id).count() + 1
        candidate = f"KB-{self.company_id}-{base:05d}"

        suffix = base
        while EggSale.objects.filter(
            company_id=self.company_id,
            invoice_number=candidate,
        ).exists():
            suffix += 1
            candidate = f"KB-{self.company_id}-{suffix:05d}"

        return candidate

    # ------------------------------------------------------------
    # Money / status helpers
    # ------------------------------------------------------------
    @property
    def balance(self):
        return _to_decimal(self.total_amount) - _to_decimal(self.amount_paid)

    @property
    def total_eggs(self):
        """Total eggs across all line items."""
        return sum(item.eggs_count for item in self.items.all())

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

    @property
    def total_eggs(self):
        """Sum of eggs across all line items."""
        return sum(item.eggs_count for item in self.items.all())

    @property
    def eggs_breakdown(self):
        """
        Compact string like '5×30 + 2×12 + 10' for the sub-line.
        Shows tray size breakdown so managers see the mix.
        """
        parts = []
        for item in self.items.all():
            if item.unit == 'tray' and item.tray_size:
                parts.append(f"{item.quantity}×{item.tray_size}")
            elif item.unit == 'crate':
                parts.append(f"{item.quantity}×360")
            else:
                parts.append(str(item.quantity))
        return ' + '.join(parts) if parts else '—'


class EggSaleItem(models.Model):
    """
    One line in an EggSale — e.g. '5 trays @ KES 360 each'
    or '30 eggs @ KES 15 each'.

    We store `tray_size` so the same sale can mix 6/12/30/45-egg trays.
    `eggs_count` reflects the actual number of eggs.
    """

    sale = models.ForeignKey(
        EggSale, on_delete=models.CASCADE,
        related_name='items',
    )
    unit = models.CharField(
        max_length=10, choices=EGG_UNIT_CHOICES, default='tray'
    )
    # For 'tray' sales, which tray size did we sell? (0 for non-tray units)
    tray_size = models.PositiveIntegerField(
        default=30,
        help_text="For tray sales: 6, 12, 30, or 45. Ignored for 'egg'/'crate'.",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Egg Sale Item'
        verbose_name_plural = 'Egg Sale Items'

    def __str__(self):
        if self.unit == 'tray':
            return f"{self.quantity}×{self.tray_size}-egg tray @ {self.unit_price}"
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
        if self.unit == 'crate':
            return self.quantity * 360
        if self.unit == 'tray':
            return self.quantity * (self.tray_size or 30)
        return self.quantity  # 'egg'

    @property
    def unit_label(self):
        """Friendly label for the receipt / list."""
        if self.unit == 'tray':
            return f"{self.tray_size}-Egg Tray"
        if self.unit == 'crate':
            return "Crate (360 eggs)"
        return "Egg"


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
    """
    Egg trays, feed bags, crates, equipment — track stock levels per branch.

    `tray_size` marks egg containers (6/12/30/45/360) so we know how many
    eggs each unit holds. Non-egg items leave it at 0.
    """

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
    # How many eggs does one unit hold? (0 = non-egg item)
    tray_size = models.PositiveIntegerField(
        default=0,
        choices=TRAY_SIZE_CHOICES,
        help_text="Eggs per unit for egg containers. 0 for non-egg items.",
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

    image = models.ImageField(
        upload_to='kuku/inventory/',
        null=True, blank=True,
        max_length=500,
        help_text="Cloudinary public_id (URL built via image_url property)",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Inventory Item'
        verbose_name_plural = 'Inventory'

    def __str__(self):
        loc = f" @ {self.branch.name}" if self.branch else ""
        return f"{self.name}{loc} — {self.quantity} {self.unit}"

    # ---------- Computed ----------

    @property
    def eggs_per_unit(self):
        """Eggs per unit for egg containers. 0 for non-egg items."""
        if self.tray_size:
            return self.tray_size
        if self.item_type == 'egg_crate':
            return 360
        return 0

    @property
    def total_eggs(self):
        """Total eggs this line represents."""
        return float(self.quantity) * self.eggs_per_unit

    @property
    def is_egg_container(self):
        return self.eggs_per_unit > 0

    @property
    def needs_reorder(self):
        return self.quantity <= self.reorder_level

    @property
    def image_url(self):
        """
        Fully-formed Cloudinary URL for the item image, or None.

        The view uploads to Cloudinary via cloudinary.uploader.upload()
        and stores the returned public_id in `self.image`. This property
        builds the delivery URL manually:

            https://res.cloudinary.com/<cloud_name>/image/upload/<public_id>

        Falls back to MEDIA_URL when Cloudinary is not configured (dev).
        """
        if not self.image:
            return None

        key = getattr(self.image, 'name', None) or str(self.image)
        key = key.strip().lstrip('/')

        if not key:
            return None

        if key.startswith('media/'):
            key = key[len('media/'):]

        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')

        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{key}"

        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"


# ============================================================
# PRICE HISTORY
# ============================================================

class PriceHistory(models.Model):
    """
    Egg price tracking over time — one row per change.

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
    # Optional: which tray size this price applies to (0 = any / N/A)
    tray_size = models.PositiveIntegerField(
        default=0, choices=TRAY_SIZE_CHOICES,
        help_text="Which tray size this price applies to (0 for non-tray units)",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField(default=timezone.now)
    notes = models.CharField(max_length=200, blank=True)

    image = models.ImageField(
        upload_to='kuku/prices/',
        null=True, blank=True,
        max_length=500,
        help_text="Cloudinary public_id (URL built via image_url property)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date']
        verbose_name = 'Price History'
        verbose_name_plural = 'Price History'

    def __str__(self):
        if self.unit == 'tray' and self.tray_size:
            return f"{self.tray_size}-Egg Tray — KES {self.price} from {self.effective_date}"
        return f"{self.get_unit_display()} — KES {self.price} from {self.effective_date}"

    @property
    def display_label(self):
        """Friendly label used in templates."""
        if self.unit == 'tray' and self.tray_size:
            return f"{self.tray_size}-Egg Tray"
        return self.get_unit_display()

    @property
    def image_url(self):
        """
        Fully-formed Cloudinary URL for the price image, or None.
        """
        if not self.image:
            return None

        key = getattr(self.image, 'name', None) or str(self.image)
        key = key.strip().lstrip('/')

        if not key:
            return None

        if key.startswith('media/'):
            key = key[len('media/'):]

        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')

        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{key}"

        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"