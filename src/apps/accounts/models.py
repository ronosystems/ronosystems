# apps/accounts/models.py

import random
import string
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings as django_settings


class User(AbstractUser):
    ROLE_CHOICES = (
        # ─────────────────────────────────────────
        # Platform / System Roles
        # ─────────────────────────────────────────
        ('guest', 'Guest'),
        ('super_admin', 'Super Admin'),
        ('site_manager', 'Site Manager'),

        # ─────────────────────────────────────────
        # Business Roles (EPA Shop, Kuku, etc.)
        # ─────────────────────────────────────────
        ('company_admin', 'Company Admin'),
        ('company_manager', 'Company Manager'),
        ('company_cashier', 'Company Cashier'),
        ('stock_controller', 'Stock Controller'),
        ('company_agent', 'Company Agent'),
        ('mpesa_agent', 'Mpesa Agent'),
        ('company_technician', 'Company Technician'),
        ('customer_care', 'Customer Care'),
        ('company_staff', 'Company Staff'),

        # ─────────────────────────────────────────
        # Chama Specific Roles
        # ─────────────────────────────────────────
        ('chairperson', 'Chairperson'),
        ('vice_chairperson', 'Vice Chairperson'),
        ('secretary', 'Secretary'),
        ('vice_secretary', 'Vice Secretary'),
        ('treasurer', 'Treasurer'),
        ('loan_officer', 'Loan Officer'),
        ('coopted_member', 'Co-opted Member'),
        ('member', 'Member'),
    )

    # EMAIL IS THE TRUE IDENTIFIER FOR THE MILLIONS OF USERS
    email = models.EmailField(unique=True, blank=False)
    
    # Username is still required by Django, but we use it as a global unique ID
    # We do not use this for logging in. We use email.
    username = models.CharField(max_length=150, unique=True, blank=True)

    # PRIMARY company / role - for backward compatibility
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='company_staff')
    company = models.ForeignKey(
        'companies.Company', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users',
    )
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='staff',
    )

    # Contact
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

    # ============================================================
    # SAVE OVERRIDE
    # ============================================================
    def save(self, *args, **kwargs):
        # If no username is provided, use the email prefix or a random string
        if not self.username:
            self.username = self.email.split('@')[0]
            # Ensure uniqueness
            while User.objects.filter(username=self.username).exclude(pk=self.pk).exists():
                self.username += str(random.randint(1, 9999))

        if self.is_superuser and self.role != 'super_admin':
            self.role = 'super_admin'
        if self.company_id and self.role == 'guest':
            self.role = 'company_staff'
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.email} ({self.role})"

    # ============================================================
    # MEMBERSHIP HELPERS
    # ============================================================
    def get_companies(self):
        """Companies zote ambazo user ni member (active)."""
        return [
            m.company
            for m in self.memberships.select_related('company').filter(is_active=True)
        ]

    def get_primary_membership(self):
        """Membership ambayo ni primary."""
        return self.memberships.filter(
            is_primary=True, is_active=True
        ).select_related('company', 'branch').first()

    def get_membership_for_company(self, company):
        """Membership ya user kwenye company fulani."""
        return self.memberships.filter(
            company=company, is_active=True
        ).select_related('company', 'branch').first()

    def has_membership_in(self, company):
        """Ana ruhusa kwenye hii company?"""
        return self.memberships.filter(company=company, is_active=True).exists()

    # ============================================================
    # ROLE HELPERS (Platform)
    # ============================================================
    @property
    def is_guest(self):
        return self.role == 'guest'

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_site_manager(self):
        return self.role == 'site_manager'

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
    def is_stock_controller(self):
        return self.role == 'stock_controller'

    @property
    def is_company_agent(self):
        return self.role == 'company_agent'

    @property
    def is_mpesa_agent(self):
        return self.role == 'mpesa_agent'

    @property
    def is_company_technician(self):
        return self.role == 'company_technician'

    @property
    def is_customer_care(self):
        return self.role == 'customer_care'

    @property
    def is_company_staff(self):
        return self.role == 'company_staff'

    @property
    def is_admin_or_manager(self):
        return self.role in ['super_admin', 'company_admin', 'company_manager']

    # ============================================================
    # ROLE HELPERS (Chama)
    # ============================================================
    @property
    def is_chairperson(self):
        return self.role == 'chairperson'

    @property
    def is_vice_chairperson(self):
        return self.role == 'vice_chairperson'

    @property
    def is_secretary(self):
        return self.role == 'secretary'

    @property
    def is_vice_secretary(self):
        return self.role == 'vice_secretary'

    @property
    def is_treasurer(self):
        return self.role == 'treasurer'

    @property
    def is_loan_officer(self):
        return self.role == 'loan_officer'

    @property
    def is_coopted_member(self):
        return self.role == 'coopted_member'

    @property
    def is_member(self):
        return self.role == 'member'

    @property
    def is_chama_role(self):
        """Any role that belongs to the Chama app."""
        return self.role in {
            'chairperson', 'vice_chairperson',
            'secretary', 'vice_secretary',
            'treasurer', 'loan_officer',
            'coopted_member', 'member',
        }

    # ============================================================
    # ROLE FLAGS DICTIONARY
    # ============================================================
    @property
    def role_flags(self):
        """Serializable dict of role flags for the frontend."""
        return {
            # Platform
            'is_super_admin': self.is_super_admin,
            'is_site_manager': self.is_site_manager,
            'is_company_admin': self.is_company_admin,
            'is_company_manager': self.is_company_manager,
            'is_company_cashier': self.is_company_cashier,
            'is_company_agent': self.is_company_agent,
            'is_company_staff': self.is_company_staff,
            'is_stock_controller': self.is_stock_controller,
            'is_mpesa_agent': self.is_mpesa_agent,
            'is_company_technician': self.is_company_technician,
            'is_customer_care': self.is_customer_care,
            'is_guest': self.is_guest,

            # Chama
            'is_chairperson': self.is_chairperson,
            'is_vice_chairperson': self.is_vice_chairperson,
            'is_secretary': self.is_secretary,
            'is_vice_secretary': self.is_vice_secretary,
            'is_treasurer': self.is_treasurer,
            'is_loan_officer': self.is_loan_officer,
            'is_coopted_member': self.is_coopted_member,
            'is_member': self.is_member,
            'is_chama_role': self.is_chama_role,
        }

    # ============================================================
    # DISPLAY HELPERS
    # ============================================================
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def branch_name(self):
        return self.branch.name if self.branch else 'Not Assigned'

    # ============================================================
    # PROFILE PICTURE URL
    # ============================================================
    @property
    def profile_picture_url(self):
        """
        Fully-formed Cloudinary URL for the profile picture.
        """
        if not self.profile_picture:
            return None

        key = getattr(self.profile_picture, 'name', None) or str(self.profile_picture)
        key = key.strip().lstrip('/')

        if not key:
            return None

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

    class Meta:
        db_table = 'rono_users'
        ordering = ['-created_at']


