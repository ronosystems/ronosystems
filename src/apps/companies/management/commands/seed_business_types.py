from django.core.management.base import BaseCommand
from apps.companies.business_type_manager import BusinessTypeManager

class Command(BaseCommand):
    help = 'Seed all default business types into the database'
    
    def handle(self, *args, **options):
        self.stdout.write('Seeding business types...')
        
        try:
            created = BusinessTypeManager.initialize_default_business_types()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created {len(created)} business types')
            )
            for bt in created:
                self.stdout.write(f'  - {bt.name}')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error seeding business types: {e}')
            )
