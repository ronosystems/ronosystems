# apps/companies/models.py
import re

from django.db import models
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify

from apps.companies.business_types import (
    BusinessTypeEnum,
    BUSINESS_TYPE_CHOICES,
    BUSINESS_TYPE_SLUGS,
    BUSINESS_TYPE_APPS,
)

# ============================================
# COMPANY ID GENERATOR
# ============================================

def generate_company_id(name, exclude_pk=None):
    """
    Generate a company ID in the format: {LETTER}@RS{NNN}
    Examples: "Kalyet Company" -> K@RS001
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

def generate_unique_subdomain(name, exclude_pk=None):
    """Generate unique subdomain: Kalyet Shop -> kalyet-shop"""
    base = slugify(name) or 'company'
    candidate = base
    i = 1
    qs = Company.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(subdomain=candidate).exists():
        i += 1
        candidate = f"{base}-{i}"
    return candidate

# ============================================
# BUSINESS TYPE
# ============================================

class BusinessType(models.Model):
    name = models.CharField(max_length=100, unique=True, choices=BUSINESS_TYPE_CHOICES)
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
            raise ValidationError(f"Invalid business type. Must be one of: {valid_names}")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def integration(self):
        return BusinessTypeEnum.get_integration(self.name)

    @property
    def slug(self):
        from apps.companies.business_types import BUSINESS_TYPE_SLUGS
        return BUSINESS_TYPE_SLUGS.get(self.name)

    @property
    def app_module(self):
        from apps.companies.business_types import BUSINESS_TYPE_APPS
        return BUSINESS_TYPE_APPS.get(self.name)

    class Meta:
        db_table = 'rono_business_types'
        ordering = ['name']

class CompanyApplication(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    company_name = models.CharField(max_length=200)
    company_pin = models.CharField(max_length=20, help_text="Registration Number / KRA PIN")
    company_email = models.EmailField()
    company_phone = models.CharField(max_length=20)
    company_website = models.URLField(blank=True)

    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True)

    admin_first_name = models.CharField(max_length=150)
    admin_last_name = models.CharField(max_length=150)
    admin_email = models.EmailField(unique=True)
    admin_phone = models.CharField(max_length=20)
    admin_id_number = models.CharField(max_length=50, blank=True)

    password_hash = models.CharField(max_length=255)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rono_company_applications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} - {self.admin_email} ({self.status})"

# ============================================
# COMPANY - MAIN TENANT
# ============================================

class Company(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )

    # ---------- Identity ----------
    company_id = models.CharField(
        max_length=20, unique=True, db_index=True, editable=False, blank=True,
        help_text="Auto-generated unique company ID (e.g. F@RS001). Employees use this to register.",
    )
    name = models.CharField(max_length=200)
    business_type = models.ForeignKey(BusinessType, on_delete=models.SET_NULL, null=True, related_name='companies')
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
    company_pin = models.CharField(max_length=20, blank=True, default='', help_text="KRA PIN")

    # ---------- Branding ----------
    logo = models.CharField(max_length=255, blank=True, default='')
    favicon = models.CharField(max_length=255, blank=True, default='')
    login_background = models.CharField(max_length=255, blank=True, default='')
    receipt_logo = models.CharField(max_length=255, blank=True, default='')

    # ---------- Hero Settings ----------
    hero_video = models.CharField(max_length=255, blank=True, default='')
    hero_image = models.CharField(max_length=255, blank=True, default='')
    hero_title = models.CharField(max_length=150, blank=True, default='')
    hero_subtitle = models.TextField(blank=True, default='')
    tagline = models.CharField(max_length=200, blank=True, default='')
    about_tagline = models.CharField(max_length=200, blank=True, default='')
    about_mission = models.TextField(blank=True, default='')
    about_vision = models.TextField(blank=True, default='')
    about_story = models.TextField(blank=True, default='')
    years_in_business = models.PositiveIntegerField(null=True, blank=True)
    founded_year = models.PositiveIntegerField(null=True, blank=True)

    primary_color = models.CharField(max_length=7, default='#87CEEB')
    accent_color = models.CharField(max_length=7, default='#036a77')
    system_name = models.CharField(max_length=100, blank=True)

    facebook_url = models.URLField(blank=True, null=True)
    twitter_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    telegram_url = models.URLField(blank=True, null=True)
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True)

    # ---------- Domain - TENANT RESOLUTION ----------
    # 1. subdomain: kalyet -> kalyet.ronosystems.com (always exists)
    # 2. custom_domain: kalyet.co.ke (optional, needs verification)
    subdomain = models.SlugField(
        max_length=100, unique=True, blank=True, null=True, db_index=True,
        help_text="e.g. kalyet -> kalyet.ronosystems.com",
    )
    custom_domain = models.CharField(
        max_length=255, blank=True, null=True, unique=True, db_index=True,
        help_text="e.g., clientcompany.co.ke (no https://, no www., no trailing slash)",
    )
    domain_verified = models.BooleanField(default=False, help_text="Set to True after DNS is confirmed working")

    # ---------- Settings ----------
    company_settings = models.JSONField(default=dict, blank=True)

    # ---------- Subscription (denormalized cache) ----------
    plan = models.ForeignKey('plans.Plan', on_delete=models.SET_NULL, null=True, blank=True, related_name='companies')
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)

    # ---------- Status ----------
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)

    # ---------- Metadata ----------
    created_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_companies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.custom_domain = self.normalize_domain(self.custom_domain)

        # Auto subdomain
        if not self.subdomain:
            self.subdomain = generate_unique_subdomain(self.name, exclude_pk=self.pk)

        # Auto company_id
        if not self.company_id:
            for _ in range(10):
                candidate = generate_company_id(self.name, exclude_pk=self.pk)
                if not Company.objects.filter(company_id=candidate).exists():
                    self.company_id = candidate
                    break
            else:
                raise RuntimeError("Could not generate a unique company_id after 10 attempts.")

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.custom_domain = self.normalize_domain(self.custom_domain)

    def __str__(self):
        plan_name = self.plan.display_name if self.plan else 'No Plan'
        return f"{self.name} [{self.company_id}] ({plan_name})"

    class Meta:
        db_table = 'rono_companies'
        ordering = ['name']
        verbose_name_plural = 'Companies'

    # ---------- MEDIA URL HELPERS ----------
    @staticmethod
    def _build_media_url(key, resource_type='image'):
        if not key:
            return None
        key = str(key).strip().lstrip('/')
        if not key:
            return None
        if key.startswith('media/'):
            key = key[len('media/'):]
        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')
        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/{key}"
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"

    @property
    def logo_url(self):
        return self._build_media_url(self.logo)

    @property
    def favicon_url(self):
        return self._build_media_url(self.favicon)

    @property
    def login_background_url(self):
        return self._build_media_url(self.login_background)

    @property
    def receipt_logo_url(self):
        return self._build_media_url(self.receipt_logo)

    @property
    def hero_video_url(self):
        return self._build_media_url(self.hero_video, resource_type='video')

    @property
    def hero_image_url(self):
        return self._build_media_url(self.hero_image)

    @property
    def display_name(self):
        return (self.system_name or '').strip() or self.name

    # ---------- SUBSCRIPTION ACCESSORS ----------
    @property
    def active_subscription(self):
        return self.subscriptions.filter(status='active').select_related('plan').order_by('-created_at').first()

    @property
    def latest_subscription(self):
        return self.subscriptions.select_related('plan').order_by('-created_at').first()

    @property
    def current_subscription(self):
        return self.active_subscription or self.latest_subscription

    @property
    def current_plan(self):
        sub = self.active_subscription
        if sub and sub.is_active_subscription():
            return sub.plan
        if self.plan:
            return self.plan
        from apps.plans.models import Plan
        return Plan.objects.filter(name='free', is_active=True).first()

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

    # ---------- ACCESS CONTROL ----------
    def can_access_system(self):
        if self.status == 'suspended':
            return False, "Your company account is suspended. Contact support."
        latest = self.latest_subscription
        if latest and latest.end_date and timezone.now() > latest.end_date:
            return False, f"Your subscription expired on {latest.end_date:%Y-%m-%d}. Please renew to continue."
        if not self.is_active:
            return False, "Your company account has been deactivated. Contact support."
        sub = self.active_subscription
        if not sub:
            return False, "No active subscription found. Please renew to continue."
        if sub.status != 'active':
            return False, f"Your subscription is {sub.get_status_display().lower()}. Please renew to continue."
        return True, "OK"

    def mark_subscription_expired(self):
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

    # ---------- FEATURE FLAGS ----------
    @property
    def plan_features(self):
        plan = self.current_plan
        if not plan:
            return {
                'has_api_access': False, 'has_advanced_reports': False,
                'has_custom_branding': False, 'has_priority_support': False,
                'has_bulk_import': False, 'has_custom_domain': False,
                'has_mpesa_integration': False,
            }
        return {
            'has_api_access': plan.has_api_access,
            'has_advanced_reports': plan.has_advanced_reports,
            'has_custom_branding': plan.has_custom_branding,
            'has_priority_support': plan.has_priority_support,
            'has_bulk_import': plan.has_bulk_import,
            'has_custom_domain': plan.has_custom_domain,
            'has_mpesa_integration': plan.has_mpesa_integration,
        }

    def has_feature(self, feature_name):
        return self.plan_features.get(feature_name, False)

    # ---------- LIMITS ----------
    @property
    def limits(self):
        plan = self.current_plan
        if not plan:
            return {'employees': 5, 'companies': 1, 'branches': 1, 'storage': 100}
        return {
            'employees': plan.max_employees,
            'companies': plan.max_companies,
            'branches': plan.max_branches,
            'storage': plan.max_storage,
        }

    def can_add_employee(self):
        return self.users.count() < self.limits['employees']

    def can_add_branch(self):
        branch_count = getattr(self, 'company_branches', None)
        if branch_count is None:
            return True
        return branch_count.count() < self.limits['branches']

    # ---------- BUSINESS TYPE HELPERS ----------
    @property
    def business_type_slug(self):
        return self.business_type.slug if self.business_type else None

    @property
    def business_type_app(self):
        return self.business_type.app_module if self.business_type else None

    # ---------- DOMAIN HELPERS ----------
    @staticmethod
    def normalize_domain(value):
        if not value:
            return None
        d = str(value).strip().lower()
        for prefix in ('https://', 'http://'):
            if d.startswith(prefix):
                d = d[len(prefix):]
        d = d.split('/')[0]
        d = d.split(':')[0]
        if d.startswith('www.'):
            d = d[4:]
        return d or None

    @property
    def normalized_domain(self):
        return self.normalize_domain(self.custom_domain)

    @property
    def domain(self):
        """Domain user uses to login. Prefers verified custom domain."""
        if self.custom_domain and self.domain_verified:
            return self.custom_domain
        if self.subdomain:
            return f"{self.subdomain}.ronosystems.com"
        return "ronosystems.onrender.com"

    @property
    def platform_url(self):
        """Always available subdomain URL, even if custom domain exists."""
        if self.subdomain:
            return f"https://{self.subdomain}.ronosystems.com"
        return "https://ronosystems.onrender.com"

    @classmethod
    def find_by_domain(cls, host, require_verified: bool = True):
        """
        MAIN TENANT RESOLVER - Used by TenantMiddleware.
        1. Try custom_domain: kalyet.co.ke
        2. Try subdomain: kalyet.ronosystems.com
        3. Return None for main domain: ronosystems.com
        """
        canonical = cls.normalize_domain(host)
        if not canonical:
            return None

        # Main platform domains have no tenant
        if canonical in ('ronosystems.com', 'ronosystems.onrender.com', 'localhost', '127.0.0.1'):
            return None

        # 1. Custom domain
        qs = cls.objects.filter(custom_domain__iexact=canonical, is_active=True)
        if require_verified:
            qs = qs.filter(domain_verified=True)
        tenant = qs.select_related('business_type', 'plan').first()
        if tenant:
            return tenant

        # 2. Subdomain
        # ronosystems.com (production) + localhost (local dev)
        subdomain = None
        if canonical.endswith('.ronosystems.com'):
            subdomain = canonical.replace('.ronosystems.com', '')
        elif canonical.endswith('.localhost'):
            subdomain = canonical.replace('.localhost', '')
        if subdomain and subdomain not in ('www', ''):
            return cls.objects.filter(
                subdomain__iexact=subdomain, is_active=True
            ).select_related('business_type', 'plan').first()

        # 3. Also support *.onrender.com for staging: kalyet.ronosystems.onrender.com
        if canonical.endswith('.ronosystems.onrender.com'):
            subdomain = canonical.replace('.ronosystems.onrender.com', '')
            if subdomain and subdomain != 'www':
                return cls.objects.filter(
                    subdomain__iexact=subdomain, is_active=True
                ).select_related('business_type', 'plan').first()

        return None

    def get_full_url(self, request=None):
        if self.custom_domain and self.domain_verified:
            return f"https://{self.custom_domain}"
        if self.subdomain:
            return f"https://{self.subdomain}.ronosystems.com"
        if request:
            return request.build_absolute_uri('/')
        return "https://ronosystems.onrender.com"

    def can_use_custom_domain(self):
        return self.has_feature('has_custom_domain')

    def is_domain_ready(self):
        return bool(self.custom_domain and self.domain_verified)

# ============================================
# COMPANY JOIN REQUEST
# ============================================

class CompanyJoinRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='join_requests')
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    username = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    password_hash = models.CharField(max_length=255)
    requested_role = models.CharField(max_length=20, default='company_staff')

    assigned_role = models.CharField(max_length=20, blank=True, default='')
    assigned_user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='join_request_assigned')
    assigned_branch = models.ForeignKey('companies.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='join_request_assigned')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_join_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
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
        return self.assigned_role or self.requested_role

    def mark_approved(self, reviewed_by, assigned_user=None, assigned_role=None, assigned_branch=None):
        now = timezone.now()
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = now
        self.assigned_role = assigned_role or self.requested_role or 'company_staff'
        self.assigned_user = assigned_user
        self.assigned_branch = assigned_branch
        self.updated_at = now
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'assigned_role', 'assigned_user', 'assigned_branch', 'updated_at'])

    def mark_rejected(self, reviewed_by, reason=''):
        now = timezone.now()
        self.status = 'rejected'
        self.reviewed_by = reviewed_by
        self.reviewed_at = now
        self.rejection_reason = reason or ''
        self.assigned_role = ''
        self.assigned_user = None
        self.assigned_branch = None
        self.updated_at = now
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'assigned_role', 'assigned_user', 'assigned_branch', 'updated_at'])

    def mark_pending(self):
        now = timezone.now()
        self.status = 'pending'
        self.reviewed_by = None
        self.reviewed_at = None
        self.rejection_reason = ''
        self.assigned_role = ''
        self.assigned_user = None
        self.assigned_branch = None
        self.updated_at = now
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'assigned_role', 'assigned_user', 'assigned_branch', 'updated_at'])

# ============================================
# SUPPORT SESSION
# ============================================

class SupportSession(models.Model):
    super_admin = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='support_sessions')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='support_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    reason = models.TextField(blank=True)
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

# ============================================
# TENANT FEEDBACK
# ============================================

class TenantFeedback(models.Model):
    TYPE_BUG = 'bug'
    TYPE_FEATURE = 'feature'
    TYPE_IMPROVE = 'improvement'
    TYPE_OTHER = 'other'

    FEEDBACK_TYPES = (
        (TYPE_BUG, 'Bug / Error'),
        (TYPE_FEATURE, 'Feature Request'),
        (TYPE_IMPROVE, 'Improvement'),
        (TYPE_OTHER, 'Other'),
    )

    SEVERITY_LOW = 'low'
    SEVERITY_NORMAL = 'normal'
    SEVERITY_HIGH = 'high'
    SEVERITY_CRIT = 'critical'

    SEVERITY_CHOICES = (
        (SEVERITY_LOW, 'Low — minor annoyance'),
        (SEVERITY_NORMAL, 'Normal — should fix soon'),
        (SEVERITY_HIGH, 'High — blocking my work'),
        (SEVERITY_CRIT, 'Critical — losing data / money'),
    )

    STATUS_NEW = 'new'
    STATUS_REVIEWING = 'reviewing'
    STATUS_PLANNED = 'planned'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_DONE = 'done'
    STATUS_WONT_FIX = 'wont_fix'

    STATUS_CHOICES = (
        (STATUS_NEW, 'New'),
        (STATUS_REVIEWING, 'Reviewing'),
        (STATUS_PLANNED, 'Planned'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_DONE, 'Done'),
        (STATUS_WONT_FIX, "Won't Fix"),
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='feedback_items')
    submitted_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='feedback_submitted')
    branch = models.ForeignKey('companies.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='feedback_items')

    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPES, default=TYPE_OTHER, db_index=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_NORMAL)
    title = models.CharField(max_length=200)
    message = models.TextField()

    page_url = models.CharField(max_length=500, blank=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    screenshot = models.FileField(upload_to='tenant_feedback/%Y/%m/', blank=True, null=True, max_length=500)
    screenshot_format = models.CharField(max_length=10, blank=True, default='')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True)
    admin_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='feedback_resolved')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rono_tenant_feedback'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['feedback_type', 'status']),
        ]

    def __str__(self):
        return f"[{self.get_feedback_type_display()}] {self.title} — {self.company.name}"

    @property
    def is_open(self):
        return self.status not in (self.STATUS_DONE, self.STATUS_WONT_FIX)

    @property
    def is_critical(self):
        return self.severity == self.SEVERITY_CRIT and self.is_open

    @property
    def screenshot_url(self):
        if not self.screenshot:
            return None
        key = getattr(self.screenshot, 'name', None) or str(self.screenshot)
        key = key.strip().lstrip('/')
        if not key:
            return None
        if key.startswith(('http://', 'https://')):
            return key
        if key.startswith('media/'):
            key = key[len('media/'):]
        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')
        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{key}"
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"

    def set_status(self, new_status, by_user=None, note=None):
        self.status = new_status
        if note:
            self.admin_notes = (self.admin_notes + '\n\n' + note).strip()
        if new_status in (self.STATUS_DONE, self.STATUS_WONT_FIX):
            self.resolved_at = timezone.now()
            self.resolved_by = by_user
        else:
            self.resolved_at = None
            self.resolved_by = None
        self.save()

class ContactMessage(models.Model):
    REPLY_CHOICES = [('email', 'Email'), ('sms', 'SMS'), ('whatsapp', 'WhatsApp')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='contact_messages', null=True, blank=True)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, null=True)
    whatsapp_number = models.CharField(max_length=50, blank=True, null=True)
    subject = models.CharField(max_length=200, blank=True, null=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    admin_reply = models.TextField(blank=True, null=True)
    replied_at = models.DateTimeField(blank=True, null=True)
    reply_method = models.CharField(max_length=10, choices=REPLY_CHOICES, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"

    def __str__(self):
        return f"{self.name} - {self.subject or 'No Subject'} ({self.created_at.strftime('%Y-%m-%d')})"

    def _format_number(self, number):
        phone = number.strip().replace(" ", "").replace("-", "")
        if phone.startswith('07') or phone.startswith('01'):
            return f"+254{phone[1:]}"
        elif phone.startswith('7') or phone.startswith('1'):
            return f"+254{phone}"
        elif phone.startswith('+'):
            return phone
        return phone

    def get_formatted_phone(self):
        if not self.phone:
            return None
        return self._format_number(self.phone)

    def get_formatted_whatsapp(self):
        number = self.whatsapp_number or self.phone
        if not number:
            return None
        return self._format_number(number)

# ============================================
# GALLERY
# ============================================

class Gallery(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gallery_images')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    image = models.CharField(max_length=255, help_text="Cloudinary public_id")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rono_company_gallery'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.company.name}"

    @property
    def image_url(self):
        return Company._build_media_url(self.image)

# ============================================
# BRANCH / STORE LOCATION
# ============================================

class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_branches')
    is_mother_branch = models.BooleanField(default=False, help_text="Marks this branch as the HQ/feeder.")
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    manager = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_branches')
    currency = models.CharField(max_length=10, default='KES')
    currency_symbol = models.CharField(max_length=10, default='KSh')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'epa_branches'
        ordering = ['name']
        unique_together = ['company', 'code']
        constraints = [
            models.UniqueConstraint(fields=['company'], condition=models.Q(is_mother_branch=True), name='one_mother_branch_per_company'),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

# ============================================
# COMPANY EXPENSES
# ============================================

class Expense(models.Model):
    TYPE_SALARY = 'salary'
    TYPE_RENT = 'rent'
    TYPE_BILL = 'bill'
    TYPE_GENERAL = 'general'

    EXPENSE_TYPES = (
        (TYPE_SALARY, 'Salary'),
        (TYPE_RENT, 'Rent'),
        (TYPE_BILL, 'Bill'),
        (TYPE_GENERAL, 'General Expense'),
    )

    GENERAL_CATEGORIES = (
        ('transport', 'Transport'),
        ('utilities', 'Utilities'),
        ('supplies', 'Office Supplies'),
        ('maintenance', 'Maintenance'),
        ('marketing', 'Marketing'),
        ('tax', 'Tax'),
        ('insurance', 'Insurance'),
        ('other', 'Other'),
    )

    BILL_TYPES = (
        ('electricity', 'Electricity'),
        ('water', 'Water'),
        ('internet', 'Internet'),
        ('phone', 'Phone'),
        ('security', 'Security'),
        ('waste', 'Waste Collection'),
        ('other', 'Other Bill'),
    )

    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('m-pesa', 'M-Pesa'),
        ('card', 'Card'),
        ('other', 'Other'),
    )

    EXPENSE_STATUS = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='expenses')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES, default=TYPE_GENERAL, db_index=True)
    expense_date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    employee_name = models.CharField(max_length=150, blank=True)
    employee_id = models.CharField(max_length=50, blank=True)
    employee_phone = models.CharField(max_length=20, blank=True)
    salary_month = models.DateField(null=True, blank=True)

    rent_month = models.DateField(null=True, blank=True)
    landlord_name = models.CharField(max_length=150, blank=True)
    landlord_phone = models.CharField(max_length=20, blank=True)

    bill_type = models.CharField(max_length=20, choices=BILL_TYPES, blank=True)
    bill_name = models.CharField(max_length=150, blank=True)
    bill_period = models.DateField(null=True, blank=True)

    category = models.CharField(max_length=20, choices=GENERAL_CATEGORIES, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    reference = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True)

    attachment = models.FileField(upload_to='expense_attachments/%Y/%m/', blank=True, null=True, max_length=500)
    attachment_format = models.CharField(max_length=10, blank=True, default='')
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=EXPENSE_STATUS, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='expenses_created')
    approved_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses_updated')
    paid_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses_paid')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_expenses'
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'expense_type', 'expense_date']),
            models.Index(fields=['company', 'expense_type', 'status']),
            models.Index(fields=['company', 'salary_month']),
            models.Index(fields=['company', 'rent_month']),
            models.Index(fields=['company', 'bill_period']),
        ]

    def __str__(self):
        return f"[{self.get_expense_type_display()}] {self.description} (KSh {self.amount})"

    @property
    def is_pdf(self):
        if not self.attachment:
            return False
        fmt = (self.attachment_format or '').strip().lower()
        if fmt:
            return fmt == 'pdf'
        return self.attachment.name.lower().endswith('.pdf')

    @property
    def attachment_url(self):
        if not self.attachment:
            return None
        key = getattr(self.attachment, 'name', None) or str(self.attachment)
        key = key.strip().lstrip('/')
        if not key:
            return None
        if key.startswith('http://') or key.startswith('https://'):
            return key
        if key.startswith('media/'):
            key = key[len('media/'):]
        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')
        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{key}"
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"

    def approve(self, user):
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def reject(self):
        self.status = 'rejected'
        self.save()

    def mark_paid(self, user=None):
        self.status = 'paid'
        self.paid_at = timezone.now()
        if user:
            self.paid_by = user
            if not self.approved_by:
                self.approved_by = user
                self.approved_at = timezone.now()
        self.save()