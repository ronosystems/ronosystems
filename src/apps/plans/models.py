# apps/plans/models.py

from django.db import models
from django.utils import timezone
from apps.companies.models import Company
from django.conf import settings as django_settings


class Plan(models.Model):
    """Subscription plans for companies"""

    PLAN_TYPES = (
        ('free', 'FREE'),
        ('free_trial', 'FREE TRIAL'),
        ('basic', 'BASIC'),
        ('basic_pro', 'BASIC PRO'),
        ('premium', 'PREMIUM'),
        ('premium_pro', 'PREMIUM PRO'),
        ('standard', 'STANDARD'),
        ('standard_pro', 'STANDARD PRO'),
        ('enterprise', 'ENTERPRISE'),
        ('enterprise_pro', 'ENTERPRISE PRO'),
    )

    BILLING_CYCLES = (
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
        ('lifetime', 'Lifetime'),
    )

    name = models.CharField(max_length=50, choices=PLAN_TYPES, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLES, default='monthly')
    currency = models.CharField(max_length=3, default='KES')

    # Features
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

    class Meta:
        db_table = 'plans'
        ordering = ['order', 'price']

    def __str__(self):
        return f"{self.display_name} ({self.billing_cycle})"

    # ---------- Feature list ----------
    def get_feature_list(self):
        features = []
        features.append(f"Up to {self.max_employees} employees")
        features.append(f"Up to {self.max_companies} company")

        if self.has_api_access:
            features.append("API Access")
        if self.has_advanced_reports:
            features.append("Advanced Reports")
        if self.has_custom_branding:
            features.append("Custom Branding")
        if self.has_priority_support:
            features.append("Priority Support")
        if self.has_bulk_import:
            features.append("Bulk Import")
        if self.has_custom_domain:
            features.append("Custom Domain")
        if self.has_mpesa_integration:
            features.append("M-Pesa Integration")
        if self.has_treasury:
            features.append("MpesaShop")

        return features


class Subscription(models.Model):
    """Company subscription to a plan"""

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

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # ============================================
    # PAYMENT INFO
    # ============================================
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=200, blank=True)

    # Manual / offline payment receipt
    payment_receipt = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Cloudinary public_id of the uploaded receipt.',
    )
    payment_message = models.TextField(
        blank=True, default='',
        help_text='M-Pesa / bank confirmation message pasted by the customer.',
    )

    # Review tracking (who verified this payment, and when)
    reviewed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_payments',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(
        blank=True, default='',
        help_text='Optional note from the reviewer (reason for rejection, etc.).',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'payment_method']),
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
    # DATE HELPERS (used by UI)
    # ============================================

    @property
    def is_lifetime(self):
        """No end date = never expires."""
        return self.end_date is None

    @property
    def is_expired_now(self):
        """True if end_date has passed (regardless of status)."""
        if not self.end_date:
            return False
        return timezone.now() > self.end_date

    @property
    def days_until_expiry(self):
        """
        Days until end_date.
        - Returns None if lifetime (no end_date)
        - Returns 0 if already expired or expiring today
        """
        if not self.end_date:
            return None
        delta = self.end_date - timezone.now()
        return max(0, delta.days)

    @property
    def days_since_expiry(self):
        """
        Days since end_date passed.
        - Returns None if not expired (or lifetime)
        """
        if not self.end_date:
            return None
        if timezone.now() <= self.end_date:
            return None
        return (timezone.now() - self.end_date).days

    # ============================================
    # DISPLAY STATE (for badges in list views)
    # ============================================

    @property
    def display_state(self):
        """
        Normalized state string for UI:
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
        """True if a receipt file has been uploaded."""
        return bool(self.payment_receipt and self.payment_receipt.strip())

    @property
    def is_manual_pending(self):
        """True if this is a manual payment still awaiting verification."""
        if self.status != 'pending':
            return False
        if not self.payment_method:
            return False
        if self.payment_method in ('mpesa', 'stk'):
            return False
        return True

    def get_receipt_url(self):
        """
        Return a fully-formed URL for the uploaded receipt.

        - Images → /image/upload/...
        - PDFs   → /raw/upload/...
        Falls back to MEDIA_URL for local dev.
        """
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
        """
        Flip status to 'expired' if the end_date has passed.
        Returns True if a change was made.
        """
        if self.status == 'active' and self.is_expired_now:
            self.status = 'expired'
            if save:
                self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    # ============================================
    # REVIEW ACTIONS
    # ============================================

    def approve(self, by_user, note='', save=True):
        """
        Approve this pending payment → status becomes 'active'.
        Also expires any other active subscriptions for the same company.
        Returns True if the row changed.
        """
        if self.status != 'pending':
            return False

        # Expire other active subscriptions for this company
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
                'status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at',
            ])

            # Sync Company row
            company = self.company
            company.plan = self.plan
            company.subscription_start = self.start_date
            company.subscription_end = self.end_date
            company.status = 'active'
            company.is_active = True
            company.save(update_fields=[
                'plan', 'subscription_start', 'subscription_end',
                'status', 'is_active',
            ])

        return True

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
                'status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at',
            ])
        return True


class PlanFeature(models.Model):
    """Additional features for plans"""

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