# ============================================================
# MEMBERSHIP - The Bridge
# Jane can belong to MULTIPLE companies, with a DIFFERENT 
# role and UNIQUE username in each company.
# ============================================================
class Membership(models.Model):
    ROLE_CHOICES = User.ROLE_CHOICES

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='memberships',
    )
    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE, related_name='memberships',
    )
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='memberships',
    )
    
    # This is the specific username for this company profile (e.g., FJ443355)
    company_username = models.CharField(
        max_length=50, unique=True, null=True, blank=True,
        help_text="Auto-generated unique username for this specific company."
    )
    
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='company_staff')
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_invitations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rono_memberships'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'company'], name='unique_user_company_membership'),
        ]

    def __str__(self):
        return f"{self.company_username} @ {self.company} ({self.role})"

    def generate_company_username(self):
        """
        Generates a username like FJ443355.
        Company Prefix (F) + First Initial (J) + Last Initial (S) + 6 random digits.
        """
        first_name = self.user.first_name or 'X'
        last_name = self.user.last_name or 'X'
        
        f_initial = first_name[0].upper()
        l_initial = last_name[0].upper()
        
        # Get Company Prefix (First letter of company name)
        c_prefix = self.company.name[0].upper() if self.company.name else 'C'
        
        while True:
            # Generate 6 random digits
            digits = ''.join(random.choices(string.digits, k=6))
            username = f"{c_prefix}{f_initial}{l_initial}{digits}"
            
            # Ensure it doesn't exist globally in User model OR Membership model
            if not User.objects.filter(username=username).exists() and \
               not Membership.objects.filter(company_username=username).exists():
                return username

    def save(self, *args, **kwargs):
        # 1. Auto-generate the unique username if it doesn't exist yet
        if not self.company_username:
            self.company_username = self.generate_company_username()

        # 2. If this is set as primary, unset all other primary memberships
        if self.is_primary and self.is_active:
            Membership.objects.filter(
                user=self.user, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
            
        super().save(*args, **kwargs)

        # 3. Keep User model in sync when this is the primary membership
        if self.is_primary and self.is_active:
            User.objects.filter(pk=self.user_id).update(
                company_id=self.company_id, 
                role=self.role,
                branch_id=self.branch_id,
                # Do NOT update the global User.username here. 
                # Let the Membership hold the company-specific username.
            )