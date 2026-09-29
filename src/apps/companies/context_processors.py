"""
Context processors.

These run on every request and inject tenant-aware variables into every
template's context. All of them are defensive: if a company isn't set,
is anonymous, or a field is empty, they return safe defaults instead of
raising — templates should never crash because of a missing tenant.
"""

from apps.companies.models import Company, CompanyJoinRequest


# ============================================
# PLATFORM DEFAULTS
# ============================================
DEFAULT_SYSTEM_NAME = 'RonoSystems'
DEFAULT_PRIMARY_COLOR = '#87CEEB'
DEFAULT_ACCENT_COLOR = '#036a77'


# ============================================
# HELPERS
# ============================================
def _get_effective_company(request):
    """
    Return the Company that should be "active" for this request.

    Precedence:
      1. Support mode  → the impersonated company (super_admin only)
      2. Custom domain → request.company (set by CustomDomainMiddleware)
      3. Logged-in user's own company — BUT skipped for super_admins on
         the platform domain, because they operate at the platform level
         (mother site), not as a tenant.
      4. None          → platform-level (super admin browsing, public pages)

    The result is cached on `request._effective_company` so downstream
    processors and views don't hit the DB multiple times per request.
    """
    cached = getattr(request, '_effective_company', False)
    if cached is not False:
        return cached

    company = None
    user = request.user

    # ── 1. Support mode ──
    if user.is_authenticated:
        support_mode = request.session.get('support_mode', False)
        viewing_company_id = request.session.get('viewing_company_id')
        if support_mode and viewing_company_id:
            company = Company.objects.filter(id=viewing_company_id).first()

    # ── 2. Custom domain ──
    if company is None:
        company = getattr(request, 'company', None)

    # ── 3. User's own company — skip for super_admins on the mother site ──
    if company is None and user.is_authenticated:
        is_super = (
            user.is_superuser
            or getattr(user, 'role', None) == 'super_admin'
        )
        if not is_super:
            company = getattr(user, 'company', None)

    request._effective_company = company
    return company


# ============================================
# PENDING JOIN REQUESTS
# ============================================
def pending_join_requests(request):
    """Inject pending_join_requests_count into every template context."""
    count = 0
    try:
        user = request.user
        if user.is_authenticated and getattr(user, 'role', None) in (
            'company_admin', 'super_admin'
        ):
            company = getattr(user, 'company', None)
            if company:
                count = CompanyJoinRequest.objects.filter(
                    company=company, status='pending'
                ).count()
    except Exception:
        count = 0
    return {'pending_join_requests_count': count}


# ============================================
# SUPPORT MODE
# ============================================
def support_mode_context(request):
    """
    Adds `support_company` to the context when in support mode.

    This allows base.html to:
        - Display the viewed company's name/logo in the sidebar
        - Show the orange "SUPPORT MODE" banner
        - Render the elapsed-time timer
    """
    support_company = None

    if request.user.is_authenticated:
        viewing_company_id = request.session.get('viewing_company_id')
        support_mode = request.session.get('support_mode', False)

        if support_mode and viewing_company_id:
            try:
                support_company = Company.objects.get(id=viewing_company_id)
            except Company.DoesNotExist:
                pass

    return {
        'support_company': support_company,
        'is_support_mode': support_company is not None,
    }


# ============================================
# COMPANY BRANDING (favicon, logo, colors, name)
# ============================================
def company_branding_context(request):
    """
    Inject tenant-specific branding into every template — but ONLY override
    the platform-wide defaults (from `system_settings`) when the tenant
    actually has a value set.

    Precedence for each field:
        tenant value (if set) > platform value from `system_settings`

    Fields provided (only when present, so `system_settings` keeps control
    on non-tenant pages):
        site_logo_url       → company.logo_url
        site_favicon_url    → company.favicon_url
        site_primary_color  → company.primary_color
        site_accent_color   → company.accent_color
        system_name         → company.display_name

    Always provided:
        current_company     → the effective Company (or None)
        is_custom_domain    → True when the request arrived on a tenant domain

    Behavior by scenario:
        - Super admin on `/settings/` (mother site):
              current_company = None
              → this processor sets only `current_company` and `is_custom_domain`;
                `system_settings` provides site_logo_url / site_favicon_url / etc.
        - Super admin in support mode:
              current_company = impersonated company
              → overrides branding with that company's values (only if set)
        - Company user on platform URL:
              current_company = their company
              → overrides branding with their values (only if set)
        - Any user on a custom domain:
              current_company = the domain owner
              → overrides branding with that company's values (only if set)
    """
    company = _get_effective_company(request)
    is_custom_domain = getattr(request, 'company', None) is not None

    ctx = {
        'current_company': company,
        'is_custom_domain': is_custom_domain,
    }

    # Nothing to override if there's no active tenant.
    # `apps.settings.context_processors.system_settings` provides the
    # platform-wide logo / favicon / colors in that case.
    if company is None:
        return ctx

    # Override ONLY the fields the tenant has filled in.
    # Unset fields fall through to whatever `system_settings` provided.
    if company.logo_url:
        ctx['site_logo_url'] = company.logo_url

    if company.favicon_url:
        ctx['site_favicon_url'] = company.favicon_url

    if company.login_background_url:                              
        ctx['login_background_url'] = company.login_background_url


    if company.primary_color:
        ctx['site_primary_color'] = company.primary_color

    if company.accent_color:
        ctx['site_accent_color'] = company.accent_color

    if company.system_name:
        ctx['system_name'] = company.system_name

    return ctx