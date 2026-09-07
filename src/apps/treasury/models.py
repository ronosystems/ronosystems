from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from apps.epa_shop.models import Branch
from apps.companies.models import Company

User = get_user_model()

# ============================================
# TREASURY - PER COMPANY & BRANCH
# ============================================
class Treasury(models.Model):
    """
    Treasury account per company and branch
    This holds the aggregate net balance but individual accounts are tracked separately
    """
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='treasuries'
    )
    branch = models.OneToOneField(
        Branch, 
        on_delete=models.CASCADE, 
        related_name='treasury'
    )
    
    # Aggregated balances (calculated from daily records)
    total_bank_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0, 
        help_text="Total of all bank accounts"
    )
    total_mpesa_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0, 
        help_text="Total of all M-Pesa accounts"
    )
    cash_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0, 
        help_text="Physical Cash in Shop"
    )
    credit_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0, 
        help_text="Money owed to you / Credit float"
    )

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def net_balance(self):
        """NET BALANCE = Total Bank + Total M-Pesa + Cash + Credit"""
        return self.total_bank_balance + self.total_mpesa_balance + self.cash_balance + self.credit_balance

    @property
    def liquid_balance(self):
        """Only liquid: Total Bank + Total M-Pesa + Cash"""
        return self.total_bank_balance + self.total_mpesa_balance + self.cash_balance

    def __str__(self):
        return f"Treasury - {self.company.name} - {self.branch.name} | Net: {self.net_balance}"

    class Meta:
        verbose_name_plural = "Treasuries"
        ordering = ['company', 'branch__name']
        unique_together = ['company', 'branch']


# ============================================
# BANK ACCOUNT
# ============================================
class BankAccount(models.Model):
    """
    Individual bank account with daily balance tracking
    """
    class BankType(models.TextChoices):
        EQUITY = 'EQUITY', 'Equity Bank'
        KCB = 'KCB', 'KCB Bank'
        COOP = 'COOP', 'Co-operative Bank'
        ABSA = 'ABSA', 'ABSA Bank'
        STANBIC = 'STANBIC', 'Stanbic Bank'
        STANDARD_CHARTERED = 'SC', 'Standard Chartered'
        NCBA = 'NCBA', 'NCBA Bank'
        DIAMOND_TRUST = 'DTB', 'Diamond Trust Bank'
        FAMILY = 'FAMILY', 'Family Bank'
        GUARDIAN = 'GUARDIAN', 'Guardian Bank'
        OTHER = 'OTHER', 'Other'

    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='bank_accounts'
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.CASCADE, 
        related_name='bank_accounts'
    )
    treasury = models.ForeignKey(
        Treasury, 
        on_delete=models.CASCADE, 
        related_name='bank_accounts'
    )
    
    # Bank details
    bank_type = models.CharField(
        max_length=20, 
        choices=BankType.choices, 
        default=BankType.OTHER
    )
    account_name = models.CharField(
        max_length=200, 
        help_text="Enter bank account name (e.g., KCB A, KCB B, ABSA A)"
    )
    account_number = models.CharField(
        max_length=50, 
        help_text="Enter bank account number"
    )
    branch_code = models.CharField(max_length=20, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    
    # Current balance (last recorded daily balance)
    current_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Current/Last recorded balance for this account"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company', 'bank_type', 'account_name']
        unique_together = ['company', 'branch', 'account_name', 'account_number']
        indexes = [
            models.Index(fields=['company', 'branch', 'is_active']),
            models.Index(fields=['account_number']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.get_bank_type_display()} - {self.account_name} ({self.account_number})"

    def save(self, *args, **kwargs):
        # Ensure treasury exists
        if not self.treasury_id:
            treasury, created = Treasury.objects.get_or_create(
                company=self.company,
                branch=self.branch
            )
            self.treasury = treasury
        
        # If primary, unset other primary for this branch
        if self.is_primary:
            BankAccount.objects.filter(
                company=self.company, 
                branch=self.branch, 
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        
        super().save(*args, **kwargs)


# ============================================
# MPESA ACCOUNT
# ============================================
class MpesaAccount(models.Model):
    """
    Individual M-Pesa account with daily balance tracking
    """
    class MpesaType(models.TextChoices):
        PAYBILL = 'PAYBILL', 'Paybill'
        TILL = 'TILL', 'Till Number'
        SEND_MONEY = 'SEND_MONEY', 'Send Money'

    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='mpesa_accounts'
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.CASCADE, 
        related_name='mpesa_accounts'
    )
    treasury = models.ForeignKey(
        Treasury, 
        on_delete=models.CASCADE, 
        related_name='mpesa_accounts'
    )
    
    # M-Pesa details
    till_name = models.CharField(
        max_length=200, 
        help_text="Enter M-Pesa Till/Account name (e.g., MPESA A, MPESA B)"
    )
    till_number = models.CharField(
        max_length=20, 
        help_text="Enter M-Pesa Till number"
    )
    store_number = models.CharField(max_length=20, blank=True)
    account_type = models.CharField(
        max_length=20, 
        choices=MpesaType.choices, 
        default=MpesaType.TILL
    )
    
    # Current balance (last recorded daily balance)
    current_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Current/Last recorded balance for this M-Pesa account"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company', 'till_name']
        unique_together = ['company', 'branch', 'till_name', 'till_number']
        indexes = [
            models.Index(fields=['company', 'branch', 'is_active']),
            models.Index(fields=['till_number']),
        ]

    def __str__(self):
        return f"{self.company.name} - M-Pesa - {self.till_name} ({self.till_number})"

    def save(self, *args, **kwargs):
        # Ensure treasury exists
        if not self.treasury_id:
            treasury, created = Treasury.objects.get_or_create(
                company=self.company,
                branch=self.branch
            )
            self.treasury = treasury
        
        # If primary, unset other primary for this branch
        if self.is_primary:
            MpesaAccount.objects.filter(
                company=self.company, 
                branch=self.branch, 
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        
        super().save(*args, **kwargs)


# ============================================
# DAILY RECORD - INDIVIDUAL ACCOUNT BALANCES
# ============================================
class DailyRecord(models.Model):
    """
    Daily snapshot - records EACH individual account balance
    This is the main table you'll use to track daily balances
    """
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='daily_records'
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.CASCADE, 
        related_name='daily_records'
    )
    treasury = models.ForeignKey(
        Treasury, 
        on_delete=models.CASCADE, 
        related_name='daily_records'
    )
    date = models.DateField(default=timezone.now)

    # Cash balance (physical cash in shop)
    cash_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Physical cash in shop"
    )
    
    # Credit balance (money owed to you)
    credit_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Money owed to you / Credit float"
    )
    
    # Notes for this day
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_bank_balance(self):
        """Sum of all bank account balances for this day"""
        return self.bank_balances.aggregate(
            total=models.Sum('closing_balance')
        )['total'] or 0

    @property
    def total_mpesa_balance(self):
        """Sum of all M-Pesa account balances for this day"""
        return self.mpesa_balances.aggregate(
            total=models.Sum('closing_balance')
        )['total'] or 0

    @property
    def net_balance(self):
        """NET BALANCE = Total Bank + Total M-Pesa + Cash + Credit"""
        return self.total_bank_balance + self.total_mpesa_balance + self.cash_balance + self.credit_balance

    def __str__(self):
        return f"Daily Record - {self.company.name} - {self.branch.name} - {self.date} | Net: {self.net_balance}"

    class Meta:
        unique_together = ['company', 'branch', 'date']
        ordering = ['company', 'branch', '-date']
        indexes = [
            models.Index(fields=['company', 'branch', 'date']),
            models.Index(fields=['company', 'date']),
        ]


