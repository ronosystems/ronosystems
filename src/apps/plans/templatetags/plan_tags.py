from django import template

register = template.Library()


@register.simple_tag
def company_has_treasury(company):
    """
    Returns True if the company's active plan includes has_treasury.
    Caches the result on the company object to avoid repeat queries.
    """
    if not company:
        return False

    # Cache hit — avoid re-querying on multi-render pages
    cached = getattr(company, '_has_treasury_cache', None)
    if cached is not None:
        return cached

    plan = getattr(company, 'plan', None)

    # Fallback: look up via active subscription
    if plan is None:
        sub = (
            company.subscriptions
            .filter(status='active')
            .select_related('plan')
            .order_by('-created_at')
            .first()
        )
        plan = sub.plan if sub else None

    result = bool(plan and plan.has_treasury)

    # Cache it on the instance (lives for this request only)
    company._has_treasury_cache = result
    return result