from django.core.management.base import BaseCommand
from apps.settings.views import _ensure_schema_rows, SETTINGS_SCHEMA
from apps.settings.models import SystemSetting


class Command(BaseCommand):
    help = 'Create any missing SystemSetting rows based on SETTINGS_SCHEMA.'

    def handle(self, *args, **options):
        _ensure_schema_rows()
        count = SystemSetting.objects.count()
        self.stdout.write(self.style.SUCCESS(f'Schema ensured. {count} setting(s) now in DB.'))