from django.db import migrations, models


def forwards(apps, schema_editor):
    Tx = apps.get_model('mpesa', 'MpesaTransaction')
    Tx.objects.update(provider='daraja')
    Tx.objects.update(provider_ref=models.F('checkout_request_id'))


def backwards(apps, schema_editor):
    Tx = apps.get_model('mpesa', 'MpesaTransaction')
    Tx.objects.update(provider_ref=None)


class Migration(migrations.Migration):

    dependencies = [
        ('mpesa', '0004_add_provider_and_provider_ref'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]