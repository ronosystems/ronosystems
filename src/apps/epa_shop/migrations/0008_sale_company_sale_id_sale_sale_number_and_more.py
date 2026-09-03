# apps/epa_shop/migrations/0008_add_company_sale_id.py

from django.db import migrations, models

def populate_sale_number(apps, schema_editor):
    Sale = apps.get_model('epa_shop', 'Sale')
    for sale in Sale.objects.all():
        sale.sale_number = sale.id
        sale.save(update_fields=['sale_number'])

def populate_company_sale_id(apps, schema_editor):
    Sale = apps.get_model('epa_shop', 'Sale')
    for sale in Sale.objects.all():
        company_prefix = sale.company.name[:3].upper() if sale.company and sale.company.name else "COM"
        sale.company_sale_id = f"{company_prefix}-{str(sale.sale_number).zfill(6)}"
        sale.save(update_fields=['company_sale_id'])

class Migration(migrations.Migration):

    dependencies = [
        ('epa_shop', '0007_alter_customer_phone_and_more'),
    ]

    operations = [
        # Step 1: Add sale_number with default
        migrations.AddField(
            model_name='sale',
            name='sale_number',
            field=models.PositiveIntegerField(default=1, editable=False),
            preserve_default=False,
        ),
        
        # Step 2: Populate sale_number
        migrations.RunPython(populate_sale_number, reverse_code=migrations.RunPython.noop),
        
        # Step 3: Add company_sale_id (allow null temporarily)
        migrations.AddField(
            model_name='sale',
            name='company_sale_id',
            field=models.CharField(blank=True, editable=False, help_text='Company prefix + sale number', max_length=50, null=True),
        ),
        
        # Step 4: Populate company_sale_id
        migrations.RunPython(populate_company_sale_id, reverse_code=migrations.RunPython.noop),
        
        # Step 5: Make company_sale_id required
        migrations.AlterField(
            model_name='sale',
            name='company_sale_id',
            field=models.CharField(editable=False, help_text='Company prefix + sale number', max_length=50, unique=True),
            preserve_default=False,
        ),
        
        # Step 6: Add unique constraint
        migrations.AlterUniqueTogether(
            name='sale',
            unique_together={('company', 'sale_number')},
        ),
        
        # Step 7: Add indexes
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['company', 'sale_number'], name='epa_sales_company_sale_number_idx'),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['company_sale_id'], name='epa_sales_company_sale_id_idx'),
        ),
    ]