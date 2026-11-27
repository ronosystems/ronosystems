# apps/companies/middleware.py

from django.conf import settings
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import NoReverseMatch
from django.contrib import messages

from apps.accounts.models import Membership
from apps.companies.models import Company


# ============================================================
# CONSTANTS
# ============================================================
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

PLATFORM_HOSTS = frozenset({
    'ronosystems.com',
    'www.ronosystems.com',
    'ronosystems.onrender.com',
    'www.ronosystems.onrender.com',
    'localhost',
    '127.0.0.1',
})

PLATFORM_ROOTS = (
    'ronosystems.com',
    'ronosystems.onrender.com',
    'localhost',
)

# Runtime CSRF cache
_RUNTIME_TRUSTED_ORIGINS = set()


def _trust_csrf_origin(origin: str) -> None:
    if origin in _RUNTIME_TRUSTED_ORIGINS:
        return
    try:
        if origin not in settings.CSRF_TRUSTED_ORIGINS:
            settings.CSRF_TRUSTED_ORIGINS.append(origin)
    except Exception:
        pass
    _RUNTIME_TRUSTED_ORIGINS.add(origin)


# ============================================================
# TENANT RESOLVER (the ONLY TenantMiddleware)
# ============================================================
class TenantMiddleware:
    """
    Resolves request.company / request.tenant from the Host header.
    Runs FIRST. Also enforces per-tenant membership access.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()

        # Defaults — always set so downstream middleware/views don't crash
        request.tenant = None
        request.company = None
        request.tenant_company = None
        request.current_company = None

        # Bypass 1 — paths that never resolve a tenant
        if any(request.path_info.startswith(p) for p in BYPASS_DOMAIN_PREFIXES):
            return self.get_response(request)

        # Bypass 2 — platform's own hosts (ronosystems.com, localhost, etc.)
        if host in PLATFORM_HOSTS:
            return self.get_response(request)

        # ---------- Resolve company by domain / subdomain ----------
        is_local_test = host.endswith('.localhost')
        lookup_host = host.replace('.localhost', '') if is_local_test else host

        company = Company.find_by_domain(
            lookup_host, require_verified=not is_local_test,
        )

        # Fallback 1: local dev subdomain (fieldmax.localhost)
        if company is None and is_local_test:
            company = (
                Company.objects.filter(subdomain=lookup_host, is_active=True).first()
                or Company.objects.filter(name__iexact=lookup_host, is_active=True).first()
            )

        # Fallback 2: platform subdomain (kalwal.ronosystems.com)
        if company is None and not is_local_test:
            for root in PLATFORM_ROOTS:
                if root == 'localhost':
                    continue
                suffix = '.' + root
                if lookup_host.endswith(suffix):
                    sub = lookup_host[:-len(suffix)].split('.')[0]
                    company = Company.objects.filter(subdomain=sub, is_active=True).first()
                    if company:
                        break

        # No company → 404 (except auth paths on unknown domains)
        if company is None:
            if request.path_info.startswith('/auth/') or request.path_info.startswith('/accounts/'):
                return self.get_response(request)
            raise Http404(f"No company registered for this domain: {host}")

        # ---------- Attach tenant to request ----------
        request.tenant = company
        request.company = company
        request.tenant_company = company
        request.current_company = company
        try:
            request.session['current_tenant_id'] = company.id
        except Exception:
            pass

        # Trust CSRF for this host
        _trust_csrf_origin(f"https://{host}")
        _trust_csrf_origin(f"http://{host}")

        # ---------- Membership enforcement ----------
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.is_superuser:
            # Support mode bypass
            if request.session.get('support_mode'):
                return self.get_response(request)

            # FIX: field is `company`, not `tenant`; state is `is_active`, not `status`
            has_access = Membership.objects.filter(
                user=user, company=company, is_active=True,
            ).exists()

            if not has_access:
                legacy_company = getattr(user, 'company', None)
                if legacy_company and legacy_company.id == company.id:
                    has_access = True

            if not has_access:
                return HttpResponseForbidden(
                    "You don't belong to this business. "
                    f"Go to your own domain. You are trying to access {company.name}."
                )

        return self.get_response(request)


# Alias for older settings
CustomDomainMiddleware = TenantMiddleware


# ============================================================
# ACTIVE MEMBERSHIP
# ============================================================
class ActiveMembershipMiddleware:
    """
    Resolves request.membership for the current user.

    Priority:
      1. Already attached (by JWT auth class)
      2. Session value (active_membership_id)
      3. request.company match (tenant)
      4. Primary membership
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, 'membership'):
            request.membership = None

        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return self.get_response(request)

        membership = getattr(request, 'membership', None)

        # Session
        if membership is None:
            mid = request.session.get('active_membership_id')
            if mid:
                membership = (
                    Membership.objects
                    .select_related('company', 'branch')
                    .filter(pk=mid, user=user, is_active=True)
                    .first()
                )

        # Tenant match
        if membership is None and getattr(request, 'company', None):
            membership = user.get_membership_for_company(request.company)

        # Primary
        if membership is None:
            membership = user.get_primary_membership()

        request.membership = membership
        return self.get_response(request)


# ============================================================
# SUBSCRIPTION EXPIRY
# ============================================================
EXEMPT_URL_NAMES = {
    'login', 'logout', 'register', 'forgot-password', 'reset-password',
    'subscription-expired',
    'company-payments', 'company-payments-initiate', 'company-payments-status',
    'company-payments-callback', 'company-payments-dev-confirm',
    'kcb-callback', 'mpesa-callback',
}

EXEMPT_URL_PREFIXES = (
    '/admin/', '/static/', '/media/', '/auth/', '/accounts/',
    '/api/support/', '/subscription-expired/',
    '/payments/', '/plans/',
)


class SubscriptionExpiryMiddleware:
    """
    Blocks requests from users whose company subscription has expired.
    Uses request.tenant (set by TenantMiddleware) — NOT user.company.
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

        if request.session.get('support_mode') or request.session.get('viewing_company_id'):
            return self.get_response(request)

        try:
            match = request.resolver_match
            if match and match.url_name in EXEMPT_URL_NAMES:
                return self.get_response(request)
        except Exception:
            pass

        company = (
            getattr(request, 'tenant', None)
            or getattr(request, 'company', None)
            or getattr(request, 'tenant_company', None)
        )
        if company is None:
            return self.get_response(request)

        try:
            allowed, reason = company.can_access_system()
        except Exception:
            # If the method is missing, don't block the whole app
            return self.get_response(request)

        if not allowed:
            try:
                company.mark_subscription_expired()
            except Exception:
                pass

            messages.error(
                request,
                "Your subscription has expired. Please renew to regain access.",
            )
            try:
                return redirect('subscription-expired')
            except NoReverseMatch:
                return redirect('/subscription-expired/')

        return self.get_response(request)