# apps/workshop/models.py

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.companies.models import Company
from apps.company.models import Branch


# ================================================================
# REPAIR CATEGORY
# ================================================================

class RepairCategory(models.Model):
    """
    Category of repair work — phone, electronic, accessory, screen, product.
    Scoped per-company. Global defaults (company=NULL) are intentionally
    not supported to avoid NULL-uniqueness pitfalls on (company, slug).
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='workshop_categories',
        help_text='Categories belong to a specific company.',
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workshop_repair_categories'
        ordering = ['order', 'name']
        unique_together = [('company', 'slug')]

    def __str__(self):
        return self.name


# ================================================================
# WORKSHOP CUSTOMER
# ================================================================

class WorkshopCustomer(models.Model):
    """Customer who brought in a device."""

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='workshop_customers',
    )
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workshop_customers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'phone']),
        ]

    def __str__(self):
        return f"{self.name or 'Customer'} ({self.phone or 'no phone'})"


# ================================================================
# WORKSHOP JOB
# ================================================================

class WorkshopJob(models.Model):
    """Core repair job. One device, one repair workflow."""

    REPAIR_CATEGORIES = (
        ('phone', 'Phone Repair'),
        ('electronic', 'Electronic Repair'),
        ('accessory', 'Accessory Repair'),
        ('screen', 'Screen Repair'),
        ('product', 'Product Repair'),
        ('other', 'Other'),
    )

    WORK_SOURCE = (
        ('customer', 'Customer Walk-in'),
        ('store_stock', 'Store Stock (Company Device)'),
    )

    STATUS_CHOICES = (
        ('received', 'Received'),
        ('diagnosed', 'Diagnosed / Quoted'),
        ('awaiting_approval', 'Awaiting Customer Approval'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('unrepairable', 'Unrepairable'),
    )

    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )

    # -------------------- Identifiers --------------------
    job_number = models.CharField(
        max_length=30, unique=True, blank=True,
        help_text='Auto-generated on save if blank.',
    )

    # -------------------- Company scoping --------------------
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='workshop_jobs',
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='workshop_jobs',
    )

    # -------------------- Classification --------------------
    repair_category = models.CharField(
        max_length=20,
        choices=REPAIR_CATEGORIES,
        default='phone',
    )
    work_source = models.CharField(
        max_length=20,
        choices=WORK_SOURCE,
        default='customer',
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='received',
        db_index=True,
    )

    # -------------------- Customer / device --------------------
    customer = models.ForeignKey(
        WorkshopCustomer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='jobs',
        help_text='Null for store-stock repairs.',
    )

    device_name = models.CharField(
        max_length=200,
        help_text='e.g. "Samsung Galaxy A14", "HP Laptop", "Sony TV"',
    )
    device_brand = models.CharField(max_length=100, blank=True)
    device_model = models.CharField(max_length=100, blank=True)
    device_serial = models.CharField(
        max_length=100, blank=True,
        help_text='IMEI, serial number, or other identifier.',
    )
    device_password = models.CharField(
        max_length=100, blank=True,
        help_text='Lock code / PIN if customer provided one.',
    )
    device_accessories = models.TextField(
        blank=True,
        help_text='e.g. "charger, case, SIM tray" — items received with the device.',
    )

    # -------------------- Problem & diagnosis --------------------
    reported_problem = models.TextField(
        help_text='What the customer said is wrong.',
    )
    diagnosis = models.TextField(
        blank=True,
        help_text='Technician findings after inspection.',
    )
    work_summary = models.TextField(
        blank=True,
        help_text='Final summary of what was done.',
    )

    # -------------------- Money --------------------
    estimated_material_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Estimated cost of repair materials.',
    )
    actual_material_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Actual amount spent on materials (auto-calculated from JobMaterial).',
    )
    quoted_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Amount quoted to the customer.',
    )
    final_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Final amount the customer pays.',
    )
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Total received from customer so far.',
    )

    # -------------------- People --------------------
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='jobs_received',
    )
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='jobs_assigned',
        limit_choices_to={'role__in': ['company_technician', 'company_manager', 'company_admin']},
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='jobs_completed',
    )

    transport_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Amount spent on transport for this repair (fuel, boda, courier).',
    )

    # -------------------- Dates --------------------
    received_at = models.DateTimeField(default=timezone.now)
    diagnosed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)

    # -------------------- Warranty --------------------
    warranty_days = models.IntegerField(
        default=0,
        help_text='Number of days warranty on this repair. 0 = no warranty.',
    )
    warranty_expires_at = models.DateField(null=True, blank=True)

    # -------------------- Notes --------------------
    internal_notes = models.TextField(
        blank=True,
        help_text='Notes visible only to staff.',
    )

    # -------------------- Audit --------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workshop_jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['assigned_technician', 'status']),
            models.Index(fields=['job_number']),
        ]

    def __str__(self):
        return f"{self.job_number} — {self.device_name}"

    # ----------------------------------------------------------------
    # SAVE / AUTO NUMBER
    # ----------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.job_number:
            self.job_number = self._generate_job_number()

        # Recompute material cost from child rows when the job already exists.
        if self.pk:
            total = self.materials.aggregate(
                total=models.Sum('total_cost')
            )['total'] or Decimal('0.00')
            self.actual_material_cost = total

        super().save(*args, **kwargs)

    def _generate_job_number(self):
        """
        Generates a unique job number scoped to the company:
        WS-<company_id>-<YYYYMMDD>-<seq>
        """
        today = timezone.now().strftime('%Y%m%d')
        prefix = f"WS-{self.company_id or 0}-{today}-"
        last = (
            WorkshopJob.objects
            .filter(job_number__startswith=prefix)
            .order_by('-id')
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.job_number.rsplit('-', 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f"{prefix}{seq:04d}"

    # ----------------------------------------------------------------
    # MONEY HELPERS
    # ----------------------------------------------------------------
    @property
    def balance_due(self):
        return (self.final_amount or Decimal('0.00')) - (self.amount_paid or Decimal('0.00'))

    @property
    def is_fully_paid(self):
        return self.balance_due <= Decimal('0.00')

    @property
    def profit(self):
        """Revenue minus cost of materials. Never negative."""
        raw = (self.final_amount or Decimal('0.00')) - (self.actual_material_cost or Decimal('0.00'))
        return max(raw, Decimal('0.00'))

    # ----------------------------------------------------------------
    # STATUS HELPERS
    # ----------------------------------------------------------------
    @property
    def is_open(self):
        return self.status not in ('delivered', 'cancelled', 'unrepairable')

    @property
    def is_closed(self):
        return not self.is_open

    @property
    def days_open(self):
        end = self.delivered_at or timezone.now()
        return (end - self.received_at).days

    # ----------------------------------------------------------------
    # TECHNICIAN PAYOUT
    # ----------------------------------------------------------------
    def compute_technician_payout(self, save=True):
        """
        Compute (or recompute) the TechnicianPayout row for this job.

        Resolution order for the rate:
          1. Specific (technician, repair_category) match.
          2. Technician's default (blank repair_category).
          3. No rate → create a zero-amount manual row.

        Payouts that are already 'paid' are never overwritten.
        Payouts that are 'pending' get their basis/pct/basis_amount refreshed
        so the audit trail stays accurate — but the `amount` field is left
        untouched (admin edits are preserved).
        """
        tech = self.assigned_technician
        if not tech:
            return None

        # --- Rate lookup ---
        rate = (
            TechnicianRate.objects
            .filter(
                company=self.company,
                technician=tech,
                repair_category=self.repair_category,
                is_active=True,
            )
            .first()
            or TechnicianRate.objects
            .filter(
                company=self.company,
                technician=tech,
                repair_category='',
                is_active=True,
            )
            .first()
        )

        # --- Basis amount ---
        if rate and rate.basis == 'revenue':
            basis_amount = self.final_amount or Decimal('0.00')
            basis = 'revenue'
            pct = rate.percentage
            amount = (basis_amount * pct / 100).quantize(Decimal('0.01'))
        elif rate and rate.basis == 'profit':
            basis_amount = self.profit
            basis = 'profit'
            pct = rate.percentage
            amount = (basis_amount * pct / 100).quantize(Decimal('0.01'))
        else:
            basis = 'manual'
            basis_amount = Decimal('0.00')
            pct = Decimal('0.00')
            amount = Decimal('0.00')

        payout, created = TechnicianPayout.objects.get_or_create(
            job=self,
            defaults={
                'technician': tech,
                'basis': basis,
                'percentage': pct,
                'basis_amount': basis_amount,
                'amount': amount,
                'status': 'pending',
            },
        )

        if not created and payout.status == 'pending':
            payout.basis = basis
            payout.percentage = pct
            payout.basis_amount = basis_amount
            if save:
                payout.save(update_fields=[
                    'basis', 'percentage', 'basis_amount', 'updated_at',
                ])

        return payout


# ================================================================
# JOB MATERIAL
# ================================================================

class JobMaterial(models.Model):
    """
    A material/part used on a repair.
    Can be sourced from stock OR purchased externally.
    """

    SOURCE_CHOICES = (
        ('stock', 'From Store Stock'),
        ('external', 'Purchased Externally'),
    )

    FUND_SOURCE_CHOICES = (
        ('', 'N/A (from stock)'),
        ('company_cash', 'Company Cash'),
        ('technician_cash', 'Technician Personal Cash'),
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('other', 'Other'),
    )

    job = models.ForeignKey(
        WorkshopJob,
        on_delete=models.CASCADE,
        related_name='materials',
    )

    name = models.CharField(
        max_length=200,
        help_text='e.g. "LCD Screen", "Charging Port", "Battery"',
    )
    description = models.TextField(blank=True)

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='stock')
    fund_source = models.CharField(
        max_length=20,
        choices=FUND_SOURCE_CHOICES,
        blank=True,
        default='',
        help_text='Who paid for this material. Only relevant for external purchases.',
    )

    stock_item_id = models.IntegerField(
        null=True, blank=True,
        help_text='Optional link to an inventory item.',
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='materials_added',
    )

    purchase_receipt = models.CharField(
        max_length=500, blank=True,
        help_text='Cloudinary public_id for the purchase receipt (external buys only).',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workshop_job_materials'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.name} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.total_cost = (self.quantity or 0) * (self.unit_cost or 0)
        super().save(*args, **kwargs)

    def get_receipt_url(self):
        """Fully-formed URL for the purchase receipt (Cloudinary or local)."""
        if not self.purchase_receipt:
            return None
        key = self.purchase_receipt.strip().lstrip('/')
        cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')
        if cloud_name:
            resource = 'raw' if key.lower().endswith('.pdf') else 'image'
            return f"https://res.cloudinary.com/{cloud_name}/{resource}/upload/{key}"
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"


# ================================================================
# JOB NOTE
# ================================================================

class JobNote(models.Model):
    """Progress notes on a job."""

    job = models.ForeignKey(
        WorkshopJob,
        on_delete=models.CASCADE,
        related_name='notes',
    )
    note = models.TextField()
    is_customer_visible = models.BooleanField(
        default=False,
        help_text='If True, this note can appear on the customer receipt.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='job_notes_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workshop_job_notes'
        ordering = ['created_at']

    def __str__(self):
        return f"Note on {self.job.job_number}"


# ================================================================
# JOB PAYMENT
# ================================================================

class JobPayment(models.Model):
    """A payment received from a customer for a job."""

    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('mpesa_till', 'M-Pesa Till'),
        ('mpesa_withdrawal', 'M-Pesa Withdrawal'),
        ('bank_transfer', 'Bank Transfer'),
        ('card', 'Card'),
        ('other', 'Other'),
    )

    job = models.ForeignKey(
        WorkshopJob,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference = models.CharField(
        max_length=200, blank=True,
        help_text='M-Pesa code, bank ref, or other transaction identifier.',
    )
    notes = models.TextField(blank=True)

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='job_payments_received',
    )
    received_at = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workshop_job_payments'
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.amount} via {self.get_method_display()} on {self.job.job_number}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update parent job's amount_paid from all payments.
        # Explicit updated_at keeps the audit trail honest.
        total = (
            self.job.payments
            .aggregate(total=models.Sum('amount'))['total']
            or Decimal('0.00')
        )
        WorkshopJob.objects.filter(pk=self.job_id).update(
            amount_paid=total,
            updated_at=timezone.now(),
        )


# ================================================================
# TECHNICIAN RATE
# ================================================================

class TechnicianRate(models.Model):
    """
    Default payout percentage for a technician.
    Per technician, optionally per repair category.
    """

    BASIS_CHOICES = (
        ('profit', 'Profit (final amount − material cost)'),
        ('revenue', 'Revenue (final amount)'),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='technician_rates',
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workshop_rates',
        limit_choices_to={'role': 'company_technician'},
    )
    repair_category = models.CharField(
        max_length=20,
        blank=True,
        default='',
        choices=WorkshopJob.REPAIR_CATEGORIES,
        help_text="Leave blank for the technician's default rate across all categories.",
    )
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='e.g. 30.00 = 30% of profit',
    )
    basis = models.CharField(
        max_length=10,
        choices=BASIS_CHOICES,
        default='profit',
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workshop_technician_rates'
        ordering = ['technician__first_name', 'repair_category']
        unique_together = [('company', 'technician', 'repair_category')]

    def __str__(self):
        cat = self.repair_category or 'all'
        tech_name = self.technician.full_name if self.technician else 'Unknown'
        return f"{tech_name} — {cat} — {self.percentage}% of {self.basis}"


# ================================================================
# TECHNICIAN PAYOUT
# ================================================================

class TechnicianPayout(models.Model):
    """
    Amount owed to a technician for a specific job.
    Auto-created when a job is completed; admin can adjust and pay.
    """

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    )

    BASIS_CHOICES = (
        ('profit', 'Profit'),
        ('revenue', 'Revenue'),
        ('manual', 'Manual Override'),
    )

    job = models.OneToOneField(
        WorkshopJob,
        on_delete=models.CASCADE,
        related_name='technician_payout',
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='workshop_payouts',
    )

    basis = models.CharField(max_length=10, choices=BASIS_CHOICES, default='profit')
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Percentage used at time of computation.',
    )
    basis_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='The amount the percentage was applied to (profit or revenue).',
    )

    amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Final amount owed to the technician. Editable by admins.',
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )

    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='workshop_payouts_paid',
    )
    payment_method = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('cash', 'Cash'),
            ('mpesa', 'M-Pesa'),
            ('bank_transfer', 'Bank Transfer'),
            ('other', 'Other'),
        ],
    )
    payment_reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='workshop_payouts_computed',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workshop_technician_payouts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['technician', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        tech_name = self.technician.full_name if self.technician else 'Unassigned'
        return f"{self.job.job_number} — {tech_name} — {self.amount} ({self.status})"

    @property
    def is_paid(self):
        return self.status == 'paid'

    @property
    def is_pending(self):
        return self.status == 'pending'

    def clean(self):
        """Enforce that a paid payout has payment metadata."""
        if self.status == 'paid' and not self.paid_at:
            raise ValidationError({'paid_at': 'A paid payout must have a paid_at timestamp.'})