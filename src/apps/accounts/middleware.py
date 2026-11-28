import time
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
# apps/accounts/middleware.py
from django.contrib.auth.views import redirect_to_login
from django.urls import resolve, Resolver404

PUBLIC_PREFIXES = (
    '/auth/',
    '/admin/',
    '/api/',
    '/accounts/',
    '/static/',
    '/media/',
    '/subscription-expired/',
    '/payments/',
    '/plans/',
    '/contact/', '/about/', '/features/', '/pricing/',   # public marketing pages
    '/manifest.json', '/sw.js', '/favicon.ico',
)

PUBLIC_PATHS = (
    '/',
)

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path_info
            if path in PUBLIC_PATHS:
                return self.get_response(request)
            if not any(path.startswith(p) for p in PUBLIC_PREFIXES):
                try:
                    resolve(path)
                    return redirect_to_login(request.get_full_path())
                except Resolver404:
                    pass
        return self.get_response(request)

class InactivityLogoutMiddleware:
    """
    Logs out a user after INACTIVITY_TIMEOUT_SECONDS of no requests.
    Works alongside SESSION_COOKIE_AGE + SESSION_SAVE_EVERY_REQUEST.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, 'INACTIVITY_TIMEOUT_SECONDS', 1800)

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last_activity = request.session.get('_last_activity')

            if last_activity and (now - last_activity) > self.timeout:
                logout(request)
                request.session.flush()
                login_url = reverse('account_login')
                return redirect(f'{login_url}?next={request.path}')

            request.session['_last_activity'] = now
            request.session.modified = True

        return self.get_response(request)