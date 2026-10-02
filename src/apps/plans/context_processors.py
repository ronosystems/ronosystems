def treasury_access(request):
    """
    Adds `company_has_treasury` to every template context.
    True only if the logged-in user's company has an active plan
    with has_treasury=True.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'company_has_treasury': False}

    # Super admins always see it
    if getattr(user, 'role', None) == 'super_admin':
        return {'company_has_treasury': True}

    company = getattr(user, 'company', None)
    if not company:
        return {'company_has_treasury': False}

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

    return {'company_has_treasury': bool(plan and plan.has_treasury)}