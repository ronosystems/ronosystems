from django.apps import AppConfig

class SettingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.settings'

    def ready(self):
        try:
            from .views import create_default_settings
            create_default_settings()
        except Exception as e:
            print(f"⚠️ Could not create default settings: {e}")
