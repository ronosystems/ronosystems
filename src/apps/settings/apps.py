from django.apps import AppConfig

class SettingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.settings'
    label = 'settings'
    verbose_name = 'System Settings'

    def ready(self):
        # Import signals only if the module exists
        try:
            from . import signals
        except ImportError:
            pass
        
        # Create default settings after migrations
        try:
            from django.db import connection
            from .models import SystemSetting
            
            # Check if the table exists by trying to query
            if SystemSetting.objects.exists():
                return
        except:
            pass
        
        # Create default settings
        from .views import create_default_settings
        create_default_settings()