# ============================================
# DAILY BANK BALANCE
# ============================================
class DailyBankBalance(models.Model):
    """
    Daily closing balance for a specific bank account
    """
    daily_record = models.ForeignKey(
        DailyRecord, 
        on_delete=models.CASCADE, 
        related_name='bank_balances'
    )
    bank_account = models.ForeignKey(
        BankAccount, 
        on_delete=models.CASCADE, 
        related_name='daily_balances'
    )
    
    # The closing balance for this specific account on this day
    closing_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Closing balance for this bank account"
    )
    
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['daily_record', 'bank_account']
        ordering = ['bank_account__bank_type', 'bank_account__account_name']

    def __str__(self):
        return f"{self.bank_account.account_name} - {self.closing_balance} ({self.daily_record.date})"


# ============================================
# DAILY MPESA BALANCE
# ============================================
class DailyMpesaBalance(models.Model):
    """
    Daily closing balance for a specific M-Pesa account
    """
    daily_record = models.ForeignKey(
        DailyRecord, 
        on_delete=models.CASCADE, 
        related_name='mpesa_balances'
    )
    mpesa_account = models.ForeignKey(
        MpesaAccount, 
        on_delete=models.CASCADE, 
        related_name='daily_balances'
    )
    
    # The closing balance for this specific M-Pesa account on this day
    closing_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Closing balance for this M-Pesa account"
    )
    
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['daily_record', 'mpesa_account']
        ordering = ['mpesa_account__till_name']

    def __str__(self):
        return f"{self.mpesa_account.till_name} - {self.closing_balance} ({self.daily_record.date})"


