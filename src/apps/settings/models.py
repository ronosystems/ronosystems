from django.db import models
from django.conf import settings as django_settings

class SystemSetting(models.Model):
    SETTING_TYPES = (
        ('text', 'Text'),
        ('textarea', 'Text Area'),
        ('boolean', 'Boolean'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('email', 'Email'),
        ('url', 'URL'),
        ('image', 'Image'),
        ('color', 'Color'),
        ('password', 'Password'),
        ('select', 'Select'),
        ('file', 'File'),
    )
    
    CATEGORIES = (
        ('general', 'General'),
        ('branding', 'Branding & Design'),
        ('email', 'Email Settings'),
        ('payment', 'Payment Settings'),
        ('currency', 'Currency & Localization'),
        ('language', 'Language & Internationalization'),
        ('security', 'Security'),
        ('preferences', 'Preferences'),
        ('integration', 'Integrations'),
        ('advanced', 'Advanced'),
    )
    
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    setting_type = models.CharField(max_length=20, choices=SETTING_TYPES, default='text')
    category = models.CharField(max_length=50, choices=CATEGORIES, default='general')
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    help_text = models.TextField(blank=True)
    is_editable = models.BooleanField(default=True)
    is_required = models.BooleanField(default=False)
    order = models.IntegerField(default=0)
    options = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'order', 'key']
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'
    
    def __str__(self):
        return f"{self.key}: {self.value[:50]}..."
    
    def get_value(self):
        """Get the value with proper type casting"""
        if self.setting_type == 'boolean':
            return self.value.lower() in ['true', '1', 'yes', 'on']
        elif self.setting_type == 'integer':
            try:
                return int(self.value)
            except:
                return 0
        elif self.setting_type == 'float':
            try:
                return float(self.value)
            except:
                return 0.0
        elif self.setting_type == 'image' and self.value:
            # Handle image URLs properly
            if self.value.startswith('http://') or self.value.startswith('https://'):
                return self.value
            if self.value.startswith('/media/'):
                return self.value
            if self.value.startswith('media/'):
                return f"/{self.value}"
            if not self.value.startswith('/') and not self.value.startswith('media/'):
                return f"{django_settings.MEDIA_URL}{self.value}"
            return self.value
        return self.value
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value by key with default fallback"""
        try:
            setting = cls.objects.get(key=key)
            return setting.get_value()
        except cls.DoesNotExist:
            return default
        except Exception:
            return default
    
    def get_display_value(self):
        """Get display-friendly value"""
        if self.setting_type == 'boolean':
            return 'Enabled' if self.get_value() else 'Disabled'
        elif self.setting_type == 'image' and self.value:
            return f'<img src="{self.get_value()}" style="max-height:50px;">'
        return self.value