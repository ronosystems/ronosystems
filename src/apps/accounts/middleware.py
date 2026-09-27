import time
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


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