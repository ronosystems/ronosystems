"""
Context processors.

These run on every request and inject tenant-aware variables into every
template's context. All of them are defensive: if a company isn't set,
is anonymous, or a field is empty, they return safe defaults instead of
raising — templates should never crash because of a missing tenant.
"""

import os
from django.conf import settings
from django.db.models import F
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




# ============================================
# SYSTEM WEBSITE URL (for "Powered by" footer link)
# ============================================
def system_website_url(request):
    """
    URL of the system's own website homepage — never the tenant site.

    Resolution order:
      1. settings.SYSTEM_WEBSITE_URL  (explicit override, e.g. env var)
      2. settings.SYSTEM_DOMAIN       (e.g. "ronosystems.onrender.com")
      3. Strip a known tenant subdomain from the request host
         (e.g. fieldmax.localhost -> localhost,
               fieldmax.ronosystems.onrender.com -> ronosystems.onrender.com)
      4. Fall back to the request host as-is
    """
    explicit = (
        getattr(settings, 'SYSTEM_WEBSITE_URL', None)
        or os.getenv('SYSTEM_WEBSITE_URL', '')
    )
    if explicit:
        return {'system_website_url': explicit.rstrip('/') + '/'}

    full_host = request.get_host()             # includes port
    host, _, port = full_host.partition(':')
    host = host.lower()

    # --- 2. Explicit system domain ---
    system_domain = (
        getattr(settings, 'SYSTEM_DOMAIN', None)
        or os.getenv('SYSTEM_DOMAIN', '')
    )
    if system_domain:
        host = system_domain
    else:
        # --- 3. Strip tenant subdomain ---
        # Base domains we know are system roots — never strip below these
        SYSTEM_ROOTS = (
            'localhost',
            'ronosystems.onrender.com',
            'ronosystems.co.ke',
        )
        for root in SYSTEM_ROOTS:
            if host == root or host.endswith('.' + root):
                host = root
                break
        else:
            # Custom company domain (e.g. fieldmax.co.ke) → fall back to
            # the canonical system domain if configured, else leave as-is
            if settings.DEBUG:
                host = 'localhost'
            # In production, without SYSTEM_DOMAIN or SYSTEM_WEBSITE_URL set,
            # we can't know the system domain → leave the host unchanged.
            # Set SYSTEM_DOMAIN in prod to guarantee correct behaviour.

    scheme = 'https' if request.is_secure() else 'http'
    port_part = f':{port}' if port else ''
    return {'system_website_url': f'{scheme}://{host}{port_part}/'}


# ============================================
# UNREAD CONTACT MESSAGES (for navbar bell & notification center)
# ============================================
def unread_messages_count(request):
    """
    Inject the number of unread contact messages into every template context.
    Only runs for authenticated admins/managers.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'unread_messages_count': 0}

    # Check if the user has permission to see messages
    is_admin = user.is_superuser or getattr(user, 'role', '') in ('super_admin', 'company_admin', 'company_manager')
    if not is_admin:
        return {'unread_messages_count': 0}

    company = _get_effective_company(request)
    
    try:
        from apps.companies.models import ContactMessage
        
        if company:
            # Company domain: only their messages
            count = ContactMessage.objects.filter(company=company, is_read=False).count()
        else:
            # Super admin on the main site: ONLY system messages (company is NULL)
            count = ContactMessage.objects.filter(company__isnull=True, is_read=False).count()
            
    except Exception:
        count = 0

    return {'unread_messages_count': count}
    
    

def pending_applications_count(request):
    """
    Injects the count of pending company applications into every template context.
    Only visible to super admins.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'pending_applications_count': 0}

    role = getattr(user, 'role', '')
    if role != 'super_admin' and not user.is_staff:
        return {'pending_applications_count': 0}

    try:
        from apps.companies.models import CompanyApplication
        count = CompanyApplication.objects.filter(status='pending').count()
    except Exception:
        count = 0

    return {'pending_applications_count': count}



def total_notifications_count(request):
    """
    Combines all relevant notification counts into a single integer
    to display on the navbar bell.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'total_notifications_count': 0}

    total = 0
    company = _get_effective_company(request)
    role = getattr(user, 'role', '')

    # 1. Unread Messages (Fixed Isolation)
    if role in ('company_admin', 'company_manager', 'super_admin'):
        try:
            from apps.companies.models import ContactMessage
            if company:
                # Company domain: only their messages
                total += ContactMessage.objects.filter(company=company, is_read=False).count()
            else:
                # System domain: ONLY system messages (company is NULL)
                total += ContactMessage.objects.filter(company__isnull=True, is_read=False).count()
        except Exception:
            pass

    # 2. Pending Orders
    if company and role in ('company_admin', 'company_manager', 'super_admin'):
        try:
            from apps.cart_orders.models import Order
            total += Order.objects.filter(company=company, status='new').count()
        except ImportError:
            pass

    # 3. Low Stock (Bulletproof Context Processor)
    if company and role in ('company_admin', 'stock_controller', 'super_admin'):
        try:
            from apps.epa_shop.models import Phone, Electronic, Accessory, Unit
            
            count = 0
            
            # Check Live Units for Phones
            for item in Phone.objects.filter(company=company, is_active=True):
                if Unit.objects.filter(phone=item, status='available').count() <= 5:
                    count += 1
                    
            # Check Live Units for Electronics
            for item in Electronic.objects.filter(company=company, is_active=True):
                if Unit.objects.filter(electronic=item, status='available').count() <= 5:
                    count += 1
                    
            # Check Accessories
            for item in Accessory.objects.filter(company=company, is_active=True):
                if item.total_quantity_in_stock <= 5:
                    count += 1
                    
            total += count
        except Exception as e:
            print(f"Sidebar Low stock error: {e}")

    # 4. Pending Join Requests
    if company and role in ('company_admin', 'super_admin'):
        try:
            from apps.companies.models import CompanyJoinRequest
            total += CompanyJoinRequest.objects.filter(company=company, status='pending').count()
        except ImportError:
            pass

    # 5. Unverified Daily Records
    if company and role in ('company_admin', 'super_admin'):
        try:
            from apps.treasury.models import DailyRecord
            total += DailyRecord.objects.filter(company=company, is_approved=False).count()
        except ImportError:
            pass

    # 6. Pending Losses / Returns
    if company and role in ('company_admin', 'super_admin'):
        try:
            from apps.losses.models import LossReturn
            total += LossReturn.objects.filter(company=company, is_verified=False).count()
        except ImportError:
            pass

    # ==========================================
    # SYSTEM-LEVEL COUNTS (SUPER ADMIN ONLY)
    # ==========================================
    if role == 'super_admin' and not company:
        # 7. New Users
        try:
            from apps.accounts.models import User
            from datetime import datetime
            from django.utils import timezone
            
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
        except Exception as e:
            print(f"Users count error: {e}")

        # 8. Pending Company Applications
        try:
            from apps.companies.models import CompanyApplication
            total += CompanyApplication.objects.filter(status='pending').count()
        except Exception:
            pass

    return {'total_notifications_count': total}