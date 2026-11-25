from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch
from django.contrib import messages
from django.http import Http404, HttpResponseForbidden

# ============================================
# PATHS THAT BYPASS TENANT RESOLUTION
# ============================================
BYPASS_DOMAIN_PREFIXES = (
    '/payments/',
    '/mpesa/',
    '/admin/',
    '/static/',
    '/media/',
    '/api/support/',
    '/subscription-expired/',
    '/plans/',
)

# ============================================
# PLATFORM HOSTS (never treated as tenant domains)
# ============================================
PLATFORM_HOSTS = frozenset({
    'ronosystems.com',
    'www.ronosystems.com',
    'ronosystems.onrender.com',
    'www.ronosystems.onrender.com',
    'localhost',
    '127.0.0.1',
})

# Hizi TU ndio platform roots. Subdomain ya hizi ndio tenant.
# 'kalyet.ronosystems.com' -> tenant
# 'ronosystems.onrender.com' -> platform (iko kwenye PLATFORM_HOSTS)
PLATFORM_ROOTS = (
    'ronosystems.com',
    'ronosystems.onrender.com',
    'localhost',
)

# ============================================
# CSRF TRUSTED ORIGINS — runtime cache
# ============================================
_RUNTIME_TRUSTED_ORIGINS = set()

def _trust_csrf_origin(origin: str) -> None:
    if origin in _RUNTIME_TRUSTED_ORIGINS:
        return
    if origin not in settings.CSRF_TRUSTED_ORIGINS:
        settings.CSRF_TRUSTED_ORIGINS.append(origin)
    _RUNTIME_TRUSTED_ORIGINS.add(origin)

