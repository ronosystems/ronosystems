# apps/customers/models.py

import uuid
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.utils import timezone
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Customer(models.Model):
    # Links the customer to a specific Company (Tenant)
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='customers',
        help_text="The company this customer belongs to."
    )

    # Public ID for secure URLs
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # --- Core Personal Info ---
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', "Enter a valid phone number.")]
    )
    email = models.EmailField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True)
    national_id = models.CharField(max_length=50, blank=True)

    # --- Next of Kin ---
    next_of_kin_name = models.CharField(max_length=200, blank=True)
    next_of_kin_phone = models.CharField(max_length=30, blank=True)

    # --- Auth Link (Optional) ---
    # CASCADE: deleting the User (super admin) also deletes this Customer row.
    # The reverse (deleting this Customer deletes the User) is handled by the
    # post_delete signal at the bottom of this file.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='customer_profiles'
    )

    pin = models.CharField(
        max_length=128, blank=True, null=True,
        help_text="Hashed PIN for this specific tenant"
    )

    # --- Profile Photo & KYC Documents (Cloudinary Public IDs) ---
    profile_photo = models.CharField(max_length=255, null=True, blank=True)

    id_front = models.CharField(max_length=255, null=True, blank=True)
    id_back = models.CharField(max_length=255, null=True, blank=True)
    good_conduct = models.CharField(max_length=255, null=True, blank=True)
    kra_pin = models.CharField(max_length=255, null=True, blank=True)
    cv = models.CharField(max_length=255, null=True, blank=True)

    # --- Chama Specific Fields ---
    custom_loan_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Custom borrowing limit set by the committee."
    )

    # --- Reviewer Tracking ---
    reviewer_comment = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_customers'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # --- Status ---
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('company', 'phone_number')]

    def __str__(self):
        return f"{self.full_name} ({self.phone_number}) - {self.company.display_name}"

    # ============================================================
    # CLOUDINARY URL PROPERTIES
    # ============================================================
    def _build_cloudinary_url(self, key, resource_type='image'):
        if not key:
            return None

        cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')

        if cloud_name:
            if resource_type == 'raw':
                return f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/fl_attachment/{key}"
            else:
                return f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload/{key}"
        return None

    @property
    def profile_photo_url(self):
        return self._build_cloudinary_url(self.profile_photo, 'image')

    @property
    def id_front_url(self):
        return self._build_cloudinary_url(self.id_front, 'image')

    @property
    def id_back_url(self):
        return self._build_cloudinary_url(self.id_back, 'image')

    @property
    def good_conduct_url(self):
        return self._build_cloudinary_url(self.good_conduct, 'raw')

    @property
    def kra_pin_url(self):
        return self._build_cloudinary_url(self.kra_pin, 'raw')

    @property
    def cv_url(self):
        return self._build_cloudinary_url(self.cv, 'raw')



# ============================================================
# SIGNAL: Customer deleted → delete its linked User (if orphaned)
# ============================================================
@receiver(post_delete, sender=Customer)
def _delete_orphaned_customer_user(sender, instance, **kwargs):
    from django.contrib.auth import get_user_model

    user_id = instance.user_id
    if not user_id:
        return

    User = get_user_model()

    # If the User is already gone (CASCADE from User.delete()), do nothing.
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return

    # Safety: leave the User alone if another Customer profile still uses it.
    if Customer.objects.filter(user_id=user_id).exists():
        return

    try:
        user.delete()
    except Exception:
        pass


        