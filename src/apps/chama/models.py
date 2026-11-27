from django.conf import settings
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone


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
    TYPE_CHOICES = [
        ('regular', 'Regular Member'),
        ('executive', 'Executive Member'),
        ('student', 'Student Member'),
        ('honorary', 'Honorary Member'),
        ('corporate', 'Corporate Member'),
        ('youth', 'Youth Member'),
        ('women', 'Women Representative'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_membership_types',
    )
    name = models.CharField(
        max_length=100,
        choices=TYPE_CHOICES,
        help_text="Select the category for this membership tier."
    )
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
        return self.get_name_display()


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
    custom_loan_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Override borrowing limit. Set to 0 to use default (3x contributions)."
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
    # ALIASES
    # ============================================================
    @property
    def phone_number(self):
        """Alias for compatibility with templates that expect phone_number."""
        return self.phone

    # ============================================================
    # BALANCE / ELIGIBILITY PROPERTIES
    # ============================================================
    @property
    def savings_balance(self):
        agg = self.savings.aggregate(total=models.Sum('amount'))
        return agg['total'] or 0

    @property
    def total_contributions_paid(self):
        agg = self.contributions.filter(paid=True).aggregate(
            total=models.Sum('amount')
        )
        return agg['total'] or 0

    @property
    def max_loan_multiplier(self):
        return 3

    @property
    def has_good_repayment_history(self):
        from datetime import timedelta
        one_year_ago = timezone.localdate() - timedelta(days=365)
        return self.loans.filter(
            status='closed',
            disbursed_on__lte=one_year_ago,
        ).exists()

    @property
    def eligible_loan_limit(self):
        if self.custom_loan_limit > 0:
            return self.custom_loan_limit
        if self.has_good_repayment_history:
            return self.total_contributions_paid * 3
        return 0

    @property
    def total_principal_taken(self):
        agg = self.loans.filter(
            status__in=['approved', 'disbursed']
        ).aggregate(total=models.Sum('principal'))
        return agg['total'] or 0

    @property
    def available_borrowing_power(self):
        return max(0, self.eligible_loan_limit - self.total_principal_taken)

    @property
    def active_loans_total(self):
        active_loans = self.loans.filter(status__in=['approved', 'disbursed'])
        return sum(loan.total_repayable for loan in active_loans)

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
    paid_on_time = models.BooleanField(
        default=True,
        help_text="Uncheck if paid after the deadline.",
    )

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
    paid_on = models.DateField(null=True, blank=True)   # 👈 ADDED

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.member} — {self.reason} ({self.amount})'


# ============================================================
# LOAN TYPES
# ============================================================
class LoanType(TimeStampedModel):
    LOAN_NAME_CHOICES = [
        ('emergency', 'Emergency Loan'),
        ('development', 'Development Loan'),
        ('school_fees', 'School Fees Loan'),
        ('business', 'Business Loan'),
        ('agriculture', 'Agriculture Loan'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='chama_loan_types',
    )
    name = models.CharField(
        max_length=100,
        choices=LOAN_NAME_CHOICES,
        help_text="Select the type of loan.",
    )
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text='Interest rate (%) charged on the principal amount.',
    )
    processing_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Processing fee (%) deducted from the loan at disbursement.',
    )
    max_term_months = models.PositiveIntegerField(
        default=12,
        help_text='Maximum term allowed for this loan type (in months).',
    )
    max_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text='Maximum principal allowed for this loan type (optional).',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return self.get_name_display()


