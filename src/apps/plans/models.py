# apps/plans/models.py

from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.db import models, transaction
from django.utils import timezone

from apps.companies.models import Company


# ============================================================
# HELPERS
# ============================================================

def _as_decimal(value, default='0'):
    """Safe Decimal coercion — never raises on '', None, or junk."""
    if value in (None, ''):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _as_int(value, default=0):
    """Safe int coercion — never raises on '', None, or junk."""
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ============================================================
# PLAN
# ============================================================

class Plan(models.Model):
    """Subscription plans for companies."""

    PLAN_TYPES = (
        ('free', 'FREE'),
        ('basic', 'BASIC'),
        ('premium', 'PREMIUM'),
        ('standard', 'STANDARD'),
        ('enterprise', 'ENTERPRISE'),
    )

    BILLING_CYCLES = (
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('lifetime', 'Lifetime'),
    )

    # CHANGED: `name` is no longer `choices`+`unique` — that combination
    # limited you to 5 plans ever. We keep `plan_kind` for the grouping
    # (used by the UI to say "show all Premium plans"), and make
    # (name, billing_cycle) unique so Premium Monthly and Premium Yearly
    # can coexist as separate purchasable rows.
    plan_kind = models.CharField(
        max_length=20,
        choices=PLAN_TYPES,
        default='basic',
        help_text='Grouping used by the UI (free / basic / premium / …).',
    )
    name = models.CharField(
        max_length=50,
        help_text='Internal plan name. Unique together with billing_cycle.',
    )
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle = models.CharField(
        max_length=20, choices=BILLING_CYCLES, default='monthly',
    )
    currency = models.CharField(max_length=3, default='KES')

    # Limits
    max_employees = models.IntegerField(default=5)
    max_companies = models.IntegerField(default=1)
    max_branches = models.IntegerField(default=1)
    max_storage = models.IntegerField(default=100, help_text="Storage in MB")

    # Feature flags
    has_api_access = models.BooleanField(default=False)
    has_advanced_reports = models.BooleanField(default=False)
    has_custom_branding = models.BooleanField(default=False)
    has_priority_support = models.BooleanField(default=False)
    has_bulk_import = models.BooleanField(default=False)
    has_custom_domain = models.BooleanField(default=False)
    has_mpesa_integration = models.BooleanField(default=False)
    has_treasury = models.BooleanField(default=False)
    has_workshop = models.BooleanField(
        default=False,
        help_text='Company can access the workshop / technician app.',
    )

    # Business type access
    allowed_business_types = models.ManyToManyField(
        'companies.BusinessType',
        blank=True,
        related_name='allowed_plans',
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # NEW: Single source of truth for feature flags. Iterating this list
    # drives forms, serialization, and get_feature_list() — so adding a
    # new feature is a one-line change instead of eight.
    FEATURE_FLAGS = (
        ('has_api_access',          'API Access'),
        ('has_advanced_reports',    'Advanced Reports'),
        ('has_custom_branding',     'Custom Branding'),
        ('has_priority_support',    'Priority Support'),
        ('has_bulk_import',         'Bulk Import'),
        ('has_custom_domain',       'Custom Domain'),
        ('has_mpesa_integration',   'M-Pesa Integration'),
        ('has_treasury',            'MpesaShop / Treasury'),
        ('has_workshop',            'Workshop / Technician App'),
    )

    class Meta:
        db_table = 'plans'
        ordering = ['order', 'price']
        # CHANGED: name alone is no longer unique.
        unique_together = (('name', 'billing_cycle'),)
        indexes = [
            models.Index(fields=['is_active', 'order']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.billing_cycle})"

    # ---------- Feature helpers ----------

    def enabled_features(self):
        """Dict of {flag_name: bool} — used by APIs and templates."""
        return {flag: getattr(self, flag) for flag, _ in self.FEATURE_FLAGS}

    def get_feature_list(self):
        """Human-readable list of capabilities for the pricing UI."""
        features = [
            f"Up to {self.max_employees} employees",
            f"Up to {self.max_companies} company" +
            ("ies" if self.max_companies != 1 else ""),
        ]
        if self.max_branches > 1:
            features.append(f"Up to {self.max_branches} branches")
        for flag, label in self.FEATURE_FLAGS:
            if getattr(self, flag):
                features.append(label)
        return features


# ============================================================
# SUBSCRIPTION
# ============================================================

class Subscription(models.Model):
    """A company's subscription to a plan."""

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('pending', 'Pending'),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )

    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='active',
    )

    # ---------- Payment info ----------
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=200, blank=True)

    payment_receipt = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Cloudinary public_id of the uploaded receipt.',
    )
    payment_message = models.TextField(
        blank=True, default='',
        help_text='M-Pesa / bank confirmation message pasted by the customer.',
    )

    # Review tracking
    reviewed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_payments',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(
        blank=True, default='',
        help_text='Optional note from the reviewer.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'payment_method']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['end_date']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.plan.display_name}"

    # ============================================
    # CORE HELPERS
    # ============================================

    def is_active_subscription(self):
        """True if status is active AND (no end date OR end date in the future)."""
        if self.status != 'active':
            return False
        if self.end_date and timezone.now() > self.end_date:
            return False
        return True

    # ============================================
    # FEATURE ACCESS
    # ============================================

    @property
    def has_workshop_access(self):
        """Single source of truth for gating the workshop app."""
        return bool(self.is_active_subscription() and self.plan
                    and self.plan.has_workshop)

    def feature_enabled(self, flag_name):
        """Generic feature check: `sub.feature_enabled('has_treasury')`."""
        if not self.is_active_subscription():
            return False
        return bool(self.plan and getattr(self.plan, flag_name, False))

    # ============================================
    # DATE HELPERS
    # ============================================

    @property
    def is_lifetime(self):
        return self.end_date is None

    @property
    def is_expired_now(self):
        if not self.end_date:
            return False
        return timezone.now() > self.end_date

    @property
    def days_until_expiry(self):
        """
        Days until end_date.
        - None if lifetime (no end_date)
        - 0 if already expired or expiring today
        Kept clamped for backwards compatibility with templates.
        """
        if not self.end_date:
            return None
        delta = self.end_date - timezone.now()
        return max(0, delta.days)

    @property
    def signed_days_until_expiry(self):
        """
        NEW: Like days_until_expiry but can be negative.
        Useful for analytics; templates should use display_state instead.
        """
        if not self.end_date:
            return None
        return (self.end_date - timezone.now()).days

    @property
    def days_since_expiry(self):
        if not self.end_date or timezone.now() <= self.end_date:
            return None
        return (timezone.now() - self.end_date).days

    # ============================================
    # DISPLAY STATE
    # ============================================

    @property
    def display_state(self):
        """
        'lifetime' | 'expired' | 'pending' | 'cancelled' | 'inactive'
        | 'active' | 'expiring'
        """
        if self.status == 'pending':
            return 'pending'
        if self.status == 'cancelled':
            return 'cancelled'
        if self.status == 'inactive':
            return 'inactive'
        if self.status == 'expired' or self.is_expired_now:
            return 'expired'
        if self.end_date is None:
            return 'lifetime'
        days = self.days_until_expiry
        if days is not None and days <= 7:
            return 'expiring'
        return 'active'

    # ============================================
    # RECEIPT HELPERS
    # ============================================

    @property
    def has_receipt(self):
        return bool(self.payment_receipt and self.payment_receipt.strip())

    @property
    def is_manual_pending(self):
        """Pending manual payment awaiting review (not M-Pesa/STK)."""
        if self.status != 'pending' or not self.payment_method:
            return False
        return self.payment_method not in ('mpesa', 'stk')

    def get_receipt_url(self):
        """Cloudinary URL (image or raw) with a MEDIA_URL fallback."""
        if not self.has_receipt:
            return None

        key = self.payment_receipt.strip().lstrip('/')
        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')

        if cloud_name:
            resource = 'raw' if key.lower().endswith('.pdf') else 'image'
            return f"https://res.cloudinary.com/{cloud_name}/{resource}/upload/{key}"

        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"

    # ============================================
    # AUTO-EXPIRE
    # ============================================

    def mark_expired(self, save=True):
        if self.status == 'active' and self.is_expired_now:
            self.status = 'expired'
            if save:
                self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    # ============================================
    # REVIEW ACTIONS
    # ============================================

    @transaction.atomic
    def approve(self, by_user, note='', save=True):
        """
        Approve this pending payment → status becomes 'active'.
        Expires any other active subscription for the same company and
        rebuilds the Company cache. All writes are atomic.
        """
        if self.status != 'pending':
            return False

        # Expire other active subs (skip self).
        (self.company.subscriptions
            .filter(status='active')
            .exclude(pk=self.pk)
            .update(status='expired'))

        self.status = 'active'
        self.reviewed_by = by_user
        self.reviewed_at = timezone.now()
        self.review_note = (note or '').strip()

        if save:
            self.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_at',
                'review_note', 'updated_at',
            ])
            # NEW: all Company-side sync flows through one function.
            sync_company_from_subscription(self.company)

        return True

    @transaction.atomic
    def reject(self, by_user, note='', save=True):
        """Reject this pending payment → status becomes 'cancelled'."""
        if self.status != 'pending':
            return False

        self.status = 'cancelled'
        self.reviewed_by = by_user
        self.reviewed_at = timezone.now()
        self.review_note = (note or '').strip()

        if save:
            self.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_at',
                'review_note', 'updated_at',
            ])
            sync_company_from_subscription(self.company)
        return True

    @transaction.atomic
    def cancel(self, by_user=None, note='', save=True):
        """NEW: Cancel an active subscription (not just pending ones)."""
        if self.status not in ('active', 'pending'):
            return False

        self.status = 'cancelled'
        if by_user is not None:
            self.reviewed_by = by_user
            self.reviewed_at = timezone.now()
        if note:
            self.review_note = note.strip()

        if save:
            self.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_at',
                'review_note', 'updated_at',
            ])
            sync_company_from_subscription(self.company)
        return True


