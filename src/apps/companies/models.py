from django.db import models
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from apps.business_types.business_type_registry import BusinessTypeEnum, BUSINESS_TYPE_CHOICES

class BusinessType(models.Model):
    """
    Business Type model with strict validation
    Only allows creation of business types defined in the registry
    """
    name = models.CharField(
        max_length=100, 
        unique=True,
        choices=BUSINESS_TYPE_CHOICES
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


class Company(models.Model):
    """Company model - the main tenant"""
    
    # Updated PLAN_CHOICES to match all plans in the Plan model
    PLAN_CHOICES = (
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('standard', 'Standard'),
        ('enterprise', 'Enterprise'),
    )
    
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    name = models.CharField(max_length=200)
    business_type = models.ForeignKey(
        BusinessType, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='companies'
    )
    registration_number = models.CharField(max_length=100, unique=True, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    
    # ============================================
    # Settings field - using different name to avoid conflict
    # ============================================
    company_settings = models.JSONField(default=dict, blank=True, help_text="Company settings stored as JSON")
    
    # Subscription
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,  # Use renamed import
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_companies'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.plan})"
    
    @property
    def is_subscription_active(self):
        from django.utils import timezone
        if self.subscription_end:
            return timezone.now() <= self.subscription_end
        return True
    
    def get_plan_details(self):
        """Get the full plan details from Plan model"""
        try:
            from apps.plans.models import Plan
            return Plan.objects.get(name=self.plan)
        except:
            return None
    
    class Meta:
        db_table = 'rono_companies'
        ordering = ['name']
        verbose_name_plural = 'Companies'





# apps/companies/models.py

class SupportSession(models.Model):
    """Track super admin support sessions for audit"""
    super_admin = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_sessions'
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='support_sessions'
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