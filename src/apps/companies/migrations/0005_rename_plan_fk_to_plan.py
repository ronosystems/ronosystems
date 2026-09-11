from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0004_copy_plan_string_to_fk'),
        ('plans', '0001_initial'),
    ]

    operations = [
        # 1. Drop the old string `plan` column.
        #    Its data is already safely stored in `plan_fk_id` from migration 0004.
        migrations.RemoveField(
            model_name='company',
            name='plan',
        ),

        # 2. Rename plan_fk -> plan (pure column rename, no data movement).
        migrations.RenameField(
            model_name='company',
            old_name='plan_fk',
            new_name='plan',
        ),

        # 3. Add back subscription_start / subscription_end (nullable, safe).
        migrations.AddField(
            model_name='company',
            name='subscription_start',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='company',
            name='subscription_end',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]