# ============================================================
# GUEST MODEL (For External Loans)
# ============================================================
class Guest(TimeStampedModel):
    """
    External borrowers who are not Chama members.
    They must provide full KYC and a valid M-Pesa statement.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('blacklisted', 'Blacklisted'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_guests',
    )
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    national_id = models.CharField(max_length=50, unique=True)
    address = models.TextField(blank=True)

    # KYC Documents
    passport_photo = models.ImageField(upload_to='chama/guests/passport/', null=True, blank=True)
    id_front = models.ImageField(upload_to='chama/guests/id_front/', null=True, blank=True)
    id_back = models.ImageField(upload_to='chama/guests/id_back/', null=True, blank=True)
    mpesa_statement = models.FileField(upload_to='chama/guests/mpesa_statement/', null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f'{self.full_name} ({self.national_id})'

    # ============================================================
    # ALIASES
    # ============================================================
    @property
    def phone_number(self):
        """Alias used by external loan templates/views."""
        return self.phone

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
    def mpesa_statement_url(self):
        return _build_cloudinary_url(self.mpesa_statement, resource_type='raw')


# ============================================================
# LOANS
# ============================================================
class Loan(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('disbursed', 'Disbursed'),
        ('closed', 'Closed'),
    ]

    LOAN_CATEGORY_CHOICES = [
        ('internal', 'Internal Loan (Chama Member)'),
        ('external', 'External Loan (Guest)'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_loans',
    )

    loan_category = models.CharField(
        max_length=20, choices=LOAN_CATEGORY_CHOICES, default='internal',
        help_text="Internal = for Chama members. External = for guests.",
    )

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='loans',
        null=True, blank=True,
    )

    guest = models.ForeignKey(
        Guest, on_delete=models.CASCADE, related_name='loans',
        null=True, blank=True,
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
        borrower = (
            self.member.full_name if self.member
            else (self.guest.full_name if self.guest else 'Unknown')
        )
        return f'Loan #{self.pk} — {borrower} ({self.get_status_display()})'

    # ============================================================
    # REPAYMENT TRACKING
    # ============================================================
    @property
    def total_repaid(self):
        agg = self.repayments.aggregate(total=models.Sum('amount'))
        return agg['total'] or 0

    @property
    def total_interest(self):
        from decimal import Decimal
        return self.principal * (self.interest_rate / Decimal('100'))

    @property
    def total_repayable(self):
        return self.principal + self.total_interest

    @property
    def monthly_installment(self):
        if not self.term_months or self.term_months <= 0:
            return self.total_repayable
        return self.total_repayable / self.term_months

    @property
    def balance_remaining(self):
        repaid = self.total_repaid
        return max(0, self.total_repayable - repaid)

    @property
    def is_fully_repaid(self):
        return self.total_repaid >= self.total_repayable

    @property
    def repayment_progress_pct(self):
        total = self.total_repayable
        if total <= 0:
            return 0
        return min(100, float((self.total_repaid / total) * 100))

    # ============================================================
    # BORROWER HELPERS
    # ============================================================
    @property
    def borrower_name(self):
        if self.member:
            return self.member.full_name
        if self.guest:
            return self.guest.full_name
        return 'Unknown'

    @property
    def borrower_phone(self):
        if self.member:
            return self.member.phone
        if self.guest:
            return self.guest.phone
        return ''


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
    notes = models.TextField(blank=True)   # 👈 ADDED

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.loan} — {self.amount}'


# ============================================================
# ACCOUNTS
# ============================================================
class Account(TimeStampedModel):
    ACCOUNT_TYPES = [
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('mpesa', 'M-Pesa'),
    ]

    PURPOSE_CHOICES = [
        ('pool', 'Main Account'),
        ('welfare', 'Welfare Fund'),
        ('loans', 'Loan Fund'),
        ('projects', 'Project Fund'),
        ('emergency', 'Emergency Fund'),
        ('general', 'Operational Fund'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_accounts',
    )
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='cash')

    purpose = models.CharField(
        max_length=20,
        choices=PURPOSE_CHOICES,
        default='pool',
        help_text="Determines what this account is used for (e.g., Pool, Welfare, Loans)."
    )

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return f"{self.name} ({self.get_purpose_display()})"

    @property
    def current_balance(self):
        from django.db.models import Sum
        total_in = self.transactions.filter(transaction_type='in').aggregate(Sum('amount'))['amount__sum'] or 0
        total_out = self.transactions.filter(transaction_type='out').aggregate(Sum('amount'))['amount__sum'] or 0
        return self.opening_balance + total_in - total_out


# ============================================================
# PROJECTS
# ============================================================
class Project(TimeStampedModel):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

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
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='ongoing',
    )   # 👈 ADDED
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_projects_created',
    )   # 👈 ADDED

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name


# ============================================================
# TRANSACTIONS
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
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions',
    )

    auto_generated = models.BooleanField(
        default=False,
        help_text="True if this row mirrors another record (contribution, loan, etc.).",
    )

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_transaction_type_display()} {self.amount} — {self.account}'


# ============================================================
# EXPENSES
# ============================================================
class Expense(TimeStampedModel):
    CATEGORY_CHOICES = [
        ('operations', 'Operations'),
        ('utilities', 'Utilities'),
        ('transport', 'Transport'),
        ('meetings', 'Meetings'),
        ('welfare', 'Welfare'),
        ('maintenance', 'Maintenance'),
        ('office', 'Office Supplies'),
        ('other', 'Other'),
    ]

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
    category = models.CharField(
        max_length=100, choices=CATEGORY_CHOICES, blank=True,
    )
    description = models.TextField(blank=True)          # 👈 ADDED
    reference = models.CharField(max_length=100, blank=True)  # 👈 ADDED
    receipt = models.FileField(
        upload_to='chama/expenses/receipts/', null=True, blank=True,
    )   # 👈 ADDED

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} — {self.amount}'

    @property
    def receipt_url(self):
        return _build_cloudinary_url(self.receipt, resource_type='raw')


# ============================================================
# MEETINGS
# ============================================================
class Meeting(TimeStampedModel):
    MEETING_TYPE_CHOICES = [
        ('physical', 'Physical Meeting'),
        ('online', 'Online Meeting'),
    ]

    TARGET_AUDIENCE_CHOICES = [
        ('all', 'All Members'),
        ('executive', 'Executive Committee'),
        ('department', 'Department Committee'),
        ('treasurer', 'Treasury Committee'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='chama_meetings',
    )
    title = models.CharField(max_length=200)
    scheduled_for = models.DateTimeField(help_text="Meeting Date")
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPE_CHOICES, default='physical')
    target_audience = models.CharField(max_length=30, choices=TARGET_AUDIENCE_CHOICES, default='all')

    location = models.CharField(max_length=200, blank=True, help_text="Physical location or online link")
    agenda = models.TextField(blank=True)
    minutes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='chama_meetings_created',
    )   # 👈 ADDED

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
    name = models.CharField(max_length=100)
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
    role_in_committee = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = [('committee', 'member')]

    def __str__(self):
        return f'{self.member.full_name} - {self.committee.name}'


# ============================================================
# ANNOUNCEMENTS
# ============================================================
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
    is_pinned = models.BooleanField(default=False)              # 👈 ADDED
    expires_at = models.DateTimeField(null=True, blank=True)    # 👈 ADDED

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return self.title