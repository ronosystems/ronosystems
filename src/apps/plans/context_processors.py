# apps/plans/context_processors.py

from django.utils import timezone
from django.db import models
from apps.plans.models import Plan

def plan_features(request):
    """
    Dynamically evaluates ALL active features for the current company 
    based on the Plan.FEATURE_FLAGS list.
    """
    user = getattr(request, 'user', None)

    # 1. Initialize all flags to False dynamically
    feature_keys = [flag for flag, label in Plan.FEATURE_FLAGS]
    
    flags = {
        'my_open_jobs_count': 0,
        'current_subscription': None, 
    }
    
    # Populate 'company_has_treasury', 'company_has_workshop', etc.
    for key in feature_keys:
        flags[f'company_{key}'] = False

    if not user or not user.is_authenticated:
        return flags

    # 2. Find the correct company
    company = getattr(request, 'company', None)
    
    if not company and hasattr(request, 'session'):
        viewing_company_id = request.session.get('viewing_company_id')
        if viewing_company_id:
            from apps.companies.models import Company
            company = Company.objects.filter(id=viewing_company_id).first()
            
    if not company:
        company = getattr(user, 'company', None)

    # 3. Super admins on mother site get everything
    if not company:
        if getattr(user, 'role', None) == 'super_admin' or user.is_superuser:
            for key in feature_keys:
                flags[f'company_{key}'] = True
        return flags

    # 4. Look ONLY at the ACTIVE subscription
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
        # Fallback to company.plan ONLY if there are no subscription rows at all
        if not company.subscriptions.exists():
            plan = getattr(company, 'plan', None)

    # 5. Dynamically set flags based on the resolved plan
    if plan:
        for key in feature_keys:
            flags[f'company_{key}'] = bool(getattr(plan, key, False))

    # 6. Workshop badge logic
    if user.role == 'company_technician' and flags.get('company_has_workshop'):
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

# Backward-compat alias
treasury_access = plan_features