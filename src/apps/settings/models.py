from django.db import models
from django.core.files.storage import default_storage
from django.conf import settings as django_settings
from urllib.parse import urlparse


# ----------------------------------------------------------------------
# URL / key normalization helper
# ----------------------------------------------------------------------
def _clean_storage_key(raw):
    """
    Given an arbitrary string that might be:
      - a full Cloudinary URL       (https://res.cloudinary.com/<cloud>/image/upload/v123/settings/rs_logo.png)
      - a /media/ prefixed path     (/media/settings/rs_logo.png)
      - a raw storage key           (settings/rs_logo.png)
      - a malformed URL             (https:/res.cloudinary.com/<cloud>/settings/rs_logo.png)
      - a cloud-name-prefixed key   (dg9it0ut8/settings/rs_logo.png)

    Return just the storage key (e.g. 'settings/rs_logo.png').

    This is the single point that guarantees `SystemSetting.value` for
    image/file types is always a clean key — never a URL, never a
    /media/ prefix, never prefixed with the Cloudinary cloud name.
    """
    if not raw:
        return ''

    v = str(raw).strip()

    # ---- Repair malformed URLs (single slash after scheme) ----
    if v.startswith('https:/') and not v.startswith('https://'):
        v = 'https://' + v[len('https:/'):]
    elif v.startswith('http:/') and not v.startswith('http://'):
        v = 'http://' + v[len('http:/'):]
    elif v.startswith('//'):
        v = 'https:' + v

    # ---- Full URL: extract the storage key from the path ----
    if v.startswith(('http://', 'https://')):
        marker = '/image/upload/'
        if marker in v:
            tail = v.split(marker, 1)[1]
            # Drop a version segment like "v1234567890/"
            parts = tail.split('/', 1)
            if len(parts) == 2 and parts[0].startswith('v') and parts[0][1:].isdigit():
                return parts[1]
            return tail

        # Generic URL — take everything after the domain
        path = urlparse(v).path.lstrip('/')
        return path

    # ---- Strip /media/ or media/ prefix ----
    if v.startswith('/media/'):
        v = v[len('/media/'):]
    elif v.startswith('media/'):
        v = v[len('media/'):]

    # ---- Strip Cloudinary cloud name if the storage backend prefixed it ----
    cloud_name = getattr(django_settings, 'CLOUDINARY_STORAGE', {}).get('CLOUD_NAME', '')
    if cloud_name and v.startswith(f'{cloud_name}/'):
        v = v[len(cloud_name) + 1:]

    return v.lstrip('/')


class SystemSetting(models.Model):
    """
    A single key/value pair.

    Storage contract:
      - `value` always holds the RAW stored value.
      - For image/file types: `value` is the storage KEY (e.g. "settings/rs_logo")
        — never a full URL, never a /media/ prefix, never cloud-name-prefixed.
      - Use `.get_value()` to read it back as a Python value.
      - Use `.get_url()` to get a browser-ready Cloudinary URL for image/file types.

    The contract is enforced by `_clean_storage_key()` in `save()`, so even
    if a caller assigns a URL, the value is normalized before it hits the DB.
    """

    SETTING_TYPES = (
        ('text', 'Text'),
        ('textarea', 'Text Area'),
        ('boolean', 'Boolean'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('email', 'Email'),
        ('url', 'URL'),
        ('image', 'Image'),
        ('file', 'File'),
        ('color', 'Color'),
        ('password', 'Password'),
        ('select', 'Select'),
    )

    CATEGORIES = (
        ('general', 'General'),
        ('branding', 'Branding'),
        ('email', 'Email'),
        ('payment', 'Payment'),
        ('preferences', 'Preferences'),
    )

    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField(blank=True, default='')

    setting_type = models.CharField(max_length=20, choices=SETTING_TYPES, default='text')
    category = models.CharField(max_length=50, choices=CATEGORIES, default='general')
    label = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    help_text = models.TextField(blank=True)

    order = models.IntegerField(default=0)
    is_required = models.BooleanField(default=False)
    is_editable = models.BooleanField(default=True)
    options = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_settings'
        ordering = ['category', 'order', 'key']
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return f"{self.key} = {self.value[:40]}"

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_value(self):
        """Return the value as the correct Python type."""
        if self.setting_type == 'boolean':
            return str(self.value).lower() in ('true', '1', 'yes', 'on')

        if self.setting_type == 'integer':
            try:
                return int(self.value or 0)
            except (TypeError, ValueError):
                return 0

        if self.setting_type == 'float':
            try:
                return float(self.value or 0)
            except (TypeError, ValueError):
                return 0.0

        # text / textarea / email / url / color / password / select
        # image / file return the raw storage key
        return self.value or ''

    def get_url(self):
        """
        For image/file settings: return a browser-ready Cloudinary URL, or None.

        We build the Cloudinary delivery URL directly instead of calling
        default_storage.url() — because django-cloudinary-storage 0.3.0
        returns an incomplete URL (missing the /image/upload/ segment),
        which Cloudinary rejects with 404.
        """
        if self.setting_type not in ('image', 'file'):
            return None

        key = _clean_storage_key(self.value)
        if not key:
            return None

        # ---- Direct Cloudinary URL ----
        cloud_name = getattr(django_settings, 'CLOUDINARY_STORAGE', {}).get('CLOUD_NAME', '')
        if cloud_name:
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{key}"

        # ---- Fallback: local filesystem or other storage backend ----
        try:
            return default_storage.url(key)
        except Exception:
            media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
            if not media_url.endswith('/'):
                media_url += '/'
            return f"{media_url}{key}"

    def delete_file(self):
        """Delete the stored file for image/file types (best-effort)."""
        if self.setting_type not in ('image', 'file'):
            return

        key = _clean_storage_key(self.value)
        if not key:
            return

        try:
            if default_storage.exists(key):
                default_storage.delete(key)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Class helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_setting(cls, key, default=None):
        try:
            return cls.objects.get(key=key).get_value()
        except cls.DoesNotExist:
            return default
        except Exception:
            return default

    @classmethod
    def get_image_url(cls, key):
        try:
            return cls.objects.get(key=key).get_url()
        except cls.DoesNotExist:
            return None
        except Exception:
            return None

    @classmethod
    def as_dict(cls):
        """Return all settings as a flat dict of key → typed value."""
        return {s.key: s.get_value() for s in cls.objects.all()}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        # Normalize image/file values to a clean storage key before saving.
        # This is the last line of defense against URLs, /media/ prefixes,
        # or cloud-name-prefixed keys ever reaching the database.
        if self.setting_type in ('image', 'file') and self.value:
            self.value = _clean_storage_key(self.value)
        super().save(*args, **kwargs)