# ============================================================
# PLAN FEATURE
# ============================================================

class PlanFeature(models.Model):
    """Optional marketing-style feature rows for a plan."""

    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name='features',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'plan_features'
        ordering = ['order']

    def __str__(self):
        return f"{self.plan.display_name} - {self.name}"


# ============================================================
# SINGLE WRITER: COMPANY ↔ SUBSCRIPTION SYNC
# ============================================================
# Every place that changes a subscription's plan / dates / status MUST
# call this function. No more inline `company.save(update_fields=[...])`
# scattered across views, approve(), reject(), cancel(), etc.

def sync_company_from_subscription(company, active_sub=None):
    """
    Rebuild Company.plan / subscription_start / subscription_end / status /
    is_active from the company's CURRENT active subscription.

    If `active_sub` is passed, we trust the caller that it's the active one.
    Otherwise we look it up.
    """
    if active_sub is None:
        active_sub = (
            company.subscriptions
            .filter(status='active')
            .order_by('-created_at')
            .first()
        )

    if active_sub and active_sub.is_active_subscription():
        company.plan = active_sub.plan
        company.subscription_start = active_sub.start_date
        company.subscription_end = active_sub.end_date
        company.status = 'active'
        company.is_active = True
        company.save(update_fields=[
            'plan', 'subscription_start', 'subscription_end',
            'status', 'is_active',
        ])
    else:
        # No active sub → mark company inactive but DO NOT clear company.plan.
        # Keeping the last known plan preserves history and lets the UI
        # show "Your Premium subscription expired on …".
        company.status = 'inactive'
        company.is_active = False
        company.save(update_fields=['status', 'is_active'])


# ============================================================
# BULK HELPERS (called by management commands / cron)
# ============================================================

class SubscriptionQuerySet(models.QuerySet):

    def mark_all_expired(self):
        """
        Bulk-flip active subs whose end_date has passed.
        Returns the number of rows updated. One SQL statement.
        """
        now = timezone.now()
        return (self.filter(status='active', end_date__lt=now)
                    .update(status='expired', updated_at=now))


Subscription.add_to_class(
    'objects',
    SubscriptionQuerySet.as_manager(),
)