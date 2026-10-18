# apps/plans/migrations/0011_plan_kind_and_unique_together.py

from django.conf import settings
from django.db import migrations, models


VALID_PLAN_KINDS = {'free', 'basic', 'premium', 'standard', 'enterprise'}


def backfill_plan_kind(apps, schema_editor):
    """
    Copy the old `name` (which was constrained to PLAN_TYPES choices) into
    the new `plan_kind` field so premium/free/enterprise plans keep their
    grouping after the schema change.
    """
    Plan = apps.get_model('plans', 'Plan')
    for plan in Plan.objects.all():
        if plan.name in VALID_PLAN_KINDS:
            plan.plan_kind = plan.name
            plan.save(update_fields=['plan_kind'])


def unbackfill_plan_kind(apps, schema_editor):
    """No-op — reversible safely because plan_kind has a default."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0016_company_company_pin'),
        ('plans', '0010_alter_plan_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Add the new field (defaults to 'basic').
        migrations.AddField(
            model_name='plan',
            name='plan_kind',
            field=models.CharField(
                choices=[
                    ('free', 'FREE'),
                    ('basic', 'BASIC'),
                    ('premium', 'PREMIUM'),
                    ('standard', 'STANDARD'),
                    ('enterprise', 'ENTERPRISE'),
                ],
                default='basic',
                help_text='Grouping used by the UI (free / basic / premium / …).',
                max_length=20,
            ),
        ),

        # 2. NEW: Backfill plan_kind from the old name before we loosen
        #    `name`, so each row keeps its correct kind.
        migrations.RunPython(backfill_plan_kind, unbackfill_plan_kind),

        # 3. Loosen `name`: drop choices + unique.
        migrations.AlterField(
            model_name='plan',
            name='name',
            field=models.CharField(
                help_text='Internal plan name. Unique together with billing_cycle.',
                max_length=50,
            ),
        ),

        # 4. Restore uniqueness as (name, billing_cycle).
        migrations.AlterUniqueTogether(
            name='plan',
            unique_together={('name', 'billing_cycle')},
        ),

        # 5. Cosmetic help_text change on Subscription.
        migrations.AlterField(
            model_name='subscription',
            name='review_note',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Optional note from the reviewer.',
            ),
        ),

        # 6. Indexes.
        migrations.AddIndex(
            model_name='plan',
            index=models.Index(
                fields=['is_active', 'order'],
                name='plans_is_acti_49f020_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='subscription',
            index=models.Index(
                fields=['company', 'status'],
                name='subscriptio_company_0d7ef6_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='subscription',
            index=models.Index(
                fields=['end_date'],
                name='subscriptio_end_dat_763002_idx',
            ),
        ),
    ]