def company_context(request):
    """
    Add company + dynamic base template + support-mode flags to all contexts.

    Priority order for resolving the "current" company:
      1. Support mode   (super admin viewing another company)
      2. request.tenant_company  (set by CustomDomainMiddleware for custom domains)
      3. request.user.company    (the user's own tenant)
      4. request.company         (legacy fallback)

    Exposes:
      - company              → the effective company (support target or user's own)
      - company_id           → company.id or None
      - user_branch          → user's branch or None
      - base_template        → correct base HTML for the business type
      - support_company      → the target company during support mode, else None
      - is_support_mode      → True if super admin is currently in support mode
    """
    company = None
    user_branch = None
    support_company = None
    in_support_mode = False

    # ---------- 1. Custom domain resolution wins ----------
    company = getattr(request, 'tenant_company', None)

    # ---------- 2. Support mode (super admin viewing a company) ----------
    if (
        request.user.is_authenticated
        and getattr(request.user, 'role', None) == 'super_admin'
        and request.session.get('support_mode')
        and request.session.get('viewing_company_id')
    ):
        try:
            from apps.companies.models import Company
            support_company = Company.objects.get(
                id=request.session['viewing_company_id']
            )
            company = support_company
            in_support_mode = True
        except Exception:
            # Session had stale data — clean it up
            request.session.pop('viewing_company_id', None)
            request.session.pop('support_mode', None)
            request.session.pop('support_started_at', None)

    # ---------- 3. Fall back to the authenticated user's company ----------
    if not company and request.user.is_authenticated:
        if hasattr(request.user, 'company') and request.user.company:
            company = request.user.company

    # ---------- 4. Legacy fallback ----------
    if not company and hasattr(request, 'company'):
        company = request.company

    # ---------- User's branch ----------
    if request.user.is_authenticated:
        if hasattr(request.user, 'branch') and request.user.branch:
            user_branch = request.user.branch

    # ---------- Dynamic base template by business type ----------
    base_template = _resolve_base_template(request, company)

    return {
        'company': company,
        'company_id': company.id if company else None,
        'user_branch': user_branch,
        'base_template': base_template,

        # Support-mode context — used by every base template
        'support_company': support_company,
        'is_support_mode': in_support_mode,
    }



    

# ============================================================
# BASE TEMPLATE RESOLUTION
# ============================================================

# Keyword → base template file
# Order matters: first match wins. Keywords are matched against the
# lowercase business_type.name.
BUSINESS_TYPE_BASES = [
    ('kuku',       'kuku_base.html'),
    ('poultry',    'kuku_base.html'),
    ('supermarket','base.html'),   # add supermarket_base.html later if needed
    ('epa',        'base.html'),
    ('electronic', 'base.html'),
    ('retail',     'base.html'),
    ('restaurant', 'base.html'),
    ('healthcare', 'base.html'),
    ('education',  'base.html'),
]

DEFAULT_BASE_TEMPLATE = 'base.html'


def _resolve_base_template(request, company):
    """
    Pick the base template that matches the current business type.

    In support mode, the target company's business type wins — so a super
    admin viewing a Kuku Biz company sees the Kuku Biz sidebar, not their
    own.
    """
    # In support mode, `company` passed in is already the support target
    # (see company_context above). So we just use it directly.
    target_company = company

    if not target_company:
        return DEFAULT_BASE_TEMPLATE

    business_type = getattr(target_company, 'business_type', None)
    if not business_type or not getattr(business_type, 'name', None):
        return DEFAULT_BASE_TEMPLATE

    name = business_type.name.lower()
    for keyword, template in BUSINESS_TYPE_BASES:
        if keyword in name:
            return template

    return DEFAULT_BASE_TEMPLATE