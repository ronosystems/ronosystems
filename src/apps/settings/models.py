from django.db import models
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
import os

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
        db_table = 'system_settings'
        ordering = ['category', 'order', 'key']
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'
    
    def __str__(self):
        return f"{self.key}: {self.value[:50]}..."
    
    def get_value(self):
        """
        Get the value with proper type casting and URL handling
        Supports both local storage and Cloudinary
        """
        if self.setting_type == 'boolean':
            return self.value.lower() in ['true', '1', 'yes', 'on']
        
        elif self.setting_type == 'integer':
            try:
                return int(self.value)
            except (ValueError, TypeError):
                return 0
        
        elif self.setting_type == 'float':
            try:
                return float(self.value)
            except (ValueError, TypeError):
                return 0.0
        
        elif self.setting_type in ['image', 'file'] and self.value:
            # Already a full URL (Cloudinary or external)
            if self.value.startswith('http://') or self.value.startswith('https://'):
                return self.value
            
            # Check if it's a Cloudinary URL
            if 'cloudinary' in self.value:
                return self.value
            
            # Check if it has /media/ prefix
            if self.value.startswith('/media/'):
                return self.value
            
            # Check if it starts with media/
            if self.value.startswith('media/'):
                return f"/{self.value}"
            
            # Check if the file exists in storage
            try:
                # For local storage, check if file exists
                if default_storage.exists(self.value):
                    # Return the URL from storage
                    return default_storage.url(self.value)
            except Exception:
                pass
            
            # Default: add MEDIA_URL prefix
            if not self.value.startswith('/') and not self.value.startswith('media/'):
                # Use MEDIA_URL from settings (works with both local and Cloudinary)
                if hasattr(django_settings, 'MEDIA_URL'):
                    media_url = django_settings.MEDIA_URL
                    if media_url:
                        # Ensure no double slashes
                        if media_url.endswith('/') and self.value.startswith('/'):
                            return f"{media_url}{self.value[1:]}"
                        elif media_url.endswith('/') or self.value.startswith('/'):
                            return f"{media_url}{self.value}"
                        else:
                            return f"{media_url}/{self.value}"
            
            return self.value
        
        return self.value
    
    def get_raw_value(self):
        """Get the raw stored value without any processing"""
        return self.value
    
    def get_image_url(self):
        """Get the full URL for image type settings"""
        if self.setting_type in ['image', 'file'] and self.value:
            return self.get_value()
        return None
    
    def get_display_value(self):
        """Get display-friendly value for templates"""
        if self.setting_type == 'boolean':
            return 'Enabled' if self.get_value() else 'Disabled'
        elif self.setting_type in ['image', 'file'] and self.value:
            img_url = self.get_image_url()
            if img_url:
                return f'<img src="{img_url}" style="max-height:50px; max-width:100px; object-fit:contain;">'
            return self.value
        elif self.setting_type == 'color' and self.value:
            return f'<span style="display:inline-block;width:20px;height:20px;background:{self.value};border:1px solid #000;border-radius:4px;"></span> {self.value}'
        return self.value
    
    def get_file_name(self):
        """Get the filename from the path"""
        if self.value:
            return os.path.basename(self.value)
        return None
    
    def file_exists(self):
        """Check if the file actually exists in storage"""
        if not self.value:
            return False
        try:
            # Remove any /media/ prefix for checking
            file_path = self.value
            if file_path.startswith('/media/'):
                file_path = file_path[7:]
            elif file_path.startswith('media/'):
                file_path = file_path[6:]
            return default_storage.exists(file_path)
        except Exception:
            return False
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value by key with default fallback"""
        try:
            setting = cls.objects.get(key=key)
            return setting.get_value()
        except cls.DoesNotExist:
            return default
        except Exception as e:
            print(f"Error getting setting {key}: {e}")
            return default
    
    @classmethod
    def get_raw_setting(cls, key, default=None):
        """Get raw setting value without processing"""
        try:
            setting = cls.objects.get(key=key)
            return setting.value
        except cls.DoesNotExist:
            return default
        except Exception:
            return default
    
    @classmethod
    def set_setting(cls, key, value, setting_type='text', **kwargs):
        """Set a setting value, creating if it doesn't exist"""
        try:
            setting = cls.objects.get(key=key)
            setting.value = value
            if setting_type != 'text':
                setting.setting_type = setting_type
            setting.save()
        except cls.DoesNotExist:
            cls.objects.create(
                key=key,
                value=value,
                setting_type=setting_type,
                **kwargs
            )
        return True
    
    @classmethod
    def get_all_settings(cls):
        """Get all settings as a dictionary"""
        settings_dict = {}
        for setting in cls.objects.all():
            settings_dict[setting.key] = setting.get_value()
        return settings_dict
    
    def save(self, *args, **kwargs):
        """Override save to handle image value formatting"""
        # If this is an image/file type, ensure the value is clean
        if self.setting_type in ['image', 'file'] and self.value:
            # Remove any /media/ prefix for storage
            if self.value.startswith('/media/'):
                self.value = self.value[7:]
            elif self.value.startswith('media/'):
                self.value = self.value[6:]
        super().save(*args, **kwargs)