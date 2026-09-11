# apps/companies/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages


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
        company = getattr(request.user, 'company', None)
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