# apps/company/context_processors.py

from django.utils import timezone


def company_context(request):
    """
    Provides `company`, `company_has_treasury`, and the
    count of unapproved (unverified) daily records for the
    current user's scope.
    """
    company = getattr(request, 'company', None) or getattr(request.user, 'company', None)
    company_has_treasury = False
    unverified_daily_records_count = 0

    if company and request.user.is_authenticated:
        # Does this company have treasury enabled (i.e. any Treasury row)?
        from apps.treasury.models import Treasury, DailyRecord

        company_has_treasury = Treasury.objects.filter(company=company).exists()

        # -------- Count unverified daily records --------
        # Scope rules:
        #  * super_admin / company_admin → all branches of the company
        #  * company_manager / mpesa_agent → only their own branch (if any)
        user = request.user
        qs = DailyRecord.objects.filter(company=company, is_approved=False)

        if user.role in ('company_manager', 'mpesa_agent', 'company_cashier',
                         'company_agent', 'company_staff'):
            branch = getattr(user, 'branch', None)
            if branch:
                qs = qs.filter(branch=branch)
            else:
                # No branch assigned → nothing to show
                qs = qs.none()

        unverified_daily_records_count = qs.count()

    return {
        'company': company,
        'company_has_treasury': company_has_treasury,
        'unverified_daily_records_count': unverified_daily_records_count,
    }