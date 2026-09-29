# apps/companies/middleware.py

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.http import Http404


# ============================================
# PATHS THAT BYPASS CUSTOM-DOMAIN RESOLUTION
# ============================================
BYPASS_DOMAIN_PREFIXES = (
    '/payments/',        # KCB / M-Pesa callbacks + payment UI
    '/admin/',           # Django admin
    '/static/',          # static assets
    '/media/',           # user-uploaded media
    '/auth/',            # login / logout / register / password reset
    '/api/support/',     # support-mode API
    '/subscription-expired/',
    '/plans/',           # plans list (super admin)
)


# ============================================
# PLATFORM HOSTS (never treated as tenant domains)
# ============================================
PLATFORM_HOSTS = frozenset({
    'ronosystems.com',
    'www.ronosystems.com',
    'ronosystems.onrender.com',
    'localhost',
    '127.0.0.1',
})

PLATFORM_HOST_SUFFIXES = (
    '.onrender.com',
)


# ============================================
# CSRF TRUSTED ORIGINS — runtime cache
# ============================================
# Custom domains arrive at runtime and can't be pre-listed in settings.
# We append them to CSRF_TRUSTED_ORIGINS lazily. This set avoids re-scanning
# the full list on every request (which is what `if origin not in list` does).
_RUNTIME_TRUSTED_ORIGINS = set()


def _trust_csrf_origin(origin: str) -> None:
    """Register `origin` as a trusted CSRF origin (idempotent, cached)."""
    if origin in _RUNTIME_TRUSTED_ORIGINS:
        return
    if origin not in settings.CSRF_TRUSTED_ORIGINS:
        settings.CSRF_TRUSTED_ORIGINS.append(origin)
    _RUNTIME_TRUSTED_ORIGINS.add(origin)


class CustomDomainMiddleware:
    """
    Resolves the tenant Company from the request's Host header when a
    custom domain is being used.

    - Sets `request.company` AND `request.tenant_company` to the matched
      Company (or None).
    - Runs BEFORE SubscriptionExpiryMiddleware.
    - Skips lookup for:
        * platform hosts (localhost, 127.0.0.1, *.onrender.com, ronosystems.com)
        * explicitly bypassed paths (webhooks, admin, static, auth, ...)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()

        # ------------------------------------------------------------
        # BYPASS 1: Paths that never resolve a tenant company
        # ------------------------------------------------------------
        # Critical for webhooks (KCB / M-Pesa callbacks) which arrive at
        # arbitrary hosts (ngrok, Render) that may not be registered as a
        # custom_domain on any Company.
        if any(request.path_info.startswith(p) for p in BYPASS_DOMAIN_PREFIXES):
            request.company = None
            request.tenant_company = None
            return self.get_response(request)

        # ------------------------------------------------------------
        # BYPASS 2: Platform's own hosts
        # ------------------------------------------------------------
        if host in PLATFORM_HOSTS or host.endswith(PLATFORM_HOST_SUFFIXES):
            request.company = None
            request.tenant_company = None
            return self.get_response(request)

        # ------------------------------------------------------------
        # Resolve company by custom domain
        # ------------------------------------------------------------
        # `find_by_domain` normalizes `host` (strips www., protocols, ports)
        # and only returns is_active=True companies.
        # `require_verified=True` means unverified domains 404 — flip to
        # False if you want super admins to be able to preview DNS-pending
        # domains from the settings UI.
        from apps.companies.models import Company

        company = Company.find_by_domain(host, require_verified=True)

        if company is None:
            # No tenant for this hostname. 404 rather than redirect — we
            # don't want to leak which domains are (or aren't) registered.
            raise Http404("No company registered for this domain.")

        request.company = company
        request.tenant_company = company

        # Trust this domain for CSRF on this and future requests.
        # Django doesn't support wildcards in CSRF_TRUSTED_ORIGINS.
        _trust_csrf_origin(f"https://{host}")
        _trust_csrf_origin(f"http://{host}")

        return self.get_response(request)


# ============================================
# URL names that remain accessible when subscription is expired
# ============================================
EXEMPT_URL_NAMES = {
    'login',
    'logout',
    'register',
    'forgot-password',
    'reset-password',
    'subscription-expired',
    'company-payments',
    'company-payments-initiate',
    'company-payments-status',
    'company-payments-callback',
    'company-payments-dev-confirm',
    'kcb-callback',
    'mpesa-callback',
}


# ============================================
# Path prefixes that bypass subscription-expiry check
# ============================================
EXEMPT_URL_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/auth/',
    '/api/support/',
    '/subscription-expired/',
    '/payments/',        # covers /payments/kcb/callback/
    '/plans/',
    '/companies/',
)


class SubscriptionExpiryMiddleware:
    """
    Blocks requests from users whose company subscription has expired.

    Exemptions:
      - Anonymous users
      - Superusers
      - Support-mode sessions (super admin impersonating a company)
      - Users with no company attached
      - Exempt URL prefixes (admin, static, media, auth, support API, payments)
      - Exempt URL names (login, logout, expired page, payment endpoints, callbacks)
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

        # Resolve current company.
        # Prefer custom-domain-resolved company, then support-mode company,
        # then the user's own company.
        company = (
            getattr(request, 'company', None)
            or getattr(request, 'tenant_company', None)
            or getattr(request.user, 'company', None)
        )
        if company is None:
            return self.get_response(request)

        allowed, reason = company.can_access_system()

        if not allowed:
            # Lazy auto-expire: flip status once, so admin list shows reality
            try:
                company.mark_subscription_expired()
            except Exception:
                pass

            messages.error(request, reason)
            try:
                return redirect('subscription-expired')
            except NoReverseMatch:
                return redirect('/subscription-expired/')

        return self.get_response(request)