# ============================================
# MOVEMENTS (BOOST & TRANSFERS)
# ============================================
class Movement(models.Model):
    """
    Track money movements (BOOST or Transfers)
    """
    class AccountType(models.TextChoices):
        BANK = 'BANK', 'Bank'
        MPESA = 'MPESA', 'M-Pesa'
        CASH = 'CASH', 'Cash'
        CREDIT = 'CREDIT', 'Credit'
        EXTERNAL = 'EXTERNAL', 'External (BOOST)'

    class MovementType(models.TextChoices):
        BOOST = 'BOOST', 'BOOST - External Money Injection'
        TRANSFER = 'TRANSFER', 'Transfer between accounts'
        ADJUSTMENT = 'ADJUSTMENT', 'Manual Adjustment'

    class BoostSource(models.TextChoices):
        PERSONAL_SAVINGS = 'PERSONAL_SAVINGS', 'Personal Savings'
        COMMISSIONS = 'COMMISSIONS', 'M-Pesa Commissions'
        INVESTOR_FUNDS = 'INVESTOR_FUNDS', 'Investor Funds'
        BANK_LOAN = 'BANK_LOAN', 'Bank Loan'
        BUSINESS_PARTNER = 'BUSINESS_PARTNER', 'Business Partner'
        PROFIT_REINVESTMENT = 'PROFIT_REINVESTMENT', 'Profit Reinvestment'
        OTHER = 'OTHER', 'Other'

    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='treasury_movements'
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.CASCADE, 
        related_name='treasury_movements'
    )
    treasury = models.ForeignKey(
        Treasury, 
        on_delete=models.CASCADE, 
        related_name='movements'
    )

    # Movement details
    movement_type = models.CharField(
        max_length=20, 
        choices=MovementType.choices, 
        default=MovementType.TRANSFER
    )
    
    from_account = models.CharField(
        max_length=20, 
        choices=AccountType.choices
    )
    to_account = models.CharField(
        max_length=20, 
        choices=AccountType.choices
    )
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.CharField(max_length=200, blank=True)
    
    # BOOST specific fields
    boost_source = models.CharField(
        max_length=30, 
        choices=BoostSource.choices, 
        null=True, 
        blank=True
    )
    boost_reference = models.CharField(max_length=100, blank=True)
    boost_notes = models.TextField(blank=True)
    
    # Optional reference to specific accounts (for transfers between specific accounts)
    from_bank_account = models.ForeignKey(
        BankAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='movements_from'
    )
    to_bank_account = models.ForeignKey(
        BankAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='movements_to'
    )
    from_mpesa_account = models.ForeignKey(
        MpesaAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='movements_from'
    )
    to_mpesa_account = models.ForeignKey(
        MpesaAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='movements_to'
    )
    
    # User tracking
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='treasury_movements'
    )
    
    # Status
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.COMPLETED
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.movement_type == MovementType.BOOST:
            return f"BOOST - {self.company.name} - {self.get_to_account_display()} : {self.amount}"
        else:
            return f"{self.company.name} - {self.get_from_account_display()} → {self.get_to_account_display()} : {self.amount}"

    class Meta:
        ordering = ['company', '-created_at']
        indexes = [
            models.Index(fields=['company', 'branch', 'created_at']),
            models.Index(fields=['company', 'movement_type']),
        ]


# ============================================
# TREASURY SUMMARY
# ============================================
class TreasurySummary(models.Model):
    """
    Pre-calculated monthly summary for faster dashboard loading
    """
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='treasury_summaries'
    )
    treasury = models.ForeignKey(
        Treasury, 
        on_delete=models.CASCADE, 
        related_name='summaries'
    )
    
    # Monthly summaries
    month = models.DateField()  # First day of the month
    
    # Opening and closing balances for the month
    opening_net_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_net_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Movement stats
    total_boost_in = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Total BOOST injections")
    total_movements_in = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_movements_out = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Counts
    boost_count = models.IntegerField(default=0)
    transfer_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['company', 'treasury', 'month']
        ordering = ['company', '-month']
        verbose_name_plural = "Treasury Summaries"

    def __str__(self):
        return f"Summary - {self.company.name} - {self.treasury.branch.name} | {self.month.strftime('%B %Y')}"


# ============================================
# TREASURY TRANSACTION LOG
# ============================================
class TreasuryTransactionLog(models.Model):
    """
    Complete audit trail for all treasury changes
    """
    TRANSACTION_TYPES = (
        ('daily_record', 'Daily Record Update'),
        ('movement', 'Account Movement'),
        ('boost', 'BOOST Injection'),
        ('manual_adjustment', 'Manual Adjustment'),
        ('sale', 'Sale'),
        ('expense', 'Expense'),
        ('purchase', 'Purchase'),
    )
    
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='treasury_logs'
    )
    treasury = models.ForeignKey(
        Treasury, 
        on_delete=models.CASCADE, 
        related_name='transaction_logs'
    )
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    # Balance changes
    bank_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    mpesa_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_change = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Reference to related objects
    content_type = models.CharField(max_length=50, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    
    description = models.CharField(max_length=255)
    performed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='treasury_logs'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company', '-created_at']
        indexes = [
            models.Index(fields=['company', 'treasury', 'created_at']),
            models.Index(fields=['company', 'transaction_type']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.transaction_type} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"