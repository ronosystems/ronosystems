# apps/mpesa/models.py
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.companies.models import Company


# ============================================
# SHARED CHOICES
# ============================================
PROVIDER_CHOICES = (
    ('daraja',   'Safaricom Daraja'),
    ('kopokopo', 'Kopokopo'),
)

ENVIRONMENT_CHOICES = (
    ('sandbox',    'Sandbox'),
    ('production', 'Production'),
)

SHORTCODE_TYPES = (
    ('paybill', 'Paybill'),
    ('till',    'Buy Goods (Till)'),
)

TRANSACTION_STATUS = (
    ('pending',   'Pending'),
    ('success',   'Success'),
    ('failed',    'Failed'),
    ('cancelled', 'Cancelled'),
    ('timeout',   'Timeout'),
)


# ============================================
# M-PESA CONFIG
# ============================================
class MpesaConfig(models.Model):
    """
    Per-company (optionally per-branch) M-Pesa credentials.

    Supports two providers:
      - 'daraja'    → Safaricom's native STK Push API
      - 'kopokopo'  → Kopokopo aggregator (Incoming Payments API)

    Only the fields relevant to the selected `provider` need to be filled;
    `clean()` enforces the right set of required fields.
    """
    PROVIDER_CHOICES    = PROVIDER_CHOICES
    ENVIRONMENT_CHOICES = ENVIRONMENT_CHOICES
    SHORTCODE_TYPES     = SHORTCODE_TYPES

    provider = models.CharField(
        max_length=20, choices=PROVIDER_CHOICES,
        default='daraja', db_index=True,
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
    # blank=True on all: a Kopokopo-only row doesn't need Daraja creds.
    # clean() enforces these when provider == 'daraja'.
    consumer_key    = models.CharField(max_length=200, blank=True)
    consumer_secret = models.CharField(max_length=200, blank=True)
    shortcode       = models.CharField(
        max_length=20, blank=True,
        help_text="Daraja only: Paybill or Till number (BusinessShortCode)."
    )
    passkey = models.CharField(max_length=200, blank=True)

    callback_url = models.URLField(
        max_length=500, blank=True,
        help_text=(
            "Daraja: public URL Safaricom POSTs the STK result to. "
            "Kopokopo: webhook URL (also register it in their dashboard)."
        ),
    )

    shortcode_type = models.CharField(
        max_length=10, choices=SHORTCODE_TYPES, default='paybill'
    )
    account_reference = models.CharField(
        max_length=50, blank=True,
        help_text=(
            "Default reference sent to the provider, e.g. 'POS-SALE'. "
            "Daraja: AccountReference (max 12 chars). "
            "Kopokopo: metadata.account_reference (max 50 chars)."
        ),
    )

    # ---- Kopokopo credentials (only used when provider='kopokopo') ----
    kopokopo_client_id      = models.CharField(max_length=200, blank=True)
    kopokopo_client_secret  = models.CharField(max_length=200, blank=True)
    kopokopo_till_number    = models.CharField(
        max_length=20, blank=True,
        help_text="Kopokopo till number (Buy Goods)."
    )
    kopokopo_webhook_secret = models.CharField(
        max_length=200, blank=True,
        help_text="Used to verify X-Kopokopo-Signature on incoming webhooks."
    )

    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_mpesa_configs'
        ordering = ['company', 'branch', 'provider', 'label']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'branch', 'provider'],
                condition=models.Q(is_active=True),
                name='unique_active_provider_per_scope',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'provider', 'is_active']),
            models.Index(fields=['branch',  'provider', 'is_active']),
            models.Index(fields=['shortcode']),
            models.Index(fields=['kopokopo_till_number']),
        ]

    # ---------------- dunder ----------------
    def __str__(self):
        scope = self.branch.name if self.branch else 'Company-wide'
        ident = (
            self.shortcode
            or self.kopokopo_till_number
            or self.label
            or 'unconfigured'
        )
        return f"{self.company.name} · {scope} · {ident} ({self.get_provider_display()})"

    # ---------------- validation ----------------
    def clean(self):
        errs = {}

        if self.provider == 'daraja':
            for f in (
                'consumer_key', 'consumer_secret',
                'shortcode', 'passkey', 'callback_url',
            ):
                if not getattr(self, f):
                    errs[f] = 'Required for Daraja.'
        elif self.provider == 'kopokopo':
            for f in (
                'kopokopo_client_id', 'kopokopo_client_secret',
                'kopokopo_till_number', 'callback_url',
            ):
                if not getattr(self, f):
                    errs[f] = 'Required for Kopokopo.'

        if errs:
            raise ValidationError(errs)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ---------------- helpers ----------------
    @property
    def is_daraja(self):
        return self.provider == 'daraja'

    @property
    def is_kopokopo(self):
        return self.provider == 'kopokopo'

    @classmethod
    def for_branch(cls, company, branch=None, provider=None):
        """
        Return the most specific active config:
          1. branch-specific, if it exists and is active
          2. otherwise the company-wide config
          3. otherwise None

        If `provider` is given, only that provider is considered.
        If multiple configs exist, the most recently updated one wins.
        """
        qs = cls.objects.filter(company=company, is_active=True)
        if provider:
            qs = qs.filter(provider=provider)

        # 👈 CHANGE 1: order by updated_at for branch configs
        if branch is not None:
            cfg = qs.filter(branch=branch).order_by('-updated_at').first()
            if cfg:
                return cfg

        # 👈 CHANGE 2: order by updated_at for company-wide configs
        return qs.filter(branch__isnull=True).order_by('-updated_at').first()


