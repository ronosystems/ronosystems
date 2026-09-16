# apps/companies/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.http import Http404


# ============================================
# PATHS THAT BYPASS CUSTOM-DOMAIN RESOLUTION
# ============================================
# Requests to these paths never need a tenant company resolved from
# the Host header. This keeps webhooks (KCB, M-Pesa), admin, static
# files, auth flows, and the payments UI reachable from any host —
# including ngrok tunnels, Render preview URLs, and platform domains.
#
# IMPORTANT: keep this in sync with EXEMPT_URL_PREFIXES below.
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


class CustomDomainMiddleware:
    """
    Resolves Company from the request's Host header when a custom
    domain is being used.

    - Sets `request.tenant_company` to the matched Company (or None).
    - Runs BEFORE SubscriptionExpiryMiddleware.
    - Skips lookup for:
        * platform hosts (localhost, 127.0.0.1, *.onrender.com)
        * explicitly bypassed paths (webhooks, admin, static, auth, ...)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.platform_hosts = {
            'ronosystems.onrender.com',
            'localhost',
            '127.0.0.1',
        }

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()

        # ------------------------------------------------------------
        # BYPASS 1: Explicit paths that never resolve a tenant company
        # ------------------------------------------------------------
        # This is critical for webhooks (KCB / M-Pesa callbacks) which
        # arrive at arbitrary hosts (ngrok, Render) that may not be
        # registered as a custom_domain on any Company.
        if any(request.path_info.startswith(p) for p in BYPASS_DOMAIN_PREFIXES):
            request.tenant_company = None
            return self.get_response(request)

        # ------------------------------------------------------------
        # BYPASS 2: Platform's own hosts
        # ------------------------------------------------------------
        if host in self.platform_hosts or host.endswith('.onrender.com'):
            request.tenant_company = None
            return self.get_response(request)

        # ------------------------------------------------------------
        # Resolve company by custom domain
        # ------------------------------------------------------------
        from apps.companies.models import Company
        try:
            company = Company.objects.get(
                custom_domain__iexact=host,
                domain_verified=True,
            )
            request.tenant_company = company

            # Trust this custom domain for CSRF on this request.
            # Django doesn't support wildcards in CSRF_TRUSTED_ORIGINS,
            # so we add it dynamically.
            from django.conf import settings
            origin = f"https://{host}"
            if origin not in settings.CSRF_TRUSTED_ORIGINS:
                settings.CSRF_TRUSTED_ORIGINS.append(origin)

        except Company.DoesNotExist:
            raise Http404("No company registered for this domain.")

        return self.get_response(request)


# ============================================
# URL names that remain accessible even when the subscription is expired
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
# Path prefixes that bypass the subscription-expiry check entirely
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
        # ---------- Path-based exemptions ----------
        path = request.path_info
        if any(path.startswith(p) for p in EXEMPT_URL_PREFIXES):
            return self.get_response(request)

        # ---------- Auth exemptions ----------
        if not request.user.is_authenticated:
            return self.get_response(request)

        if request.user.is_superuser:
            return self.get_response(request)

        # ---------- Support-mode exemptions ----------
        if request.session.get('support_mode') or request.session.get('viewing_company_id'):
            return self.get_response(request)

        # ---------- Name-based exemptions ----------
        try:
            match = request.resolver_match
            if match and match.url_name in EXEMPT_URL_NAMES:
                return self.get_response(request)
        except Exception:
            pass

        # ---------- Resolve current company ----------
        # Prefer the custom-domain-resolved company, fall back to user's company.
        company = (
            getattr(request, 'tenant_company', None)
            or getattr(request.user, 'company', None)
        )
        if company is None:
            return self.get_response(request)

        # ---------- Access check ----------
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