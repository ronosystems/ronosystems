from django.apps import AppConfig

class EpaShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.epa_shop'
    verbose_name = 'EPA Shop'

    def ready(self):
        import apps.epa_shop.signals