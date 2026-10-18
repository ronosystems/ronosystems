# apps/plans/context_processors.py

from django.utils import timezone
from django.db import models

def plan_features(request):
    """
    Strictly evaluates the ACTIVE subscription for the current company.
    Does NOT fall back to company.plan unless there is no active sub.
    """
    user = getattr(request, 'user', None)

    flags = {
        'company_has_treasury': False,
        'company_has_workshop': False,
        'my_open_jobs_count': 0,
        'current_subscription': None, 
    }

    if not user or not user.is_authenticated:
        return flags

    # 1. Find the correct company for this request
    company = getattr(request, 'company', None)
    
    if not company and hasattr(request, 'session'):
        viewing_company_id = request.session.get('viewing_company_id')
        if viewing_company_id:
            from apps.companies.models import Company
            company = Company.objects.filter(id=viewing_company_id).first()
            
    if not company:
        company = getattr(user, 'company', None)

    # If there's truly no company (e.g. super_admin on mother site), give them access
    if not company:
        if getattr(user, 'role', None) == 'super_admin' or user.is_superuser:
            flags['company_has_treasury'] = True
            flags['company_has_workshop'] = True
        return flags

    # 2. Look ONLY at the ACTIVE subscription
    active_sub = (
        company.subscriptions
        .filter(status='active')
        .filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=timezone.now())
        )
        .select_related('plan')
        .order_by('-created_at')
        .first()
    )

    plan = None
    if active_sub:
        plan = active_sub.plan
        flags['current_subscription'] = active_sub 
    else:
        # 3. ONLY fall back to company.plan if there are no subscription rows at all
        if not company.subscriptions.exists():
            plan = getattr(company, 'plan', None)

    flags['company_has_treasury'] = bool(plan and plan.has_treasury)
    flags['company_has_workshop'] = bool(plan and plan.has_workshop)

    # Workshop badge for technicians
    if user.role == 'company_technician' and flags['company_has_workshop']:
        try:
            from apps.workshop.models import WorkshopJob
            flags['my_open_jobs_count'] = (
                WorkshopJob.objects
                .filter(assigned_technician=user)
                .exclude(status__in=['delivered', 'cancelled', 'unrepairable'])
                .count()
            )
        except Exception:
            flags['my_open_jobs_count'] = 0

    return flags

treasury_access = plan_features