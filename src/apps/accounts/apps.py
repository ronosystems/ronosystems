from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'RonoSystems Accounts'

    def ready(self):
        """
        Register all ModelAdmin classes to our restricted admin site
        after Django has finished loading all apps.
        """
        # Import inside ready() to avoid AppRegistryNotReady errors
        from django.contrib import admin
        from apps.accounts.admin_site import restricted_admin_site

        try:
            for model, model_admin in admin.site._registry.items():
                try:
                    restricted_admin_site.register(model, model_admin.__class__)
                except admin.sites.AlreadyRegistered:
                    pass
        except Exception:
            # Fail silently — admin registration is not critical to app boot
            pass