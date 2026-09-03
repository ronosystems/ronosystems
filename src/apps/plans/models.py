from django.db import models
from django.utils import timezone
from apps.companies.models import Company

class Plan(models.Model):
    """Subscription plans for companies"""
    
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
    has_mpesa_intergration = models.BooleanField(default=False)
    
    # Business type access
    allowed_business_types = models.ManyToManyField(
        'companies.BusinessType', 
        blank=True,
        related_name='allowed_plans'
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
        if self.has_mpesa_intergration:
            features.append("Mpesa Intergration")
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
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='subscriptions')
    
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Payment info
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=200, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.company.name} - {self.plan.display_name}"
    
    def is_active_subscription(self):
        if self.status != 'active':
            return False
        if self.end_date and timezone.now() > self.end_date:
            return False
        return True

class PlanFeature(models.Model):
    """Additional features for plans"""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='features')
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
