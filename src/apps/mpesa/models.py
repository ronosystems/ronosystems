from django.db import models
from django.utils import timezone

from apps.companies.models import Company


class MpesaConfig(models.Model):
    """
    Per-company (optionally per-branch) M-Pesa Daraja credentials.
    Mirrors how Phone / Electronic / Accessory are scoped to a Company.
    """
    ENVIRONMENT_CHOICES = (
        ('sandbox',    'Sandbox'),
        ('production', 'Production'),
    )
    SHORTCODE_TYPES = (
        ('paybill', 'Paybill'),
        ('till',    'Buy Goods (Till)'),
    )

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='mpesa_configs'
    )
    branch = models.ForeignKey(
        'company.Branch', on_delete=models.CASCADE,
        related_name='mpesa_configs', null=True, blank=True,
        help_text="Leave empty for a company-wide config; set for a branch-specific Till."
    )

    label = models.CharField(
        max_length=100, blank=True,
        help_text="Friendly name, e.g. 'Nairobi CBD Till'"
    )
    environment = models.CharField(
        max_length=20, choices=ENVIRONMENT_CHOICES, default='sandbox'
    )

    # ---- Daraja credentials ----
    consumer_key    = models.CharField(max_length=200)
    consumer_secret = models.CharField(max_length=200)
    shortcode       = models.CharField(
        max_length=20,
        help_text="Paybill or Till number (BusinessShortCode)"
    )
    passkey = models.CharField(max_length=200)
    callback_url = models.URLField(
        max_length=500,
        help_text="Public URL Safaricom will POST the STK result to"
    )

    shortcode_type = models.CharField(
        max_length=10, choices=SHORTCODE_TYPES, default='paybill'
    )
    account_reference = models.CharField(
        max_length=50, blank=True,
        help_text="Sent as AccountReference in the STK push, e.g. 'POS-SALE'"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_mpesa_configs'
        ordering = ['company', 'branch', 'label']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['shortcode']),
        ]

    def __str__(self):
        scope = self.branch.name if self.branch else 'Company-wide'
        return f"{self.company.name} · {scope} · {self.shortcode}"

    @property
    def base_url(self):
        if self.environment == 'production':
            return 'https://api.safaricom.co.ke'
        return 'https://sandbox.safaricom.co.ke'

    @property
    def transaction_type(self):
        return (
            'CustomerBuyGoodsOnline'
            if self.shortcode_type == 'till'
            else 'CustomerPayBillOnline'
        )

    @classmethod
    def for_branch(cls, company, branch=None):
        """
        Return the most specific active config:
          1. branch-specific, if it exists and is active
          2. otherwise the company-wide config
          3. otherwise None
        """
        if branch is not None:
            cfg = cls.objects.filter(
                company=company, branch=branch, is_active=True
            ).first()
            if cfg:
                return cfg
        return cls.objects.filter(
            company=company, branch__isnull=True, is_active=True
        ).first()


class MpesaTransaction(models.Model):
    """
    Every STK push / callback, scoped to a company (and optionally branch).
    Mirrors Unit / SaleItem — always has company_id for tenant isolation.
    """
    STATUS_CHOICES = (
        ('pending',   'Pending'),
        ('success',   'Success'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
        ('timeout',   'Timeout'),
    )

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='mpesa_transactions'
    )
    branch = models.ForeignKey(
        'company.Branch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mpesa_transactions'
    )
    mpesa_config = models.ForeignKey(
        MpesaConfig, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transactions'
    )

    checkout_request_id = models.CharField(max_length=100, unique=True, db_index=True)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    mpesa_code          = models.CharField(max_length=50, blank=True, db_index=True)

    phone  = models.CharField(max_length=20, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    customer_first_name  = models.CharField(max_length=100, blank=True)
    customer_middle_name = models.CharField(max_length=100, blank=True)
    customer_last_name   = models.CharField(max_length=100, blank=True)

    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    result_desc  = models.TextField(blank=True)
    raw_callback = models.JSONField(null=True, blank=True)

    sale = models.ForeignKey(
        'epa_shop.Sale', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mpesa_transactions'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_mpesa_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'mpesa_code']),
            models.Index(fields=['checkout_request_id']),
        ]

    def __str__(self):
        return f"{self.company.name} · {self.mpesa_code or self.checkout_request_id} ({self.status})"

    @property
    def customer_name(self):
        parts = [
            self.customer_first_name or '',
            self.customer_middle_name or '',
            self.customer_last_name or '',
        ]
        return ' '.join(p.strip() for p in parts if p.strip())