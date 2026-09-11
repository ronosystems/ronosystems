# apps/plans/management/commands/expire_subscriptions.py

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.plans.models import Subscription
from apps.companies.models import Company


class Command(BaseCommand):
    help = (
        "Mark expired subscriptions as 'expired' and deactivate their companies. "
        "Safe to run repeatedly. Optionally report subscriptions expiring soon."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--warn-days',
            type=int,
            default=7,
            help=(
                "Report subscriptions expiring within N days (default: 7). "
                "Pass 0 to disable the warning section."
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Show what would happen without modifying the database.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        warn_days = options['warn_days']
        dry_run = options['dry_run']

        self.stdout.write(self.style.MIGRATE_HEADING("=== Expire subscriptions ==="))
        self.stdout.write(f"Now: {now:%Y-%m-%d %H:%M:%S}")
        self.stdout.write(f"Dry-run: {dry_run}")
        self.stdout.write("")

        expired_count = self._expire_now(now, dry_run)
        self.stdout.write("")

        warn_count = 0
        if warn_days > 0:
            warn_count = self._warn_soon(now, warn_days)
            self.stdout.write("")

        # ---------- Summary ----------
        self.stdout.write(self.style.SUCCESS(
            f"Done. Expired: {expired_count}  |  Expiring soon: {warn_count}"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — no changes were saved."
            ))

    # ============================================
    # STEP 1: Mark expired + deactivate company
    # ============================================

    def _expire_now(self, now, dry_run):
        self.stdout.write(self.style.MIGRATE_HEADING("--- Marking expired ---"))

        expired_subs = (
            Subscription.objects
            .filter(status='active', end_date__lt=now, end_date__isnull=False)
            .select_related('company', 'plan')
        )

        count = 0
        for sub in expired_subs:
            company = sub.company

            if not dry_run:
                # Use model helper — flips status + timestamp
                sub.mark_expired()

                # Deactivate the company only if no other active sub remains
                still_active = (
                    company.subscriptions
                    .filter(status='active', end_date__gt=now)
                    .exclude(pk=sub.pk)
                    .exists()
                )

                if not still_active and company.status != 'inactive':
                    company.status = 'inactive'
                    company.is_active = False
                    company.save(update_fields=['status', 'is_active'])

            count += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  EXPIRED: {company.name:<30} "
                    f"plan={sub.plan.display_name:<15} "
                    f"end={sub.end_date:%Y-%m-%d}"
                )
            )

        if count == 0:
            self.stdout.write("  (none)")

        return count

    # ============================================
    # STEP 2: Report soon-to-expire
    # ============================================

    def _warn_soon(self, now, warn_days):
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"--- Expiring within {warn_days} days ---"
        ))

        warn_until = now + timedelta(days=warn_days)
        soon_subs = (
            Subscription.objects
            .filter(
                status='active',
                end_date__gte=now,
                end_date__lte=warn_until,
            )
            .select_related('company', 'plan')
            .order_by('end_date')
        )

        count = 0
        for sub in soon_subs:
            # Use model helper
            days_left = sub.days_until_expiry or 0
            count += 1

            self.stdout.write(
                self.style.NOTICE(
                    f"  WARN: {sub.company.name:<30} "
                    f"plan={sub.plan.display_name:<15} "
                    f"expires={sub.end_date:%Y-%m-%d} "
                    f"({days_left}d left)"
                )
            )

            # ---------- Optional email ----------
            # Uncomment and adjust when ready to notify customers
            #
            # from django.core.mail import send_mail
            # from django.conf import settings
            # if sub.company.email:
            #     send_mail(
            #         subject=(
            #             f"Your {sub.plan.display_name} subscription "
            #             f"expires in {days_left} days"
            #         ),
            #         message=(
            #             f"Hi {sub.company.name},\n\n"
            #             f"Your {sub.plan.display_name} subscription will expire "
            #             f"on {sub.end_date:%Y-%m-%d}. "
            #             "Please renew to avoid losing access.\n\n"
            #             "— RonoSystems"
            #         ),
            #         from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@ronosystems.com'),
            #         recipient_list=[sub.company.email],
            #         fail_silently=True,
            #     )

        if count == 0:
            self.stdout.write("  (none)")

        return count