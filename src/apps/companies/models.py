# apps/companies/models.py

from django.db import models
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.business_types.business_type_registry import (
    BusinessTypeEnum,
    BUSINESS_TYPE_CHOICES,
)


# ============================================
# BUSINESS TYPE
# ============================================

class BusinessType(models.Model):
    """
    Business Type model with strict validation.
    Only allows creation of business types defined in the registry.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        choices=BUSINESS_TYPE_CHOICES,
    )
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def clean(self):
        if not BusinessTypeEnum.validate_name(self.name):
            valid_names = ', '.join(BusinessTypeEnum.get_all_names())
            raise ValidationError(
                f"Invalid business type. Must be one of: {valid_names}"
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def integration(self):
        return BusinessTypeEnum.get_integration(self.name)

    @property
    def slug(self):
        from apps.business_types.business_type_registry import BUSINESS_TYPE_SLUGS
        return BUSINESS_TYPE_SLUGS.get(self.name)

    @property
    def app_module(self):
        from apps.business_types.business_type_registry import BUSINESS_TYPE_APPS
        return BUSINESS_TYPE_APPS.get(self.name)

    class Meta:
        db_table = 'rono_business_types'
        ordering = ['name']


# ============================================
# COMPANY
# ============================================

class Company(models.Model):
    """
    Company model - the main tenant.

    `plan` is a ForeignKey to plans.Plan (single source of truth).
    Subscription history lives in plans.Subscription.
    `plan` here is a denormalized cache kept in sync via signals.

    Access control is enforced through `can_access_system()`,
    which the SubscriptionExpiryMiddleware calls on every request.
    """

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )

    # ---------- Identity ----------
    name = models.CharField(max_length=200)
    business_type = models.ForeignKey(
        BusinessType,
        on_delete=models.SET_NULL,
        null=True,
        related_name='companies',
    )
    registration_number = models.CharField(max_length=100, unique=True, blank=True)

    # ---------- Address ----------
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)

    # ---------- Contact ----------
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)

    # ---------- Settings ----------
    company_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Company settings stored as JSON",
    )

    # ---------- Subscription (denormalized cache) ----------
    plan = models.ForeignKey(
        'plans.Plan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='companies',
        help_text="Current plan (synced from active subscription)",
    )
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)

    # ---------- Status ----------
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)

    # ---------- Metadata ----------
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_companies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ============================================
    # STRING / META
    # ============================================

    def __str__(self):
        plan_name = self.plan.display_name if self.plan else 'No Plan'
        return f"{self.name} ({plan_name})"

    class Meta:
        db_table = 'rono_companies'
        ordering = ['name']
        verbose_name_plural = 'Companies'

    # ============================================
    # SUBSCRIPTION ACCESSORS
    # ============================================

    @property
    def active_subscription(self):
        """Most recent Subscription row marked 'active' (no date check)."""
        return (
            self.subscriptions
            .filter(status='active')
            .select_related('plan')
            .order_by('-created_at')
            .first()
        )

    @property
    def latest_subscription(self):
        """Most recent subscription row REGARDLESS of status."""
        return (
            self.subscriptions
            .select_related('plan')
            .order_by('-created_at')
            .first()
        )

    @property
    def current_subscription(self):
        """Active one if it exists; otherwise the latest row (even if expired)."""
        return self.active_subscription or self.latest_subscription

    @property
    def current_plan(self):
        """
        Effective plan:
          1. Active subscription plan (if still valid)
          2. Direct plan FK
          3. Free plan fallback
        """
        sub = self.active_subscription
        if sub and sub.is_active_subscription():
            return sub.plan

        if self.plan:
            return self.plan

        from apps.plans.models import Plan
        return Plan.objects.filter(name='free', is_active=True).first()

    # ============================================
    # SUBSCRIPTION STATE
    # ============================================

    @property
    def is_subscription_active(self):
        if not self.is_active:
            return False
        if self.status == 'suspended':
            return False

        sub = self.active_subscription
        if not sub:
            return False
        if sub.end_date and timezone.now() > sub.end_date:
            return False
        return True

    @property
    def is_expired(self):
        if self.status == 'suspended':
            return False
        if not self.is_active:
            return True

        sub = self.active_subscription
        if not sub:
            return True
        if sub.end_date and timezone.now() > sub.end_date:
            return True
        return False

    @property
    def is_suspended(self):
        return self.status == 'suspended'

    @property
    def subscription_days_remaining(self):
        sub = self.active_subscription or self.latest_subscription
        if not sub or not sub.end_date:
            return None
        return max(0, (sub.end_date - timezone.now()).days)

    @property
    def subscription_days_since_expiry(self):
        sub = self.latest_subscription
        if not sub or not sub.end_date:
            return None
        if timezone.now() <= sub.end_date:
            return None
        return (timezone.now() - sub.end_date).days

    def get_plan_details(self):
        return self.current_plan

    # ============================================
    # ACCESS CONTROL
    # ============================================

    def can_access_system(self):
        """
        Master gate. Returns (allowed: bool, reason: str).
        Used by SubscriptionExpiryMiddleware on every request.

        Order (most specific reason first):
          1. Suspended
          2. Subscription expired (via latest_subscription)
          3. Manually deactivated
          4. No active subscription
          5. Active subscription is not 'active'
          6. OK
        """
        # 1. Suspended
        if self.status == 'suspended':
            return False, "Your company account is suspended. Contact support."

        # 2. Subscription expired — most informative message
        latest = self.latest_subscription
        if latest and latest.end_date and timezone.now() > latest.end_date:
            return False, (
                f"Your subscription expired on "
                f"{latest.end_date:%Y-%m-%d}. Please renew to continue."
            )

        # 3. Deactivated but subscription is not expired
        if not self.is_active:
            return False, "Your company account has been deactivated. Contact support."

        # 4. No active subscription
        sub = self.active_subscription
        if not sub:
            return False, "No active subscription found. Please renew to continue."

        # 5. Subscription exists but status isn't 'active'
        if sub.status != 'active':
            return False, (
                f"Your subscription is {sub.get_status_display().lower()}. "
                "Please renew to continue."
            )

        # 6. All good
        return True, "OK"

    def mark_subscription_expired(self):
        """
        Mark the latest subscription AND the company as expired/inactive.
        Returns True if any change was made.
        """
        changed = False

        sub = self.active_subscription
        if sub and sub.end_date and timezone.now() > sub.end_date and sub.status == 'active':
            sub.status = 'expired'
            sub.save(update_fields=['status'])
            changed = True

        if self.status == 'active':
            self.status = 'inactive'
            self.is_active = False
            self.save(update_fields=['status', 'is_active'])
            changed = True

        return changed

    # ============================================
    # FEATURE FLAGS
    # ============================================

    @property
    def plan_features(self):
        plan = self.current_plan
        if not plan:
            return {
                'has_api_access': False,
                'has_advanced_reports': False,
                'has_custom_branding': False,
                'has_priority_support': False,
                'has_bulk_import': False,
                'has_custom_domain': False,
                'has_mpesa_integration': False,
            }
        return {
            'has_api_access': plan.has_api_access,
            'has_advanced_reports': plan.has_advanced_reports,
            'has_custom_branding': plan.has_custom_branding,
            'has_priority_support': plan.has_priority_support,
            'has_bulk_import': plan.has_bulk_import,
            'has_custom_domain': plan.has_custom_domain,
            'has_mpesa_integration': plan.has_mpesa_intergration,  # model spelling
        }

    def has_feature(self, feature_name):
        return self.plan_features.get(feature_name, False)

    # ============================================
    # LIMITS
    # ============================================

    @property
    def limits(self):
        plan = self.current_plan
        if not plan:
            return {
                'employees': 5,
                'companies': 1,
                'branches': 1,
                'storage': 100,
            }
        return {
            'employees': plan.max_employees,
            'companies': plan.max_companies,
            'branches': plan.max_branches,
            'storage': plan.max_storage,
        }

    def can_add_employee(self):
        return self.users.count() < self.limits['employees']

    def can_add_branch(self):
        branch_count = getattr(self, 'branches', None)
        if branch_count is None:
            return True
        return branch_count.count() < self.limits['branches']

    def can_add_company(self):
        child_count = Company.objects.filter(
            parent=self
        ).count() if hasattr(self, 'parent') else 0
        return child_count < self.limits['companies']

    # ============================================
    # BUSINESS TYPE HELPERS
    # ============================================

    @property
    def business_type_slug(self):
        return self.business_type.slug if self.business_type else None

    @property
    def business_type_app(self):
        return self.business_type.app_module if self.business_type else None


# ============================================
# SUPPORT SESSION
# ============================================

class SupportSession(models.Model):
    """Track super admin support sessions for audit."""
    super_admin = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_sessions',
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='support_sessions',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    reason = models.TextField(blank=True, help_text="Why support was needed")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'rono_support_sessions'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['company', '-started_at']),
            models.Index(fields=['super_admin', '-started_at']),
        ]

    def __str__(self):
        return f"{self.super_admin.username} → {self.company.name} ({self.started_at})"

    def end_session(self):
        self.is_active = False
        self.ended_at = timezone.now()
        self.save()