# apps/accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings as django_settings


class User(AbstractUser):
    ROLE_CHOICES = (
        ('guest', 'Guest'),
        ('super_admin', 'Super Admin'),
        ('company_admin', 'Company Admin'),
        ('company_manager', 'Company Manager'),
        ('company_cashier', 'Company Cashier'),
        ('stock_controller', 'Stock Controller'),
        ('company_agent', 'Company Agent'),
        ('mpesa_agent', 'Mpesa Agent'),
        ('company_staff', 'Company Staff'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='company_staff')
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
    # ROLE HELPERS
    # ============================================================
    @property
    def is_guest(self):
        return self.role == 'guest'

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
    def is_stock_controller(self):
        return self.role == 'stock_controller'

    @property
    def is_company_agent(self):
        return self.role == 'company_agent'

    @property
    def is_mpesa_agent(self):
        return self.role == 'mpesa_agent'

    @property
    def is_company_staff(self):
        return self.role == 'company_staff'

    @property
    def is_admin_or_manager(self):
        return self.role in ['super_admin', 'company_admin', 'company_manager']

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

        The view uploads to Cloudinary via cloudinary.uploader.upload() with
        a UNIQUE public_id per upload (profiles/user_<id>_<timestamp>). This
        guarantees the URL changes every time, so the browser and Cloudinary's
        CDN always serve the freshest image — no stale cache.

        Returns None if no picture is set.
        """
        if not self.profile_picture:
            return None

        key = getattr(self.profile_picture, 'name', None) or str(self.profile_picture)
        key = key.strip().lstrip('/')

        if not key:
            return None

        # Strip any legacy /media/ prefix
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