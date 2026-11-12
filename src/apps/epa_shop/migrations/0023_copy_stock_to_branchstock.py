from django.db import migrations


def forwards(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    BranchStock = apps.get_model('epa_shop', 'BranchStock')
    Phone = apps.get_model('epa_shop', 'Phone')
    Electronic = apps.get_model('epa_shop', 'Electronic')
    Accessory = apps.get_model('epa_shop', 'Accessory')

    for model in (Phone, Electronic, Accessory):
        ct, _ = ContentType.objects.get_or_create(
            app_label='epa_shop',
            model=model._meta.model_name,
        )
        for product in model.objects.all():
            if not product.branch_id:
                continue
            BranchStock.objects.update_or_create(
                branch_id=product.branch_id,
                content_type=ct,
                object_id=product.pk,
                defaults={
                    'company_id': product.company_id,
                    'quantity_in_stock': product.quantity_in_stock or 0,
                    'minimum_stock_level': product.minimum_stock_level or 2,
                    'maximum_stock_level': product.maximum_stock_level or 100,
                },
            )
            model.objects.filter(pk=product.pk).update(
                total_quantity_in_stock=product.quantity_in_stock or 0,
            )


class Migration(migrations.Migration):
    dependencies = [
        ('epa_shop', '0022_add_branchstock'),
    ]

    operations = [
        migrations.RunPython(forwards),
    ]