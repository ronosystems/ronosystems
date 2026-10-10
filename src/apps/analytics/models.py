from django.conf import settings
from django.db import models
from django.utils import timezone


class Visit(models.Model):
    DEVICE_TYPES = (
        ('desktop', 'Desktop'),
        ('mobile', 'Mobile'),
        ('tablet', 'Tablet'),
        ('bot', 'Bot'),
        ('other', 'Other'),
    )

    ip_address   = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    country      = models.CharField(max_length=100, blank=True, db_index=True)
    country_code = models.CharField(max_length=3, blank=True)
    city         = models.CharField(max_length=100, blank=True, db_index=True)

    page      = models.CharField(max_length=500, db_index=True)
    full_path = models.CharField(max_length=1000, blank=True)
    method    = models.CharField(max_length=10, blank=True)
    referrer  = models.CharField(max_length=1000, blank=True)

    user_agent      = models.TextField(blank=True)
    device          = models.CharField(max_length=100, blank=True)
    device_type     = models.CharField(max_length=20, choices=DEVICE_TYPES, blank=True)
    browser         = models.CharField(max_length=100, blank=True)
    browser_version = models.CharField(max_length=50, blank=True)
    os              = models.CharField(max_length=100, blank=True)

    session_key = models.CharField(max_length=64, blank=True, db_index=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='visits',
    )
    user_name  = models.CharField(max_length=200, blank=True)
    user_email = models.EmailField(blank=True)

    # ── Timestamps ──
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at    = models.DateTimeField(null=True, blank=True, db_index=True)   # 👈 NEW

    class Meta:
        db_table = 'analytics_visits'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at', 'page']),
            models.Index(fields=['ip_address', 'created_at']),
            models.Index(fields=['created_at', 'country']),
            models.Index(fields=['read_at', 'created_at']),   # 👈 NEW
        ]
        verbose_name = 'Visit'
        verbose_name_plural = 'Visits'

    def __str__(self):
        who = self.user_name or self.ip_address or 'anon'
        return f'{self.created_at:%Y-%m-%d %H:%M} — {who} — {self.page}'

    @property
    def is_read(self):
        return self.read_at is not None


class IPGeoCache(models.Model):
    ip_address   = models.GenericIPAddressField(unique=True)
    country      = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=3, blank=True)
    city         = models.CharField(max_length=100, blank=True)
    resolved_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_ip_geo_cache'
        verbose_name = 'IP Geo Cache'
        verbose_name_plural = 'IP Geo Cache'

    def __str__(self):
        return f'{self.ip_address} → {self.city}, {self.country}'