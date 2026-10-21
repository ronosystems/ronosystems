"""
Context processors.

These run on every request and inject tenant-aware variables into every
template's context. All of them are defensive: if a company isn't set,
is anonymous, or a field is empty, they return safe defaults instead of
raising — templates should never crash because of a missing tenant.
"""

from apps.companies.models import Company, CompanyJoinRequest, TenantFeedback
from apps.business_types.business_type_registry import BusinessTypeEnum

# ============================================
# ACTIVE BASE TEMPLATE (Dynamic)
# ============================================
def active_base_template(request):
    """
    Automatically selects the correct base template based on the company's business type.
    Falls back to 'base.html' if no match is found.
    """
    # Use _get_effective_company to support Super Admin support mode!
    company = _get_effective_company(request)
    
    if not company or not getattr(company, 'business_type', None):
        return {'base_template': 'base.html'}

    # Get the business name from the database (e.g., "Chama", "Kuku Biz")
    business_name = company.business_type.name
    
    # Look it up in the registry
    registry_entry = BusinessTypeEnum.get_by_name(business_name)
    
    if registry_entry:
        module = registry_entry.value['integration']['module']
        # Map the module to the base template file
        if module == 'chama':
            return {'base_template': 'chama_base.html'}
        elif module == 'kuku_biz':
            return {'base_template': 'kuku_base.html'}
        elif module == 'epa_shop':
            return {'base_template': 'base.html'}
        # Add other modules here if you have specific bases for them

    # Default fallback
    return {'base_template': 'base.html'}

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
    (Kept exactly as you had it - it's perfect)
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
    Inject tenant-specific branding into every template.
    """
    company = _get_effective_company(request)
    is_custom_domain = getattr(request, 'company', None) is not None

    ctx = {
        'current_company': company,
        'is_custom_domain': is_custom_domain,
    }

    if company is None:
        return ctx

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


# ============================================
# RECEIPT SETTINGS
# ============================================
def receipt_settings_context(request):
    """
    Inject `receipt_settings` (dict) into every template context.
    """
    if hasattr(request, '_receipt_settings'):
        return {'receipt_settings': request._receipt_settings}

    company = _get_effective_company(request)

    settings_dict = None
    if company is not None:
        try:
            from apps.companies.views import get_company_settings
            settings_dict = get_company_settings(company).get('receipt', {})
        except Exception:
            settings_dict = None

    if not settings_dict:
        settings_dict = {
            'receipt_header': '',
            'receipt_footer': '',
            'receipt_format': 'standard',
            'show_logo': True,
            'show_company_details': True,
            'show_customer_details': True,
            'show_items': True,
            'show_totals': True,
            'show_payment': True,
            'show_signature': True,
            'receipt_title': 'RECEIPT',
            'thank_you_message': 'Thank you for your business!',
            'include_barcode': False,
            'print_copies': 1,
            'auto_print': False,
            'receipt_font_size': '14',
            'receipt_width': '80',
            'custom_css': '',
        }

    request._receipt_settings = settings_dict
    return {'receipt_settings': settings_dict}


# ============================================
# PENDING FEEDBACK COUNT (for super-admins only)
# ============================================
def pending_feedback_count(request):
    """
    Inject the number of *new* feedback items into every template context
    for super-admins only.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'pending_feedback_count': 0}

    is_hub_owner = user.is_superuser or getattr(user, 'role', '') == 'super_admin'
    if not is_hub_owner:
        return {'pending_feedback_count': 0}

    from apps.companies.support_utils import is_support_mode
    if is_support_mode(request):
        return {'pending_feedback_count': 0}

    count = TenantFeedback.objects.filter(
        status=TenantFeedback.STATUS_NEW,
    ).count()

    return {'pending_feedback_count': count}


# ============================================
# COMPANY FEATURE FLAGS (Treasury, Workshop, etc.)
# ============================================
def company_features_context(request):
    """
    Strictly evaluates feature flags based on the company's ACTIVE subscription.
    """
    company = _get_effective_company(request)
    
    has_treasury = False
    has_workshop = False

    if company:
        active_sub = (
            company.subscriptions
            .filter(status='active')
            .order_by('-created_at')
            .first()
        )
        
        # FIXED: Check if it's a property or method
        if active_sub:
            is_active = active_sub.is_active_subscription
            if callable(is_active):
                is_active = is_active()
                
            if is_active:
                has_treasury = bool(active_sub.plan.has_treasury)
                has_workshop = bool(active_sub.plan.has_workshop)
        
        if not has_treasury and not has_workshop and company.plan:
            # Fallback to the cached plan (only if there is no active sub row at all)
            has_treasury = bool(company.plan.has_treasury)
            has_workshop = bool(company.plan.has_workshop)

    return {
        'company_has_treasury': has_treasury,
        'company_has_workshop': has_workshop,
    }