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
    
    # Define the exact choices allowed for Chama membership
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
    
    # Changed from CharField to use choices
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
        # Ensures a company doesn't create the same type twice
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
        help_text="Override borrowing limit for staff members. Set to 0 to use default (3x contributions)."
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
    def has_good_repayment_history(self):
        """
        Returns True if the member has at least one loan that was 
        disbursed > 1 year ago and fully repaid (closed).
        """
        from datetime import timedelta
        
        one_year_ago = timezone.localdate() - timedelta(days=365)
        
        # Look for a loan that was disbursed before one_year_ago and is now closed
        good_loan = self.loans.filter(
            status='closed',
            disbursed_on__lte=one_year_ago
        ).exists()
        
        return good_loan

    @property
    def eligible_loan_limit(self):
        """
        Maximum borrowing based on:
        1. Custom limit set by committee (if > 0)
        2. 3x contributions IF they have 1 year of good history
        3. 0 (meaning they must rely on committee limit)
        """
        # 1. If the committee set a custom limit, use that.
        if self.custom_loan_limit > 0:
            return self.custom_loan_limit
            
        # 2. If they have good history, apply the 3x rule
        if self.has_good_repayment_history:
            return self.total_contributions_paid * 3
            
        # 3. If they don't meet the qualification, they get 0 (must be set by committee)
        return 0

    @property
    def total_principal_taken(self):
        """Sum of PRINCIPAL for all active loans (approved or disbursed)."""
        agg = self.loans.filter(
            status__in=['approved', 'disbursed']
        ).aggregate(total=models.Sum('principal'))
        return agg['total'] or 0

    @property
    def available_borrowing_power(self):
        """How much they can still borrow (Limit - Principal Taken)."""
        return max(0, self.eligible_loan_limit - self.total_principal_taken)

    @property
    def active_loans_total(self):
        """Sum of TOTAL REPAYABLE (Principal + Interest) for active loans."""
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
        help_text="Select the type of loan (e.g., Emergency, Development).",
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
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('blacklisted', 'Blacklisted')],
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
    
    # 👇 NEW: Category field
    loan_category = models.CharField(
        max_length=20, choices=LOAN_CATEGORY_CHOICES, default='internal',
        help_text="Internal = for Chama members. External = for guests.",
    )
    
    # Member (for Internal Loans)
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='loans',
        null=True, blank=True,
    )
    
    # Guest (for External Loans)
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
        borrower = self.member.full_name if self.member else (self.guest.full_name if self.guest else 'Unknown')
        return f'Loan #{self.pk} — {borrower} ({self.get_status_display()})'

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
# ACCOUNTS (Bank, Cash, M-Pesa, Welfare, Loans, Projects)
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
        default='pool', # Default to pool for new accounts
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
        
        # Sum of Money In
        total_in = self.transactions.filter(transaction_type='in').aggregate(Sum('amount'))['amount__sum'] or 0
        # Sum of Money Out
        total_out = self.transactions.filter(transaction_type='out').aggregate(Sum('amount'))['amount__sum'] or 0
        
        return self.opening_balance + total_in - total_out




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
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    # 👇 NEW: mark rows created automatically by Contribution/Loan/Savings/etc.
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



