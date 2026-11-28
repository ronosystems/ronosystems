"""
Context processors - Tenant-aware.
All defensive: if no tenant, return safe defaults.
Source of truth: request.tenant (set by TenantMiddleware from domain)
NOT user.company, NOT user.role
"""

import os
from django.conf import settings
from apps.companies.models import Company, CompanyJoinRequest, TenantFeedback
from apps.companies.business_types import BusinessTypeEnum

DEFAULT_SYSTEM_NAME = 'RonoSystems'
DEFAULT_PRIMARY_COLOR = '#87CEEB'
DEFAULT_ACCENT_COLOR = '#036a77'


# ============================================
# HELPERS
# ============================================
def _get_effective_company(request):
    cached = getattr(request, '_effective_company', False)
    if cached is not False:
        return cached

    company = None
    user = getattr(request, 'user', None)

    # 1. Support mode
    if user and user.is_authenticated:
        support_mode = request.session.get('support_mode', False)
        viewing_company_id = request.session.get('viewing_company_id')
        if support_mode and viewing_company_id:
            company = Company.objects.filter(id=viewing_company_id).first()

    # 2. Tenant from Middleware (DOMAIN) - most reliable
    if company is None:
        company = getattr(request, 'tenant', None)

    # 3. Backwards compat
    if company is None:
        company = getattr(request, 'company', None)

    # 4. Membership fallback
    if company is None and user and user.is_authenticated:
        if not _is_super_admin(user):
            try:
                last_tenant_id = request.session.get('current_tenant_id')
                if last_tenant_id:
                    m = user.memberships.filter(
                        company_id=last_tenant_id, is_active=True
                    ).select_related('company').first()
                    if m and m.company:
                        company = m.company

                if company is None:
                    m = user.memberships.filter(
                        is_active=True
                    ).select_related('company').order_by('-is_primary', 'created_at').first()
                    if m and m.company:
                        company = m.company
            except Exception:
                pass

    request._effective_company = company
    return company


def _get_user_role_in_company(user, company):
    if not user or not user.is_authenticated or not company:
        return None
    try:
        membership = user.memberships.filter(company=company, is_active=True).first()
        if membership and membership.role:
            return membership.role
        return getattr(user, 'role', None)
    except Exception:
        return getattr(user, 'role', None)


