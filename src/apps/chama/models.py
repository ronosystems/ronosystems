from django.conf import settings
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone
from django.urls import reverse


# ============================================================
# CLOUDINARY URL HELPER
# ============================================================
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
        # Add fl_attachment for raw files (PDFs) to bypass 401 errors
        if resource_type == 'raw':
            return f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/fl_attachment/{key}"
        
        return f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/{key}"

    media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
    if not media_url.endswith('/'):
        media_url += '/'
    return f"{media_url}{key}"


# ============================================================
# BASE MODEL
# ============================================================
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ============================================================
# MEMBERS
# ============================================================
class MembershipType(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_membership_types',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    monthly_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    registration_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return self.name


class Member(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('exited', 'Exited'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_members',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_memberships',
    )
    membership_type = models.ForeignKey(
        MembershipType, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='members',
    )
    member_number = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    national_id = models.CharField(max_length=50, blank=True)

    # KYC / Documents
    passport_photo = models.ImageField(upload_to='chama/members/passport/', null=True, blank=True)
    id_front = models.ImageField(upload_to='chama/members/id_front/', null=True, blank=True)
    id_back = models.ImageField(upload_to='chama/members/id_back/', null=True, blank=True)
    kra_certificate = models.FileField(upload_to='chama/members/kra/', null=True, blank=True)
    good_conduct = models.FileField(upload_to='chama/members/good_conduct/', null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    joined_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f'{self.member_number} — {self.full_name}'

    # ============================================================
    # BALANCE / ELIGIBILITY PROPERTIES
    # ============================================================
    @property
    def savings_balance(self):
        """Sum of all savings deposits for this member."""
        agg = self.savings.aggregate(total=models.Sum('amount'))
        return agg['total'] or 0

    @property
    def total_contributions_paid(self):
        """Sum of all PAID contributions for this member."""
        agg = self.contributions.filter(paid=True).aggregate(
            total=models.Sum('amount')
        )
        return agg['total'] or 0

    @property
    def max_loan_multiplier(self):
        """The multiplier applied to contributions to determine max loan (3×)."""
        return 3

    @property
    def eligible_loan_limit(self):
        """Maximum borrowing based on 3× paid contributions."""
        return self.total_contributions_paid * self.max_loan_multiplier

    @property
    def active_loans_total(self):
        """Sum of principal for loans still outstanding (approved or disbursed)."""
        agg = self.loans.filter(
            status__in=['approved', 'disbursed']
        ).aggregate(total=models.Sum('principal'))
        return agg['total'] or 0

    @property
    def available_borrowing_power(self):
        """How much the member can still borrow (limit − active loans)."""
        return max(0, self.eligible_loan_limit - self.active_loans_total)

    # ============================================================
    # CLOUDINARY URL GETTERS
    # ============================================================
    @property
    def passport_photo_url(self):
        return _build_cloudinary_url(self.passport_photo)

    @property
    def id_front_url(self):
        return _build_cloudinary_url(self.id_front)

    @property
    def id_back_url(self):
        return _build_cloudinary_url(self.id_back)

    @property
    def kra_certificate_url(self):
        return _build_cloudinary_url(self.kra_certificate, resource_type='raw')

    @property
    def good_conduct_url(self):
        return _build_cloudinary_url(self.good_conduct, resource_type='raw')


class Registration(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_registrations',
    )
    membership_type = models.ForeignKey(
        MembershipType, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    national_id = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.get_status_display()})'


# ============================================================
# SAVINGS / CONTRIBUTIONS / FINES
# ============================================================
class Savings(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_savings',
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='savings',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.member} — {self.amount}'


class Contribution(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_contributions',
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='contributions',
    )
    membership_type = models.ForeignKey(
        MembershipType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    period = models.CharField(max_length=20, blank=True, help_text='e.g. 2026-10')
    date = models.DateField(default=timezone.localdate)
    paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.member} — {self.amount} ({self.period})'


class Fine(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_fines',
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='fines',
    )
    reason = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.member} — {self.reason} ({self.amount})'


# ============================================================
# LOANS
# ============================================================
class LoanType(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_loan_types',
    )
    name = models.CharField(max_length=100)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text='Annual interest rate (%)',
    )
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_term_months = models.PositiveIntegerField(default=12)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return self.name


