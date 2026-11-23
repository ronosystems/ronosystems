from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Count
from apps.customers.models import Customer

User = get_user_model()


class Command(BaseCommand):
    help = "Verify Customer <-> User delete-sync health."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help="Delete orphaned rows found during the check.",
        )

    def handle(self, *args, **options):
        fix = options['fix']

        self.stdout.write("=" * 60)
        self.stdout.write("CUSTOMER <-> USER DELETE-SYNC HEALTH CHECK")
        self.stdout.write("=" * 60)

        problems = 0

        # ── 1. Orphaned customers (user_id is NULL) ─────────────────────
        orphan_customers = Customer.objects.filter(user__isnull=True)
        n = orphan_customers.count()
        if n == 0:
            self.stdout.write(self.style.SUCCESS(f"[1] Orphaned customers: 0"))
        else:
            problems += 1
            self.stdout.write(self.style.WARNING(f"[1] Orphaned customers: {n}"))
            for c in orphan_customers[:10]:
                self.stdout.write(f"    - id={c.pk} phone={c.phone_number} name={c.full_name}")
            if fix:
                deleted, _ = orphan_customers.delete()
                self.stdout.write(self.style.SUCCESS(f"    ✔ Deleted {deleted} orphaned customer(s)"))

        # ── 2. Orphaned users (no customer profile, not staff) ──────────
        orphan_users = User.objects.filter(
            customer_profiles__isnull=True,
            is_staff=False,
            is_superuser=False,
        )
        n = orphan_users.count()
        if n == 0:
            self.stdout.write(self.style.SUCCESS(f"[2] Orphaned users: 0"))
        else:
            problems += 1
            self.stdout.write(self.style.WARNING(f"[2] Orphaned users: {n}"))
            for u in orphan_users[:10]:
                self.stdout.write(f"    - id={u.pk} username={u.username} phone={u.phone}")
            if fix:
                deleted, _ = orphan_users.delete()
                self.stdout.write(self.style.SUCCESS(f"    ✔ Deleted {deleted} orphaned user(s)"))

        # ── 3. Counts align ─────────────────────────────────────────────
        total_customers = Customer.objects.count()
        total_users_with_profile = User.objects.filter(
            customer_profiles__isnull=False
        ).count()
        if total_customers == total_users_with_profile:
            self.stdout.write(self.style.SUCCESS(
                f"[3] Counts align: {total_customers} customers == {total_users_with_profile} users"
            ))
        else:
            problems += 1
            self.stdout.write(self.style.ERROR(
                f"[3] Count mismatch: {total_customers} customers vs {total_users_with_profile} users-with-profile"
            ))

        # ── 4. FK on_delete is CASCADE ──────────────────────────────────
        on_delete = Customer._meta.get_field('user').remote_field.on_delete.__name__
        if on_delete == 'CASCADE':
            self.stdout.write(self.style.SUCCESS(f"[4] FK on_delete: CASCADE"))
        else:
            problems += 1
            self.stdout.write(self.style.ERROR(
                f"[4] FK on_delete is {on_delete} — expected CASCADE. Run migrations."
            ))

        # ── 5. Duplicate (company, phone) users with profiles ───────────
        dupes = (
            User.objects
            .filter(customer_profiles__isnull=False)
            .values('company_id', 'phone')
            .annotate(n=Count('id'))
            .filter(n__gt=1)
        )
        n = dupes.count()
        if n == 0:
            self.stdout.write(self.style.SUCCESS(f"[5] Duplicate (company, phone) users: 0"))
        else:
            problems += 1
            self.stdout.write(self.style.WARNING(f"[5] Duplicate (company, phone) users: {n}"))
            for d in dupes[:10]:
                self.stdout.write(f"    - company_id={d['company_id']} phone={d['phone']} count={d['n']}")

        # ── Summary ─────────────────────────────────────────────────────
        self.stdout.write("=" * 60)
        if problems == 0:
            self.stdout.write(self.style.SUCCESS("RESULT: ✅ All checks passed — delete-sync is healthy."))
        else:
            self.stdout.write(self.style.WARNING(
                f"RESULT: ⚠️  {problems} check(s) reported issues. "
                f"{'They were auto-fixed.' if fix else 'Re-run with --fix to clean up.'}"
            ))
        self.stdout.write("=" * 60)