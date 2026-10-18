# apps/plans/templatetags/plan_tags.py

from django import template

register = template.Library()


# ============================================================
# EXISTING TAG (unchanged)
# ============================================================

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


# ============================================================
# NEW FILTERS (used by plans/form.html)
# ============================================================

@register.filter(name='feature_is_on')
def feature_is_on(plan, flag_name):
    """`plan|feature_is_on:'has_treasury'` → bool."""
    if not plan:
        return False
    return bool(getattr(plan, flag_name, False))


FEATURE_ICONS = {
    'has_api_access':        'code',
    'has_advanced_reports':  'chart-bar',
    'has_custom_branding':   'paint-brush',
    'has_priority_support':  'headset',
    'has_bulk_import':       'file-import',
    'has_custom_domain':     'globe',
    'has_mpesa_integration': 'dollar-sign',
    'has_treasury':          'vault',
    'has_workshop':          'tools',
}


@register.filter(name='feature_icon')
def feature_icon(flag_name):
    """`'has_treasury'|feature_icon` → 'vault'."""
    return FEATURE_ICONS.get(flag_name, 'check')