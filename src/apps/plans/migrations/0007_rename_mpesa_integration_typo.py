from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0006_subscription_payment_message_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE plans "
                "RENAME COLUMN has_mpesa_intergration TO has_mpesa_integration;"
            ),
            reverse_sql=(
                "ALTER TABLE plans "
                "RENAME COLUMN has_mpesa_integration TO has_mpesa_intergration;"
            ),
        ),
    ]