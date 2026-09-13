# apps/companies/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.http import Http404


class CustomDomainMiddleware:
    """
    Resolves Company from the request's Host header when a custom
    domain is being used.

    - Sets `request.tenant_company` to the matched Company (or None).
    - Runs BEFORE SubscriptionExpiryMiddleware.
    - Skips lookup for the platform's own hosts.
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

        # Skip lookup for platform's own hosts
        if host in self.platform_hosts or host.endswith('.onrender.com'):
            request.tenant_company = None
            return self.get_response(request)

        # Look up company by custom domain
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


# URL names that remain accessible even when the subscription is expired
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
}

# Path prefixes that bypass the check entirely
EXEMPT_URL_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/auth/',
    '/api/support/',
    '/subscription-expired/',
    '/payments/',
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
      - Exempt URL prefixes (admin, static, media, auth, support API)
      - Exempt URL names (login, logout, expired page, etc.)
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

        if request.session.get('support_company_id'):
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
                # Fallback: plain URL if name isn't registered
                return redirect('/subscription-expired/')

        return self.get_response(request)