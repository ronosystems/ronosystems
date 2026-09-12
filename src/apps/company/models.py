from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.companies.models import Company
from apps.epa_shop.models import Branch

User = get_user_model()


class Expense(models.Model):
    """Unified expense model supporting Salaries, Rents, Bills, and General expenses"""

    # ============================================
    # EXPENSE TYPE (determines which page/form)
    # ============================================
    TYPE_SALARY = 'salary'
    TYPE_RENT = 'rent'
    TYPE_BILL = 'bill'
    TYPE_GENERAL = 'general'

    EXPENSE_TYPES = (
        (TYPE_SALARY, 'Salary'),
        (TYPE_RENT, 'Rent'),
        (TYPE_BILL, 'Bill'),
        (TYPE_GENERAL, 'General Expense'),
    )

    # ============================================
    # GENERAL EXPENSE CATEGORIES (only for TYPE_GENERAL)
    # ============================================
    CATEGORY_TRANSPORT = 'transport'
    CATEGORY_UTILITIES = 'utilities'
    CATEGORY_SUPPLIES = 'supplies'
    CATEGORY_MAINTENANCE = 'maintenance'
    CATEGORY_MARKETING = 'marketing'
    CATEGORY_TAX = 'tax'
    CATEGORY_INSURANCE = 'insurance'
    CATEGORY_OTHER = 'other'

    GENERAL_CATEGORIES = (
        (CATEGORY_TRANSPORT, 'Transport'),
        (CATEGORY_UTILITIES, 'Utilities'),
        (CATEGORY_SUPPLIES, 'Office Supplies'),
        (CATEGORY_MAINTENANCE, 'Maintenance'),
        (CATEGORY_MARKETING, 'Marketing'),
        (CATEGORY_TAX, 'Tax'),
        (CATEGORY_INSURANCE, 'Insurance'),
        (CATEGORY_OTHER, 'Other'),
    )

    # ============================================
    # BILL TYPES (only for TYPE_BILL)
    # ============================================
    BILL_ELECTRICITY = 'electricity'
    BILL_WATER = 'water'
    BILL_INTERNET = 'internet'
    BILL_PHONE = 'phone'
    BILL_SECURITY = 'security'
    BILL_WASTE = 'waste'
    BILL_OTHER = 'other'

    BILL_TYPES = (
        (BILL_ELECTRICITY, 'Electricity'),
        (BILL_WATER, 'Water'),
        (BILL_INTERNET, 'Internet'),
        (BILL_PHONE, 'Phone'),
        (BILL_SECURITY, 'Security'),
        (BILL_WASTE, 'Waste Collection'),
        (BILL_OTHER, 'Other Bill'),
    )

    # ============================================
    # PAYMENT METHODS
    # ============================================
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('m-pesa', 'M-Pesa'),
        ('card', 'Card'),
        ('other', 'Other'),
    )

    # ============================================
    # STATUS
    # ============================================
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_PAID = 'paid'  # For salaries/rents/bills

    EXPENSE_STATUS = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PAID, 'Paid'),
    )

    # ============================================
    # BASIC INFORMATION
    # ============================================
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='expenses'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses'
    )

    # Determines which page/form this expense belongs to
    expense_type = models.CharField(
        max_length=20, choices=EXPENSE_TYPES, default=TYPE_GENERAL,
        db_index=True
    )

    # ============================================
    # COMMON FIELDS
    # ============================================
    expense_date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # ============================================
    # SALARY-SPECIFIC FIELDS
    # ============================================
    employee_name = models.CharField(max_length=150, blank=True)
    employee_id = models.CharField(max_length=50, blank=True)
    employee_phone = models.CharField(max_length=20, blank=True)
    salary_month = models.DateField(
        null=True, blank=True,
        help_text="Month the salary is for (use 1st of month)"
    )

    # ============================================
    # RENT-SPECIFIC FIELDS
    # ============================================
    rent_month = models.DateField(
        null=True, blank=True,
        help_text="Month the rent is for (use 1st of month)"
    )
    landlord_name = models.CharField(max_length=150, blank=True)
    landlord_phone = models.CharField(max_length=20, blank=True)

    # ============================================
    # BILL-SPECIFIC FIELDS
    # ============================================
    bill_type = models.CharField(max_length=20, choices=BILL_TYPES, blank=True)
    bill_name = models.CharField(max_length=150, blank=True)
    bill_period = models.DateField(
        null=True, blank=True,
        help_text="Billing period (use 1st of month)"
    )

    # ============================================
    # GENERAL EXPENSE CATEGORY
    # ============================================
    category = models.CharField(
        max_length=20, choices=GENERAL_CATEGORIES, blank=True
    )

    # ============================================
    # PAYMENT DETAILS
    # ============================================
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHODS, default='cash'
    )
    reference = models.CharField(
        max_length=100, blank=True, help_text="Invoice or receipt number"
    )
    receipt_number = models.CharField(
        max_length=100, blank=True, help_text="Receipt number for rent/bills"
    )

    # ============================================
    # ATTACHMENT (receipt / invoice)
    # ============================================
    attachment = models.FileField(
        upload_to='expense_attachments/%Y/%m/',
        blank=True, null=True,
        help_text="Upload receipt or invoice (JPG, PNG, GIF, or PDF)"
    )

    # ============================================
    # ADDITIONAL INFO
    # ============================================
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=EXPENSE_STATUS, default=STATUS_PENDING
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    # ============================================
    # AUDIT TRAIL
    # ============================================
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='expenses_created'
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # ============================================
    # TIMESTAMPS
    # ============================================
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_expenses'
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'expense_type', 'expense_date']),
            models.Index(fields=['company', 'expense_type', 'status']),
            models.Index(fields=['company', 'salary_month']),
            models.Index(fields=['company', 'rent_month']),
            models.Index(fields=['company', 'bill_period']),
        ]

    def __str__(self):
        return f"[{self.get_expense_type_display()}] {self.description} (KSh {self.amount})"

    # ============================================
    # DISPLAY HELPERS
    # ============================================
    @property
    def category_display(self):
        for key, value in self.GENERAL_CATEGORIES:
            if key == self.category:
                return value
        return self.category or '—'

    @property
    def bill_type_display(self):
        for key, value in self.BILL_TYPES:
            if key == self.bill_type:
                return value
        return self.bill_type or '—'

    @property
    def status_display(self):
        for key, value in self.EXPENSE_STATUS:
            if key == self.status:
                return value
        return self.status

    @property
    def payment_method_display(self):
        for key, value in self.PAYMENT_METHODS:
            if key == self.payment_method:
                return value
        return self.payment_method

    @property
    def has_attachment(self):
        return bool(self.attachment)

    @property
    def is_pdf(self):
        if not self.attachment:
            return False
        return self.attachment.name.lower().endswith('.pdf')

    @property
    def salary_month_display(self):
        if self.salary_month:
            return self.salary_month.strftime('%B %Y')
        return '—'

    @property
    def rent_month_display(self):
        if self.rent_month:
            return self.rent_month.strftime('%B %Y')
        return '—'

    @property
    def bill_period_display(self):
        if self.bill_period:
            return self.bill_period.strftime('%B %Y')
        return '—'

    # ============================================
    # SAVE OVERRIDE (delete old attachment on replace)
    # ============================================
    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = Expense.objects.get(pk=self.pk)
                if old.attachment and old.attachment != self.attachment:
                    old.attachment.delete(save=False)
            except Expense.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    # ============================================
    # STATUS ACTIONS
    # ============================================
    def approve(self, user):
        self.status = self.STATUS_APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def reject(self):
        self.status = self.STATUS_REJECTED
        self.save()

    def mark_paid(self, user=None):
        self.status = self.STATUS_PAID
        self.paid_at = timezone.now()
        if user and not self.approved_by:
            self.approved_by = user
            self.approved_at = timezone.now()
        self.save()