from .models import SystemSetting
from django.db import OperationalError, ProgrammingError


def pending_payments_count(request):
    """
    Expose the number of pending manual payments to every template.

    Only computes for authenticated staff/superadmin users, so tenants
    never trigger the query.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'pending_payments_count': 0}

    # Only staff / superusers see the badge
    if not (request.user.is_staff or request.user.is_superuser):
        return {'pending_payments_count': 0}

    try:
        from apps.plans.models import Subscription
        count = (
            Subscription.objects
            .filter(status='pending')
            .exclude(payment_method__in=['', 'mpesa', 'stk'])
            .count()
        )
    except (OperationalError, ProgrammingError):
        # Happens during initial migrations
        count = 0
    except Exception:
        count = 0

    return {'pending_payments_count': count}

def system_settings(request):
    """
    Expose a small, safe subset of settings to every template.

    Values returned are:
      - system_name                 : str
      - site_tagline                : str
      - primary_color               : str
      - secondary_color             : str
      - site_logo_url               : str or None
      - site_favicon_url            : str or None
      - login_background_url        : str or None
      - landing_video_url           : str or None   (NEW)
      - landing_video_poster_url    : str or None   (NEW)
      - system_settings             : dict (all keys → typed values)
    """

    def s(key, default=''):
        return SystemSetting.get_setting(key, default)

    def img(key):
        return SystemSetting.get_image_url(key)

    def video(key):
        return SystemSetting.get_video_url(key)

    return {
        # --- Branding text ---
        'system_name': s('SITE_NAME', 'RonoSystems'),
        'site_tagline': s('SITE_TAGLINE', ''),
        'primary_color': s('PRIMARY_COLOR', '#036a77'),
        'secondary_color': s('SECONDARY_COLOR', '#00b4d8'),

        # --- Branding images ---
        'site_logo_url': img('SITE_LOGO'),
        'site_favicon_url': img('SITE_FAVICON'),
        'login_background_url': img('LOGIN_BACKGROUND'),

        # --- Landing video (NEW) ---
        'landing_video_url': video('LANDING_VIDEO'),
        'landing_video_poster_url': img('LANDING_VIDEO_POSTER'),

        # --- Full settings dict for advanced template use ---
        'system_settings': SystemSetting.as_dict(),
    }