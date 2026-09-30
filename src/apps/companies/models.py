# apps/companies/models.py

import re

from django.db import models
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.business_types.business_type_registry import (
    BusinessTypeEnum,
    BUSINESS_TYPE_CHOICES,
)


# ============================================
# COMPANY ID GENERATOR
# ============================================

def generate_company_id(name, exclude_pk=None):
    """
    Generate a company ID in the format:  {LETTER}@RS{NNN}

    Examples:
        "Fieldmax Company"  →  F@RS001
        "Kalyet Company"    →  K@RS002

    Rules:
        - First letter is uppercased.
        - If the name starts with a non-letter, fall back to 'X'.
        - The sequential number is global (not per-letter), zero-padded to 3 digits.
        - If the number exceeds 999, it grows naturally (e.g. F@RS1000).

    The number is derived by finding the highest existing trailing number
    across ALL company_ids, then adding 1.
    """
    first_char = (name or '').strip()[:1].upper()
    if not first_char.isalpha():
        first_char = 'X'

    pattern = re.compile(r'^[A-Z]@RS(\d+)$')
    highest = 0

    qs = Company.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    for cid in qs.values_list('company_id', flat=True):
        if not cid:
            continue
        m = pattern.match(cid)
        if m:
            try:
                highest = max(highest, int(m.group(1)))
            except ValueError:
                continue

    next_number = highest + 1
    return f"{first_char}@RS{next_number:03d}"


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

    Multi-tenancy:
        - `custom_domain` identifies the tenant when a request comes in on
          a non-platform hostname (resolved by CustomDomainMiddleware).
        - Branding fields (`logo`, `favicon`, `primary_color`, ...) let each
          company customize the UI their users see.
    """

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )

    # ---------- Identity ----------
    company_id = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        blank=True,
        help_text="Auto-generated unique company ID (e.g. F@RS001). "
                  "Employees use this to register into the company.",
    )
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

    # ---------- Branding ----------
    # We do NOT use Django's ImageField here — file uploads go to Cloudinary
    # explicitly via `apps.companies.media.upload_company_media()`, and the
    # resulting public_id is stored as plain text (mirrors apps.settings).
    logo = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Cloudinary public_id for the company logo "
                  "(e.g. companies/42/logo_1789754321).",
    )
    favicon = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Cloudinary public_id for the company favicon "
                  "(e.g. companies/42/favicon_1789754321).",
    )
    login_background = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Cloudinary public_id for the login page background "
                  "(e.g. companies/42/login_background_1789754321). "
                  "Only shown when the user is on this company's domain.",
    )
    receipt_logo = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Cloudinary public_id for the receipt/ETR logo "
                  "(e.g. companies/42/receipt_logo_1789754321). "
                  "If empty, the main `logo` is used on receipts.",
    )
    
    primary_color = models.CharField(
        max_length=7,
        default='#87CEEB',
        help_text="Hex color used for primary UI accents.",
    )
    accent_color = models.CharField(
        max_length=7,
        default='#036a77',
        help_text="Hex color used for the sidebar and secondary UI accents.",
    )
    system_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display name override for the sidebar and page titles "
                  "(defaults to `name` if blank).",
    )

    # ---------- Custom Domain ----------
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="e.g., clientcompany.co.ke (no https://, no www., no trailing slash)",
    )
    domain_verified = models.BooleanField(
        default=False,
        help_text="Set to True after DNS is confirmed working",
    )

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
    # SAVE — NORMALIZE DOMAIN, GENERATE company_id
    # ============================================

    def save(self, *args, **kwargs):
        # Normalize the custom domain before persisting so lookups stay
        # consistent (no `https://`, `www.`, trailing slash, or mixed case).
        self.custom_domain = self.normalize_domain(self.custom_domain)

        # Auto-generate company_id if missing (with retry on race-condition)
        if not self.company_id:
            for _ in range(10):
                candidate = generate_company_id(self.name, exclude_pk=self.pk)
                if not Company.objects.filter(company_id=candidate).exists():
                    self.company_id = candidate
                    break
            else:
                raise RuntimeError(
                    "Could not generate a unique company_id after 10 attempts."
                )

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.custom_domain = self.normalize_domain(self.custom_domain)

    # ============================================
    # STRING / META
    # ============================================

    def __str__(self):
        plan_name = self.plan.display_name if self.plan else 'No Plan'
        return f"{self.name} [{self.company_id}] ({plan_name})"

    class Meta:
        db_table = 'rono_companies'
        ordering = ['name']
        verbose_name_plural = 'Companies'

    # ============================================
    # MEDIA URL HELPERS (Cloudinary / local)
    # ============================================

    @staticmethod
    def _build_media_url(key) -> str | None:
        """
        Build a delivery URL for a stored Cloudinary public_id.

        Falls back to the local MEDIA_URL prefix if Cloudinary isn't
        configured (dev with USE_CLOUDINARY_MEDIA=False).
        """
        if not key:
            return None
        key = str(key).strip().lstrip('/')
        if not key:
            return None

        # Strip legacy /media/ prefix if present (old uploads)
        if key.startswith('media/'):
            key = key[len('media/'):]

        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')
        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{key}"

        # Local filesystem fallback (dev with USE_CLOUDINARY_MEDIA=False)
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"


        
    @property
    def logo_url(self):
        """
        Fully-formed URL for the company logo, or None.

        Usage:
            {% if company.logo_url %}
                <img src="{{ company.logo_url }}" alt="{{ company.name }}">
            {% endif %}
        """
        return self._build_media_url(self.logo)

    @property
    def favicon_url(self):
        """
        Fully-formed URL for the company favicon, or None.

        Usage (in base.html <head>):
            {% if site_favicon_url %}
                <link rel="icon" href="{{ site_favicon_url }}">
            {% endif %}
        """
        return self._build_media_url(self.favicon)

    @property
    def login_background_url(self):
        """
        Cloudinary URL for the login-page background, or None.

        Usage (in your login template):
            {% if login_background_url %}
                body::before { background: url('{{ login_background_url }}') ... }
            {% endif %}
        """
        return self._build_media_url(self.login_background)

    @property
    def receipt_logo_url(self):
        """
        Fully-formed URL for the receipt-specific logo, or None.

        Deliberately does NOT fall back to `logo_url` — the settings UI
        needs to know whether a dedicated receipt logo was actually set
        (to show the "Remove" checkbox and preview correctly).
        Fallback happens in the receipt template itself.
        """
        return self._build_media_url(self.receipt_logo)

        
    @property
    def display_name(self):
        """`system_name` if set, otherwise fall back to `name`."""
        return (self.system_name or '').strip() or self.name

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
        """
        if self.status == 'suspended':
            return False, "Your company account is suspended. Contact support."

        latest = self.latest_subscription
        if latest and latest.end_date and timezone.now() > latest.end_date:
            return False, (
                f"Your subscription expired on "
                f"{latest.end_date:%Y-%m-%d}. Please renew to continue."
            )

        if not self.is_active:
            return False, "Your company account has been deactivated. Contact support."

        sub = self.active_subscription
        if not sub:
            return False, "No active subscription found. Please renew to continue."

        if sub.status != 'active':
            return False, (
                f"Your subscription is {sub.get_status_display().lower()}. "
                "Please renew to continue."
            )

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
    # CUSTOM DOMAIN HELPERS
    # ============================================

    @staticmethod
    def normalize_domain(value) -> str | None:
        """
        Turn any user-supplied domain string into a canonical form:

            'HTTPS://WWW.MyShop.co.ke/'        → 'myshop.co.ke'
            'http://MyShop.com:8000/path'      → 'myshop.com'
            'www.othershop.com'                → 'othershop.com'
            'shop.io'                          → 'shop.io'

        Returns None for empty / falsy input.
        """
        if not value:
            return None

        d = str(value).strip().lower()
        for prefix in ('https://', 'http://'):
            if d.startswith(prefix):
                d = d[len(prefix):]
        d = d.split('/')[0]     # strip anything after the first slash
        d = d.split(':')[0]     # strip port
        if d.startswith('www.'):
            d = d[4:]
        return d or None

    def clean_custom_domain(self):
        """
        [Deprecated] Instance method kept for backwards compatibility.
        Use `Company.normalize_domain(value)` (static) instead.
        """
        return self.normalize_domain(self.custom_domain)

    @property
    def normalized_domain(self):
        """Read-only view of `custom_domain` in its canonical form."""
        return self.normalize_domain(self.custom_domain)

    @classmethod
    def find_by_domain(cls, host, require_verified: bool = True) -> "Company | None":
        """
        Look up an active company by custom domain.

        - Canonicalizes `host` first (strips www., protocols, ports).
        - Only returns companies with `is_active=True`.
        - When `require_verified=True` (the default), also requires
          `domain_verified=True` — so DNS-pending domains don't serve traffic.
          Set to False for super-admin preview / DNS-check flows.
        """
        canonical = cls.normalize_domain(host)
        if not canonical:
            return None

        qs = cls.objects.filter(custom_domain__iexact=canonical, is_active=True)
        if require_verified:
            qs = qs.filter(domain_verified=True)

        return qs.select_related('business_type', 'plan').first()

    def get_full_url(self, request=None):
        """
        Return the best URL for this company.
        Prefers verified custom domain; falls back to platform URL.
        """
        if self.custom_domain and self.domain_verified:
            return f"https://{self.custom_domain}"
        if request:
            return request.build_absolute_uri('/')
        return "https://ronosystems.onrender.com"

    def can_use_custom_domain(self):
        """Check if the company's plan allows custom domains."""
        return self.has_feature('has_custom_domain')

    def is_domain_ready(self) -> bool:
        """
        True when the company has a custom_domain set AND it's verified.
        Used by the settings UI to decide whether to display the domain
        as "live" or "pending DNS".
        """
        return bool(self.custom_domain and self.domain_verified)