def _is_super_admin(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or getattr(user, 'role', '') == 'super_admin'


def _get_global_system_name():
    """
    FIX: Read the global SYSTEM_NAME setting with a safe lazy import.
    Falls back to DEFAULT_SYSTEM_NAME if the settings app is unavailable.
    """
    try:
        from apps.settings.models import SystemSetting
        return SystemSetting.get_setting('SYSTEM_NAME', DEFAULT_SYSTEM_NAME) or DEFAULT_SYSTEM_NAME
    except Exception:
        return DEFAULT_SYSTEM_NAME


def _get_global_colors():
    """
    FIX: Read global PRIMARY_COLOR / SECONDARY_COLOR settings.
    Falls back to module defaults if unavailable.
    """
    try:
        from apps.settings.models import SystemSetting
        return (
            SystemSetting.get_setting('PRIMARY_COLOR', DEFAULT_PRIMARY_COLOR) or DEFAULT_PRIMARY_COLOR,
            SystemSetting.get_setting('SECONDARY_COLOR', DEFAULT_ACCENT_COLOR) or DEFAULT_ACCENT_COLOR,
        )
    except Exception:
        return DEFAULT_PRIMARY_COLOR, DEFAULT_ACCENT_COLOR


# ============================================
# ACTIVE BASE TEMPLATE
# ============================================
def active_base_template(request):
    company = _get_effective_company(request)
    if not company or not getattr(company, 'business_type', None):
        return {'base_template': 'base.html'}

    business_name = company.business_type.name
    registry_entry = BusinessTypeEnum.get_by_name(business_name)
    if registry_entry:
        module = registry_entry.value['integration']['module']
        if module == 'chama':
            return {'base_template': 'chama_base.html'}
        elif module == 'kuku_biz':
            return {'base_template': 'kuku_base.html'}
        elif module == 'epa_shop':
            return {'base_template': 'base.html'}
    return {'base_template': 'base.html'}


# ============================================
# PENDING JOIN REQUESTS
# ============================================
def pending_join_requests(request):
    count = 0
    try:
        user = request.user
        company = _get_effective_company(request)
        if user.is_authenticated and company:
            role = _get_user_role_in_company(user, company)
            if role in ('company_admin', 'admin', 'manager', 'company_manager') or _is_super_admin(user):
                count = CompanyJoinRequest.objects.filter(company=company, status='pending').count()
    except Exception:
        count = 0
    return {'pending_join_requests_count': count}


# ============================================
# SUPPORT MODE
# ============================================
def support_mode_context(request):
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
# COMPANY BRANDING
# ============================================
def company_branding_context(request):
    company = _get_effective_company(request)
    is_custom_domain = False
    if company:
        host = request.get_host().split(':')[0].lower()
        if company.custom_domain and host == company.custom_domain.lower():
            is_custom_domain = True

    # FIX: Global defaults come from SystemSetting, not hardcoded constants.
    # Tenant-specific overrides (below) still take precedence when present.
    global_system_name = _get_global_system_name()
    global_primary, global_accent = _get_global_colors()

    ctx = {
        'company': company,
        'current_company': company,
        'current_tenant': company,
        'is_custom_domain': is_custom_domain,
        'system_name': global_system_name,
        'site_primary_color': global_primary,
        'site_accent_color': global_accent,
        'CLOUDINARY_CLOUD_NAME': getattr(settings, 'CLOUDINARY_STORAGE', {}).get('CLOUD_NAME', ''),
        'CLOUDINARY_UNSIGNED_PRESET': getattr(settings, 'CLOUDINARY_STORAGE', {}).get('UNSIGNED_PRESET', ''),
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

    if request.user.is_authenticated:
        ctx['current_user_role'] = _get_user_role_in_company(request.user, company)

    return ctx


# ============================================
# RECEIPT SETTINGS
# ============================================
def receipt_settings_context(request):
    if hasattr(request, '_receipt_settings'):
        return {'receipt_settings': request._receipt_settings}

    company = _get_effective_company(request)
    settings_dict = None
    if company is not None:
        try:
            from apps.companies.settings_views import get_company_settings
            settings_dict = get_company_settings(company).get('receipt', {})
        except Exception:
            settings_dict = None

    if not settings_dict:
        settings_dict = {
            'receipt_header': '', 'receipt_footer': '', 'receipt_format': 'standard',
            'show_logo': True, 'show_company_details': True, 'show_customer_details': True,
            'show_items': True, 'show_totals': True, 'show_payment': True, 'show_signature': True,
            'receipt_title': 'RECEIPT', 'thank_you_message': 'Thank you for your business!',
            'include_barcode': False, 'print_copies': 1, 'auto_print': False,
            'receipt_font_size': '14', 'receipt_width': '80', 'custom_css': '',
        }

    request._receipt_settings = settings_dict
    return {'receipt_settings': settings_dict}


# ============================================
# PENDING FEEDBACK COUNT
# ============================================
def pending_feedback_count(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'pending_feedback_count': 0}
    if not _is_super_admin(user):
        return {'pending_feedback_count': 0}
    from apps.companies.support_utils import is_support_mode
    if is_support_mode(request):
        return {'pending_feedback_count': 0}
    count = TenantFeedback.objects.filter(status=TenantFeedback.STATUS_NEW).count()
    return {'pending_feedback_count': count}


# ============================================
# COMPANY FEATURE FLAGS
# ============================================
def company_features_context(request):
    company = _get_effective_company(request)
    has_treasury = False
    has_workshop = False

    if company:
        active_sub = company.subscriptions.filter(status='active').order_by('-created_at').first()
        if active_sub:
            is_active = active_sub.is_active_subscription
            if callable(is_active):
                is_active = is_active()
            if is_active:
                has_treasury = bool(getattr(active_sub.plan, 'has_treasury', False))
                has_workshop = bool(getattr(active_sub.plan, 'has_workshop', False))
        if not has_treasury and not has_workshop and company.plan:
            has_treasury = bool(getattr(company.plan, 'has_treasury', False))
            has_workshop = bool(getattr(company.plan, 'has_workshop', False))

    return {
        'company_has_treasury': has_treasury,
        'company_has_workshop': has_workshop,
    }


# ============================================
# SYSTEM WEBSITE URL
# ============================================
def system_website_url(request):
    explicit = getattr(settings, 'SYSTEM_WEBSITE_URL', None) or os.getenv('SYSTEM_WEBSITE_URL', '')
    if explicit:
        return {'system_website_url': explicit.rstrip('/') + '/'}

    full_host = request.get_host()
    host, _, port = full_host.partition(':')
    host = host.lower()

    system_domain = getattr(settings, 'SYSTEM_DOMAIN', None) or os.getenv('SYSTEM_DOMAIN', '')
    if system_domain:
        host = system_domain
    else:
        SYSTEM_ROOTS = ('localhost', 'ronosystems.onrender.com', 'ronosystems.co.ke')
        for root in SYSTEM_ROOTS:
            if host == root or host.endswith('.' + root):
                host = root
                break
        else:
            if settings.DEBUG:
                host = 'localhost'

    scheme = 'https' if request.is_secure() else 'http'
    port_part = f':{port}' if port else ''
    return {'system_website_url': f'{scheme}://{host}{port_part}/'}


# ============================================
# UNREAD CONTACT MESSAGES
# ============================================
def unread_messages_count(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'unread_messages_count': 0}

    company = _get_effective_company(request)
    role = _get_user_role_in_company(user, company) if company else getattr(user, 'role', '')
    is_admin = _is_super_admin(user) or role in ('super_admin', 'company_admin', 'admin', 'manager', 'company_manager')

    if not is_admin:
        return {'unread_messages_count': 0}

    try:
        from apps.companies.models import ContactMessage
        if company:
            count = ContactMessage.objects.filter(company=company, is_read=False).count()
        else:
            count = ContactMessage.objects.filter(company__isnull=True, is_read=False).count()
    except Exception:
        count = 0
    return {'unread_messages_count': count}


def pending_applications_count(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'pending_applications_count': 0}
    if not _is_super_admin(user) and not user.is_staff:
        return {'pending_applications_count': 0}
    try:
        from apps.companies.models import CompanyApplication
        count = CompanyApplication.objects.filter(status='pending').count()
    except Exception:
        count = 0
    return {'pending_applications_count': count}


def total_notifications_count(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'total_notifications_count': 0}

    total = 0
    company = _get_effective_company(request)
    role = _get_user_role_in_company(user, company) if company else getattr(user, 'role', '')

    # 1. Unread Messages
    if role in ('company_admin', 'admin', 'manager', 'company_manager', 'super_admin') or _is_super_admin(user):
        try:
            from apps.companies.models import ContactMessage
            if company:
                total += ContactMessage.objects.filter(company=company, is_read=False).count()
            else:
                total += ContactMessage.objects.filter(company__isnull=True, is_read=False).count()
        except Exception:
            pass

    # 2. Pending Orders
    if company and role in ('company_admin', 'admin', 'manager', 'company_manager', 'super_admin'):
        try:
            from apps.cart_orders.models import Order
            total += Order.objects.filter(company=company, status='new').count()
        except Exception:
            pass

    # 3. Low Stock
    if company and role in ('company_admin', 'admin', 'stock_controller', 'super_admin'):
        try:
            from apps.epa_shop.models import Phone, Electronic, Accessory
            from django.db.models import Count, Q
            low_phones = Phone.objects.filter(company=company, is_active=True).annotate(
                avail=Count('units', filter=Q(units__status='available'))
            ).filter(avail__lte=5).count()
            low_electronics = Electronic.objects.filter(company=company, is_active=True).annotate(
                avail=Count('units', filter=Q(units__status='available'))
            ).filter(avail__lte=5).count()
            low_accessories = Accessory.objects.filter(company=company, is_active=True, total_quantity_in_stock__lte=5).count()
            total += low_phones + low_electronics + low_accessories
        except Exception as e:
            print(f"Low stock error: {e}")

    # 4. Pending Join Requests
    if company and role in ('company_admin', 'admin', 'super_admin'):
        try:
            total += CompanyJoinRequest.objects.filter(company=company, status='pending').count()
        except Exception:
            pass

    # 5. Unverified Daily Records
    if company and role in ('company_admin', 'admin', 'super_admin'):
        try:
            from apps.treasury.models import DailyRecord
            total += DailyRecord.objects.filter(company=company, is_approved=False).count()
        except Exception:
            pass

    # 6. Pending Losses
    if company and role in ('company_admin', 'admin', 'super_admin'):
        try:
            from apps.losses.models import LossReturn
            total += LossReturn.objects.filter(company=company, is_verified=False).count()
        except Exception:
            pass

    # 7. System-level (Super Admin on main domain)
    if _is_super_admin(user) and not company:
        try:
            from apps.accounts.models import User
            from django.utils import timezone
            from datetime import datetime
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            last_seen_iso = request.session.get('users_last_seen')
            if last_seen_iso:
                try:
                    last_seen = datetime.fromisoformat(last_seen_iso)
                    if timezone.is_naive(last_seen):
                        last_seen = timezone.make_aware(last_seen)
                    cutoff = max(last_seen, today_start)
                except (ValueError, TypeError):
                    cutoff = today_start
            else:
                cutoff = today_start
            total += User.objects.filter(created_at__gte=cutoff).count()
        except Exception:
            pass
        try:
            from apps.companies.models import CompanyApplication
            total += CompanyApplication.objects.filter(status='pending').count()
        except Exception:
            pass

    return {'total_notifications_count': total}