# apps/accounts/admin_registry.py

from django.contrib import admin
from apps.accounts.admin_site import restricted_admin_site


def register_all_admins():
    """
    Copy all registered models from the default admin.site
    to our restricted_admin_site.
    
    Call this ONCE from any AppConfig.ready() method.
    """
    # Iterate through everything already registered on the default admin.site
    for model, model_admin in admin.site._registry.items():
        # Register the same ModelAdmin class instance on our custom site
        try:
            restricted_admin_site.register(model, model_admin.__class__)
        except admin.sites.AlreadyRegistered:
            pass