# ============================================
# COMPANY JOIN REQUEST
# ============================================

class CompanyJoinRequest(models.Model):
    """
    Pending registration request for a specific company.

    Created when a user submits the register form WITH a valid Company ID.
    The applicant does NOT get a User account until a company admin approves
    the request. The password is stored pre-hashed so we can build the User
    account in a single step on approval.

    Approval can assign a role and branch different from the applicant's
    original request — these are stored in `assigned_role`, `assigned_branch`,
    and `assigned_user` so the admin UI can show what was *actually* given.
    """

    STATUS_CHOICES = (
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='join_requests',
    )

    # ---------- Applicant data ----------
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    username = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)

    password_hash = models.CharField(max_length=255)

    requested_role = models.CharField(max_length=20, default='company_staff')

    # ---------- Assignment (filled in on approval) ----------
    assigned_role = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text="Role that was actually assigned when this request was approved.",
    )
    assigned_user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='join_request_assigned',
        help_text="The User account created when this request was approved.",
    )
    assigned_branch = models.ForeignKey(
        'company.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='join_request_assigned',
        help_text="Branch chosen at approval time (if any).",
    )

    # ---------- Review state ----------
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    reviewed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_join_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # ---------- Metadata ----------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rono_company_join_requests'
        ordering = ['-created_at']
        unique_together = [('company', 'email')]
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.email} → {self.company.name} [{self.status}]"

    # ============================================
    # PROPERTIES
    # ============================================

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_approved(self):
        return self.status == 'approved'

    @property
    def is_rejected(self):
        return self.status == 'rejected'

    @property
    def effective_role(self):
        """Role to display: assigned role if approved, else requested."""
        return self.assigned_role or self.requested_role

    # ============================================
    # STATE TRANSITIONS
    # ============================================

    def mark_approved(self, reviewed_by, assigned_user=None,
                      assigned_role=None, assigned_branch=None):
        """
        Flip to approved, stamp the reviewer, and record what was assigned.
        """
        now = timezone.now()
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = now

        self.assigned_role = assigned_role or self.requested_role or 'company_staff'
        self.assigned_user = assigned_user
        self.assigned_branch = assigned_branch

        self.updated_at = now
        self.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at',
            'assigned_role', 'assigned_user', 'assigned_branch',
            'updated_at',
        ])

    def mark_rejected(self, reviewed_by, reason=''):
        """
        Flip to rejected and record the reviewer + reason.
        """
        now = timezone.now()
        self.status = 'rejected'
        self.reviewed_by = reviewed_by
        self.reviewed_at = now
        self.rejection_reason = reason or ''

        self.assigned_role = ''
        self.assigned_user = None
        self.assigned_branch = None

        self.updated_at = now
        self.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at',
            'rejection_reason',
            'assigned_role', 'assigned_user', 'assigned_branch',
            'updated_at',
        ])

    def mark_pending(self):
        """
        Reset a reviewed request back to 'pending'.
        """
        now = timezone.now()
        self.status = 'pending'
        self.reviewed_by = None
        self.reviewed_at = None
        self.rejection_reason = ''

        self.assigned_role = ''
        self.assigned_user = None
        self.assigned_branch = None

        self.updated_at = now
        self.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at',
            'rejection_reason',
            'assigned_role', 'assigned_user', 'assigned_branch',
            'updated_at',
        ])


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
        self.save(update_fields=['is_active', 'ended_at'])