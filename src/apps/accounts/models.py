# apps/accounts/models.py

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
        ('member', 'Regular Member'),
    )

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='company_staff')
    company = models.ForeignKey(
        'companies.Company', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users',
    )
    branch = models.ForeignKey(
        'company.Branch', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='staff',
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

    # ============================================================
    # SAVE OVERRIDE
    # ============================================================
    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != 'super_admin':
            self.role = 'super_admin'
        if self.company_id and self.role == 'guest':
            self.role = 'company_staff'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.email} ({self.role})"

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