# ============================================
# M-PESA TRANSACTION
# ============================================
class MpesaTransaction(models.Model):
    """
    Every STK push / callback, scoped to a company (and optionally branch).
    Mirrors Unit / SaleItem — always has company_id for tenant isolation.

    `provider_ref` is provider-agnostic:
      - Daraja    → CheckoutRequestID
      - Kopokopo  → payment_id / resourceId

    `checkout_request_id` is retained as a read-only back-compat alias so
    existing views keep working without changes.
    """
    STATUS_CHOICES = TRANSACTION_STATUS

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='mpesa_transactions'
    )
    branch = models.ForeignKey(
        'company.Branch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mpesa_transactions'
    )
    mpesa_config = models.ForeignKey(
        MpesaConfig, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mpesa_transactions'
    )

    provider = models.CharField(
        max_length=20, choices=PROVIDER_CHOICES,
        default='daraja', db_index=True,
        help_text="Which aggregator produced this transaction.",
    )

    # Provider-agnostic reference (Daraja CheckoutRequestID / Kopokopo payment_id)
    provider_ref = models.CharField(
        max_length=100, unique=True,
        help_text="Daraja CheckoutRequestID or Kopokopo payment_id.",
    )

    merchant_request_id = models.CharField(
        max_length=100, blank=True,
        help_text="Daraja only (MerchantRequestID).",
    )

    mpesa_code = models.CharField(
        max_length=50, blank=True, db_index=True,
        help_text="Safaricom receipt code (e.g. RKT1234ABCD).",
    )

    account_reference = models.CharField(
        max_length=100, blank=True, db_index=True,
        help_text=(
            "Reference sent to the provider at STK push time "
            "(e.g. C-M00001, F-M00001, POS-SALE)."
        ),
    )

    phone  = models.CharField(max_length=20, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    customer_first_name  = models.CharField(max_length=100, blank=True)
    customer_middle_name = models.CharField(max_length=100, blank=True)
    customer_last_name   = models.CharField(max_length=100, blank=True)

    status       = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
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
            models.Index(fields=['company', 'provider', 'status']),
            models.Index(fields=['company', 'mpesa_code']),
            models.Index(fields=['provider_ref']),
        ]

    # ---------------- back-compat ----------------
    @property
    def checkout_request_id(self):
        """Read-only alias — use `provider_ref` in new code."""
        return self.provider_ref

    @checkout_request_id.setter
    def checkout_request_id(self, value):
        """Allow old views that do `tx.checkout_request_id = ...` to keep working."""
        self.provider_ref = value

    # ---------------- dunder / helpers ----------------
    def __str__(self):
        ref = self.mpesa_code or self.provider_ref
        return f"{self.company.name} · {ref} ({self.status})"

    @property
    def customer_name(self):
        parts = [
            self.customer_first_name or '',
            self.customer_middle_name or '',
            self.customer_last_name or '',
        ]
        return ' '.join(p.strip() for p in parts if p.strip())

    @property
    def amount_display(self):
        """KSh formatted string, quantized to the model's precision."""
        q = Decimal('0.01')
        return f"KSh {Decimal(self.amount or 0).quantize(q, rounding=ROUND_HALF_UP):,.2f}"

    def is_final(self):
        return self.status in ('success', 'failed', 'cancelled', 'timeout')

    def mark_success(self, *, mpesa_code='', amount=None, phone=None,
                     first_name=None, middle_name=None, last_name=None,
                     result_desc='', raw_callback=None):
        """Convenience helper used by callback handlers for both providers."""
        if mpesa_code:
            self.mpesa_code = str(mpesa_code).strip().upper()
        if amount is not None:
            self.amount = Decimal(str(amount))
        if phone:
            self.phone = str(phone).strip()
        if first_name is not None:
            self.customer_first_name = first_name or ''
        if middle_name is not None:
            self.customer_middle_name = middle_name or ''
        if last_name is not None:
            self.customer_last_name = last_name or ''
        if result_desc is not None:
            self.result_desc = result_desc or ''
        if raw_callback is not None:
            self.raw_callback = raw_callback
        self.status = 'success'
        self.save()

    def mark_failed(self, *, result_desc='', raw_callback=None,
                    status='failed'):
        if status not in ('failed', 'cancelled', 'timeout'):
            status = 'failed'
        if result_desc is not None:
            self.result_desc = result_desc or ''
        if raw_callback is not None:
            self.raw_callback = raw_callback
        self.status = status
        self.save()