# apps/plans/migrations/0008_rename_has_mpesa_intergration_plan_has_mpesa_integration.py
from django.db import migrations


class Migration(migrations.Migration):
    """
    No-op migration.

    The actual column rename from `has_mpesa_intergration` → `has_mpesa_integration`
    was already performed by migration `0007_rename_mpesa_integration_typo`
    via RunSQL. This migration only records the model-state change
    (so Django's internal state matches the model definition).
    """

    dependencies = [
        ('plans', '0007_rename_mpesa_integration_typo'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # DB column already correct
            state_operations=[
                migrations.RenameField(
                    model_name='plan',
                    old_name='has_mpesa_intergration',
                    new_name='has_mpesa_integration',
                ),
            ],
        ),
    ]