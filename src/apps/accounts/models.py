# apps/users/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('super_admin', 'Super Admin'),
        ('company_admin', 'Company Admin'),
        ('company_manager', 'Company Manager'),
        ('company_cashier', 'Company Cashier'),
        ('company_agent', 'Company Agent'),
        ('mpesa_agent', 'Mpesa Agent'),
        ('company_staff', 'Company Staff'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='company_staff')
    company = models.ForeignKey(
        'companies.Company', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='users'
    )
    branch = models.ForeignKey(
        'epa_shop.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff'
    )
    phone = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    
    # Employee details
    staff_id = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    
    # Profile
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    address = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.email} ({self.role})"
    
    @property
    def is_super_admin(self):
        return self.role == 'super_admin'
    
    @property
    def is_company_admin(self):
        return self.role == 'company_admin'
    
    @property
    def is_company_manager(self):
        return self.role == 'company_manager'
    
    @property
    def is_company_cashier(self):
        return self.role == 'company_cashier'
    
    @property
    def is_company_agent(self):
        return self.role == 'company_agent'
    
    
    @property
    def is_company_staff(self):
        return self.role == 'company_staff'

    @property
    def is_mpesa_agent(self):
        return self.role == 'mpesa_agent'
    
    @property
    def is_admin_or_manager(self):
        return self.role in ['super_admin', 'company_admin', 'company_manager']
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    @property
    def branch_name(self):
        return self.branch.name if self.branch else 'Not Assigned'
    
    class Meta:
        db_table = 'rono_users'
        ordering = ['-created_at']