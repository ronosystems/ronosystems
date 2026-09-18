from django.db import models
from django.conf import settings as django_settings


class SystemSetting(models.Model):
    """
    One key/value row per setting.

    Storage contract for image/file/video types:
      - `value` holds the storage key (e.g. "settings/site_logo")
      - `get_url()` returns a fully-formed Cloudinary URL with a cache-buster

    The value for media is written by the view via `cloudinary.uploader.upload`
    using a stable public_id derived from the setting key (e.g. "settings/site_logo").
    The view is the only writer. This model never rewrites the stored value.
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
        ('video', 'Video'),           # ← NEW
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
        t = self.setting_type

        if t == 'boolean':
            return str(self.value).lower() in ('true', '1', 'yes', 'on')

        if t == 'integer':
            try:
                return int(self.value or 0)
            except (TypeError, ValueError):
                return 0

        if t == 'float':
            try:
                return float(self.value or 0)
            except (TypeError, ValueError):
                return 0.0

        # text / textarea / email / url / color / password / select /
        # image / file / video  → return raw string
        return self.value or ''

    def get_url(self):
        """
        Return a fully-formed Cloudinary URL for image/file/video settings,
        with a cache-buster (based on updated_at) so browsers/CDN always
        fetch the newest version after an update.

        - Images / files → /image/upload/  (Cloudinary serves both from
          the 'image' pipeline for our purposes)
        - Videos         → /video/upload/

        Returns None if no value is stored.
        """
        if self.setting_type not in ('image', 'file', 'video'):
            return None

        key = (self.value or '').strip().lstrip('/')
        if not key:
            return None

        cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
        cloud_name = cfg.get('CLOUD_NAME', '')

        if cloud_name:
            # Pick the correct Cloudinary delivery path
            if self.setting_type == 'video':
                resource = 'video'
            else:
                resource = 'image'

            url = f"https://res.cloudinary.com/{cloud_name}/{resource}/upload/{key}"
            if self.updated_at:
                url += f"?v={int(self.updated_at.timestamp())}"
            return url

        # Local filesystem fallback (dev with USE_CLOUDINARY_MEDIA=False)
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if not media_url.endswith('/'):
            media_url += '/'
        return f"{media_url}{key}"

    # ------------------------------------------------------------------
    # Class helpers (used by views, templates, context processors)
    # ------------------------------------------------------------------
    @classmethod
    def get_setting(cls, key, default=None):
        """Return the typed value for `key`, or `default` if not set."""
        try:
            return cls.objects.get(key=key).get_value()
        except cls.DoesNotExist:
            return default
        except Exception:
            return default

    @classmethod
    def get_image_url(cls, key):
        """Return the Cloudinary URL for any media setting (image/file/video)."""
        try:
            return cls.objects.get(key=key).get_url()
        except cls.DoesNotExist:
            return None
        except Exception:
            return None

    @classmethod
    def get_video_url(cls, key):
        """
        Explicit helper for video settings — same as get_image_url() but
        named for clarity when the caller knows they want a video.
        """
        try:
            obj = cls.objects.get(key=key)
            if obj.setting_type != 'video':
                return None
            return obj.get_url()
        except cls.DoesNotExist:
            return None
        except Exception:
            return None

    @classmethod
    def as_dict(cls):
        """
        Return all settings as a flat dict of {key: typed_value}.

        Used by apps.settings.context_processors.system_settings to inject
        SITE_NAME, PRIMARY_COLOR, etc. into every template.
        """
        return {s.key: s.get_value() for s in cls.objects.all()}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        # NOTE: we do NOT touch `value` here. The view is responsible for
        # writing correctly-formatted storage keys for image/file/video settings.
        super().save(*args, **kwargs)