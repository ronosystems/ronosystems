from django.db import migrations

def backfill_all(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    Membership = apps.get_model('accounts', 'Membership')

    existing_user_ids = set(Membership.objects.values_list('user_id', flat=True))
    to_create = []
    for u in User.objects.filter(company__isnull=False).iterator():
        if u.id in existing_user_ids:
            continue
        if u.role == 'super_admin' or u.is_superuser:
            continue
        to_create.append(Membership(
            user_id=u.id,
            company_id=u.company_id,
            branch_id=u.branch_id,
            role=u.role or 'company_staff',
            is_active=True,
            is_primary=True,
        ))
    Membership.objects.bulk_create(to_create, ignore_conflicts=True)

    for m in Membership.objects.filter(is_primary=True, is_active=True).select_related('user').iterator():
        User.objects.filter(pk=m.user_id, company__isnull=True).update(
            company_id=m.company_id,
            role=m.role,
            branch_id=m.branch_id,
        )

    for user_id in Membership.objects.filter(is_primary=False).values_list('user_id', flat=True).distinct():
        if not Membership.objects.filter(user_id=user_id, is_primary=True).exists():
            first = Membership.objects.filter(user_id=user_id, is_active=True).order_by('created_at').first()
            if first:
                first.is_primary = True
                first.save(update_fields=['is_primary'])

def reverse_backfill(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_membership_company_username_alter_user_email_and_more'),
    ]
    operations = [
        migrations.RunPython(backfill_all, reverse_backfill),
    ]
