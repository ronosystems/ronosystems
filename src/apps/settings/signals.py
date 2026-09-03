from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .apps import create_default_settings

@receiver(post_migrate)
def create_settings_on_migrate(sender, **kwargs):
    """Create default settings after migrations"""
    if sender.name == 'apps.settings':
        create_default_settings()