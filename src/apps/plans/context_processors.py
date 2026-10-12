# apps/plans/context_processors.py

def plan_features(request):
    """
    Exposes plan-gated feature flags to every template context.

    Flags:
      - company_has_treasury   → plan.has_treasury
      - company_has_workshop   → plan.has_workshop
      - my_open_jobs_count     → open jobs assigned to the current technician

    Super admins always get True for every plan flag.
    """
    user = getattr(request, 'user', None)

    # Baseline — returned for every early-exit path
    flags = {
        'company_has_treasury': False,
        'company_has_workshop': False,
        'my_open_jobs_count': 0,
    }

    if not user or not user.is_authenticated:
        return flags

    # Super admin sees everything
    if getattr(user, 'role', None) == 'super_admin':
        flags['company_has_treasury'] = True
        flags['company_has_workshop'] = True
        return flags

    company = getattr(user, 'company', None)
    if not company:
        return flags

    # Prefer the FK on Company
    plan = getattr(company, 'plan', None)

    # Fallback: active subscription
    if plan is None:
        sub = (
            company.subscriptions
            .filter(status='active')
            .select_related('plan')
            .order_by('-created_at')
            .first()
        )
        plan = sub.plan if sub else None

    flags['company_has_treasury'] = bool(plan and plan.has_treasury)
    flags['company_has_workshop'] = bool(plan and plan.has_workshop)

    # Only compute the workshop badge for technicians with workshop access
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
            # If the workshop app isn't migrated yet, don't break every page
            flags['my_open_jobs_count'] = 0

    return flags


# Backward-compat alias — anything still importing treasury_access keeps working.
treasury_access = plan_features