class Loan(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('disbursed', 'Disbursed'),
        ('closed', 'Closed'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_loans',
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='loans',
    )
    loan_type = models.ForeignKey(
        LoanType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    term_months = models.PositiveIntegerField(default=12)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_on = models.DateField(default=timezone.localdate)
    approved_on = models.DateField(null=True, blank=True)
    disbursed_on = models.DateField(null=True, blank=True)
    purpose = models.TextField(blank=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_loans_approved',
    )
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_loans_rejected',
    )
    disbursed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_loans_disbursed',
    )

    class Meta:
        ordering = ['-requested_on', '-created_at']

    def __str__(self):
        return f'Loan #{self.pk} — {self.member} ({self.get_status_display()})'

    # ============================================================
    # REPAYMENT TRACKING
    # ============================================================
    @property
    def total_repaid(self):
        """Sum of all repayments made against this loan."""
        agg = self.repayments.aggregate(total=models.Sum('amount'))
        return agg['total'] or 0

    # ============================================================
    # INTEREST CALCULATIONS (flat rate — standard for Chamas)
    # ============================================================
    @property
    def total_interest(self):
        """
        Total interest owed on this loan (flat rate).
        Formula: Principal × (Interest Rate / 100)

        Example: KES 5,000 at 5% → KES 250 interest
        """
        from decimal import Decimal
        return self.principal * (self.interest_rate / Decimal('100'))

    @property
    def total_repayable(self):
        """Total amount the member must pay back (principal + interest)."""
        return self.principal + self.total_interest

    @property
    def monthly_installment(self):
        """
        Fixed monthly repayment amount.
        Formula: Total Repayable / Term in Months

        Example: KES 5,250 / 3 months → KES 1,750/month
        """
        if not self.term_months or self.term_months <= 0:
            return self.total_repayable
        return self.total_repayable / self.term_months

    @property
    def balance_remaining(self):
        """Outstanding balance after subtracting what's been repaid."""
        repaid = self.total_repaid
        return max(0, self.total_repayable - repaid)

    @property
    def is_fully_repaid(self):
        """True once repayments meet or exceed the total repayable amount."""
        return self.total_repaid >= self.total_repayable

    @property
    def repayment_progress_pct(self):
        """How much has been repaid, as a percentage (0–100)."""
        total = self.total_repayable
        if total <= 0:
            return 0
        return min(100, float((self.total_repaid / total) * 100))


class LoanRepayment(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_loan_repayments',
    )
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name='repayments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.loan} — {self.amount}'



# ============================================================
# ACCOUNTS (Bank, Cash, M-Pesa)
# ============================================================
class Account(TimeStampedModel):
    ACCOUNT_TYPES = [
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('mpesa', 'M-Pesa'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_accounts',
    )
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='cash')
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return self.name

# ============================================================
# PROJECTS (New Feature)
# ============================================================
class Project(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_projects',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name

# ============================================================
# TRANSACTIONS (Cashbook)
# ============================================================
class Transaction(TimeStampedModel):
    TYPE_CHOICES = [
        ('in', 'Money In'),
        ('out', 'Money Out'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_transactions',
    )
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name='transactions',
    )
    transaction_type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    
    # Optional: link to a project
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_transaction_type_display()} {self.amount} — {self.account}'

# ============================================================
# EXPENSES
# ============================================================
class Expense(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_expenses',
    )
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses',
    )
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} — {self.amount}'



# ============================================================
# MEETINGS
# ============================================================
class Meeting(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_meetings',
    )
    title = models.CharField(max_length=200)
    scheduled_for = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    agenda = models.TextField(blank=True)
    minutes = models.TextField(blank=True)

    class Meta:
        ordering = ['-scheduled_for']

    def __str__(self):
        return f'{self.title} — {self.scheduled_for:%Y-%m-%d}'


class Attendance(TimeStampedModel):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('excused', 'Excused'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_attendance',
    )
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name='attendance',
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='attendance',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')

    class Meta:
        ordering = ['meeting', 'member']
        unique_together = [('meeting', 'member')]

    def __str__(self):
        return f'{self.member} — {self.get_status_display()}'


# ============================================================
# COMMITTEES
# ============================================================
class Committee(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_committees',
    )
    name = models.CharField(max_length=100)  # e.g., "Finance Committee", "Welfare"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return self.name


class CommitteeMember(TimeStampedModel):
    committee = models.ForeignKey(
        Committee, on_delete=models.CASCADE, related_name='members',
    )
    member = models.ForeignKey(
        'Member', on_delete=models.CASCADE, related_name='committees',
    )
    role_in_committee = models.CharField(max_length=100, blank=True)  # e.g., "Chair", "Secretary"

    class Meta:
        unique_together = [('committee', 'member')]

    def __str__(self):
        return f'{self.member.full_name} - {self.committee.name}'


class Announcement(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_announcements',
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_announcements',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

