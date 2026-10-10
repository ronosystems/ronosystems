import logging
import threading

from django.conf import settings

from .utils import get_client_ip, maybe_hash_ip, parse_user_agent, lookup_geo

logger = logging.getLogger(__name__)

# URL prefixes to skip — visits to these are NOT logged.
SKIP_PREFIXES = (
    '/static/',
    '/media/',
    '/admin/',
    '/analytics/',        # skips the whole analytics dashboard (incl. sub-pages)
    '/favicon.ico',
    '/robots.txt',
    '/healthz',
    '/ping',
)


def _should_track(request):
    if request.method != 'GET':
        return False
    path = request.path
    for prefix in SKIP_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def _write_visit(ip_raw, path, full_path, method, user_agent, referrer,
                 session_key, user_id, user_name, user_email):
    try:
        from .models import Visit
        ip_for_storage = maybe_hash_ip(ip_raw)
        country, country_code, city = lookup_geo(ip_raw)
        device, device_type, browser, browser_version, os_family = parse_user_agent(user_agent)

        user_obj = None
        if user_id:
            try:
                from django.contrib.auth import get_user_model
                user_obj = get_user_model().objects.filter(pk=user_id).first()
            except Exception:
                pass

        Visit.objects.create(
            ip_address=ip_for_storage,
            country=country, country_code=country_code, city=city,
            page=path[:500], full_path=full_path[:1000], method=method,
            referrer=(referrer or '')[:1000],
            user_agent=user_agent or '',
            device=device[:100], device_type=device_type,
            browser=browser[:100], browser_version=browser_version[:50],
            os=os_family[:100],
            session_key=session_key or '',
            user=user_obj,
            user_name=(user_name or '')[:200],
            user_email=(user_email or '')[:254],
        )
    except Exception as e:
        logger.exception('Failed to write Visit row: %s', e)


class VisitTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        should = _should_track(request) and getattr(settings, 'VISIT_TRACKING_ENABLED', True)

        if should:
            try:
                ip = get_client_ip(request)
                if not request.session.session_key:
                    request.session.create()
                session_key = request.session.session_key or ''

                user_id = user_name = user_email = None
                if request.user.is_authenticated:
                    user_id = request.user.pk
                    try:
                        user_name = request.user.get_full_name() or request.user.username
                    except Exception:
                        user_name = getattr(request.user, 'username', '')
                    user_email = getattr(request.user, 'email', '') or ''

                t = threading.Thread(
                    target=_write_visit,
                    kwargs={
                        'ip_raw': ip,
                        'path': request.path,
                        'full_path': request.get_full_path(),
                        'method': request.method,
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'referrer': request.META.get('HTTP_REFERER', ''),
                        'session_key': session_key,
                        'user_id': user_id,
                        'user_name': user_name,
                        'user_email': user_email,
                    },
                    daemon=True,
                )
                t.start()
            except Exception as e:
                logger.exception('Tracking setup failed: %s', e)

        return self.get_response(request)