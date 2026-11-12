from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('epa_shop', '0023_copy_stock_to_branchstock'),
    ]

    operations = [
        migrations.RemoveField(model_name='phone', name='branch'),
        migrations.RemoveField(model_name='phone', name='quantity_in_stock'),
        migrations.RemoveField(model_name='phone', name='minimum_stock_level'),
        migrations.RemoveField(model_name='phone', name='maximum_stock_level'),
        migrations.RemoveField(model_name='electronic', name='branch'),
        migrations.RemoveField(model_name='electronic', name='quantity_in_stock'),
        migrations.RemoveField(model_name='electronic', name='minimum_stock_level'),
        migrations.RemoveField(model_name='electronic', name='maximum_stock_level'),
        migrations.RemoveField(model_name='accessory', name='branch'),
        migrations.RemoveField(model_name='accessory', name='quantity_in_stock'),
        migrations.RemoveField(model_name='accessory', name='minimum_stock_level'),
        migrations.RemoveField(model_name='accessory', name='maximum_stock_level'),
    ]