class CustomDomainMiddleware:
    """
    THE tenant resolver. Runs first.
    Reads Host -> finds Company via Company.find_by_domain()
    Sets: request.tenant, request.company (alias), request.tenant_company (alias)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()

        # Default: no tenant
        request.tenant = None
        request.company = None
        request.tenant_company = None
        request.current_company = None

        # ------------------------------------------------------------
        # BYPASS 1: Paths that never resolve a tenant
        # ------------------------------------------------------------
        if any(request.path_info.startswith(p) for p in BYPASS_DOMAIN_PREFIXES):
            return self.get_response(request)

        # ------------------------------------------------------------
        # BYPASS 2: Platform's own hosts - ronosystems.com, localhost
        # ------------------------------------------------------------
        if host in PLATFORM_HOSTS:
            return self.get_response(request)

        # ------------------------------------------------------------
        # Resolve company by domain / subdomain
        # ------------------------------------------------------------
        from apps.companies.models import Company

        # Local testing: kalyet.localhost -> kalyet
        is_local_test = host.endswith('.localhost')
        lookup_host = host.replace('.localhost', '') if is_local_test else host

        # Hii ndio inashughulikia zote:
        # 1. kalyet.co.ke (custom_domain)
        # 2. kalyet.ronosystems.com (subdomain)
        # 3. kalyet.ronosystems.onrender.com (staging subdomain)
        company = Company.find_by_domain(lookup_host, require_verified=not is_local_test)

        # ===== FIX: FALLBACK KWA SUBDOMAIN (LOCAL TESTING) =====
        # Company haina field 'slug', ina 'subdomain'
        # fieldmax.localhost -> lookup_host = 'fieldmax'
        # find_by_domain('fieldmax') -> None (kwa sababu custom_domain ni fieldmax.shop)
        # Kwa hiyo jaribu subdomain moja kwa moja
        if company is None and is_local_test:
            company = Company.objects.filter(subdomain=lookup_host).first()
            if company is None:
                company = Company.objects.filter(name__iexact=lookup_host).first()
        # ===== MWISHO WA FIX =====

        # ===== FIX 2: FALLBACK KWA PLATFORM SUBDOMAIN =====
        # kalyet.ronosystems.com -> lookup_host = kalyet.ronosystems.com
        # Kama find_by_domain imeshindwa, jaribu kuchukua subdomain
        # kabla ya '.' ya kwanza na kutafuta kwa subdomain
        if company is None and not is_local_test:
            # Kama ni subdomain ya platform root
            for root in PLATFORM_ROOTS:
                if root == 'localhost':
                    continue
                suffix = '.' + root
                if lookup_host.endswith(suffix):
                    sub = lookup_host[:-len(suffix)]  # kalyet
                    # Kama bado kuna dot, ni subdomain ya subdomain - chukua ya kwanza
                    sub = sub.split('.')[0]
                    company = Company.objects.filter(subdomain=sub).first()
                    if company:
                        break
        # ===== MWISHO WA FIX 2 =====

        # KAMA HAKUNA COMPANY - USI-FALLBACK KWA name__icontains (ni security hole)
        # Kama host ni subdomain ya platform lakini company haipo -> 404
        # Kama host ni custom domain isiyojulikana -> 404
        if company is None:
            # Kama ni subdomain ya platform lakini haipo, onyesha 404 safi
            is_platform_subdomain = any(
                lookup_host.endswith('.' + root) for root in PLATFORM_ROOTS
            )
            # Kwa local test, fieldmax.localhost pia ni platform subdomain
            if is_local_test:
                is_platform_subdomain = True
            if is_platform_subdomain:
                raise Http404(f"No company registered for this domain: {host}")
            # Custom domain isiyojulikana - pia 404, usimpeleke kwa company nyingine
            # Ila kwa paths kama /auth/ kwenye domain isiyojulikana, turuhusu
            # login page ya platform ionekane badala ya kuvunja
            if request.path_info.startswith('/auth/'):
                return self.get_response(request)
            raise Http404(f"No company registered for this domain: {host}")

        # Tenant amepatikana
        request.tenant = company
        request.company = company
        request.tenant_company = company
        request.current_company = company
        # Session kwa ajili ya code ya zamani inayosoma session
        request.session['current_tenant_id'] = company.id

        # Trust CSRF
        _trust_csrf_origin(f"https://{host}")
        _trust_csrf_origin(f"http://{host}")

        # ------------------------------------------------------------
        # SECURITY: Kama user amelogin, ana Membership kwenye hii tenant?
        # ------------------------------------------------------------
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.is_superuser:
            # Support mode - super admin anaangalia company
            if request.session.get('support_mode'):
                return self.get_response(request)
            # Check membership
            try:
                has_access = user.memberships.filter(tenant=company, status='active').exists()
                # Fallback kwa code ya zamani: kama user bado ana user.company
                if not has_access:
                    legacy_company = getattr(user, 'company', None)
                    if legacy_company and legacy_company.id == company.id:
                        has_access = True
                if not has_access:
                    # Ana-try kuingia kwenye biashara si yake
                    return HttpResponseForbidden(
                        "You don't belong to this business. "
                        f"Go to your own domain. You are trying to access {company.name}."
                    )
            except Exception:
                # Kama membership table bado haija-migrate, usivunje request
                pass

        return self.get_response(request)

# Alias - ili settings zako za zamani zenye 'TenantMiddleware' zifanye kazi
TenantMiddleware = CustomDomainMiddleware

# ============================================
# URL names that remain accessible when subscription is expired
# ============================================
EXEMPT_URL_NAMES = {
    'login', 'logout', 'register', 'forgot-password', 'reset-password',
    'subscription-expired',
    'company-payments', 'company-payments-initiate', 'company-payments-status',
    'company-payments-callback', 'company-payments-dev-confirm',
    'kcb-callback', 'mpesa-callback',
}

EXEMPT_URL_PREFIXES = (
    '/admin/', '/static/', '/media/', '/auth/',
    '/api/support/', '/subscription-expired/',
    '/payments/', '/plans/',
)

class SubscriptionExpiryMiddleware:
    """
    Blocks requests from users whose company subscription has expired.
    Uses request.tenant (from CustomDomainMiddleware) - NOT user.company
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if any(path.startswith(p) for p in EXEMPT_URL_PREFIXES):
            return self.get_response(request)

        if not request.user.is_authenticated:
            return self.get_response(request)

        if request.user.is_superuser:
            return self.get_response(request)

        # Support-mode exemption
        if request.session.get('support_mode') or request.session.get('viewing_company_id'):
            return self.get_response(request)

        # Name-based exemptions
        try:
            match = request.resolver_match
            if match and match.url_name in EXEMPT_URL_NAMES:
                return self.get_response(request)
        except Exception:
            pass

        # Resolve company: PREFER request.tenant from CustomDomainMiddleware
        company = (
            getattr(request, 'tenant', None)
            or getattr(request, 'company', None)
            or getattr(request, 'tenant_company', None)
        )
        if company is None:
            # Kwenye main domain (ronosystems.com) hakuna tenant - ruhusu
            # User ataona list ya biashara zake
            return self.get_response(request)

        # FIXED: ulikuwa unaita can_access_system() mara 2
        allowed, reason = company.can_access_system()

        if not allowed:
            try:
                company.mark_subscription_expired()
            except Exception:
                pass

            messages.error(request, "Your subscription has expired. Please renew to regain access.")

            try:
                return redirect('subscription-expired')
            except NoReverseMatch:
                return redirect('/subscription-expired/')

        return self.get_response(request)