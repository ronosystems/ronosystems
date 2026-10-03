from django.apps import AppConfig


class LossesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.losses'     # ← matches INSTALLED_APPS entry
    label = 'losses'         # optional but recommended: short label for DB tables
    verbose_name = 'Losses & Returns'