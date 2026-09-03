# apps/epa_shop/migrations/0002_fix_duplicate_product_codes.py

from django.db import migrations

def fix_duplicate_product_codes(apps, schema_editor):
    """Fix duplicate product codes and ensure uniqueness"""
    Phone = apps.get_model('epa_shop', 'Phone')
    Electronic = apps.get_model('epa_shop', 'Electronic')
    Accessory = apps.get_model('epa_shop', 'Accessory')
    Company = apps.get_model('companies', 'Company')
    
    models_to_fix = [
        {'model': Phone, 'prefix': 'P'},
        {'model': Electronic, 'prefix': 'E'},
        {'model': Accessory, 'prefix': 'A'},
    ]
    
    for item in models_to_fix:
        model = item['model']
        default_prefix = item['prefix']
        
        # Get all unique company IDs for this model
        company_ids = model.objects.values_list('company_id', flat=True).distinct()
        
        for company_id in company_ids:
            try:
                company = Company.objects.get(id=company_id)
                prefix = company.name[0].upper() if company.name else default_prefix
            except Company.DoesNotExist:
                prefix = default_prefix
            
            # Get all products for this company, ordered by creation date
            products = model.objects.filter(company_id=company_id).order_by('id')
            
            used_codes = set()
            counter = 1
            
            for product in products:
                # Generate a unique code
                new_code = f"{prefix}{str(counter).zfill(6)}"
                
                # Make sure it's unique
                while new_code in used_codes:
                    counter += 1
                    new_code = f"{prefix}{str(counter).zfill(6)}"
                
                # Update the product
                product.product_code = new_code
                product.save(update_fields=['product_code'])
                used_codes.add(new_code)
                counter += 1
                
                print(f"Updated {model.__name__} {product.id}: {new_code}")

class Migration(migrations.Migration):
    dependencies = [
        ('epa_shop', '0001_initial'),  # Your actual dependency
    ]

    operations = [
        migrations.RunPython(fix_duplicate_product_codes),
    ]