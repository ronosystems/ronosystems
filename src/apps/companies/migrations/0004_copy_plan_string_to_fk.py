from django.db import migrations


def copy_string_plan_to_fk(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    Plan = apps.get_model('plans', 'Plan')

    plan_map = {p.name.lower().strip(): p.id for p in Plan.objects.all()}
    free_id = plan_map.get('free')

    for company in Company.objects.all():
        raw = (company.plan or '').strip().lower()

        # Exact match
        plan_id = plan_map.get(raw)

        # Fuzzy fallback (e.g. 'pro' matches 'premium')
        if plan_id is None and raw:
            for name, pid in plan_map.items():
                if name.startswith(raw) or raw.startswith(name):
                    plan_id = pid
                    break

        # Final fallback: free plan, or first plan available
        if plan_id is None:
            plan_id = free_id or next(iter(plan_map.values()), None)

        if plan_id is not None:
            company.plan_fk_id = plan_id
            company.save(update_fields=['plan_fk'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0003_add_plan_fk'),
        ('plans', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(copy_string_plan_to_fk, reverse_noop),
    ]