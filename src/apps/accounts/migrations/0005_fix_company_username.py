import random, string
from django.db import migrations

def fix_usernames(apps, schema_editor):
    Membership = apps.get_model('accounts', 'Membership')
    User = apps.get_model('accounts', 'User')
    for m in Membership.objects.filter(company_username__isnull=True).select_related('user', 'company'):
        first = (m.user.first_name or 'X')[0].upper()
        last = (m.user.last_name or 'X')[0].upper()
        prefix = (m.company.name[0].upper() if m.company and m.company.name else 'C')
        while True:
            digits = ''.join(random.choices(string.digits, k=6))
            username = f"{prefix}{first}{last}{digits}"
            if not Membership.objects.filter(company_username=username).exists() and not User.objects.filter(username=username).exists():
                m.company_username = username
                m.save(update_fields=['company_username'])
                break

def reverse_fix(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_backfill_all_memberships'),
    ]
    operations = [
        migrations.RunPython(fix_usernames, reverse_fix),
    ]
