from .models import SystemSetting


def system_settings(request):
    """
    Expose a small, safe subset of settings to every template.

    Values returned are:
      - system_name           : str
      - site_tagline          : str
      - primary_color         : str
      - secondary_color       : str
      - site_logo_url         : str or None
      - site_favicon_url      : str or None
      - login_background_url  : str or None
      - system_settings       : dict (all keys → typed values)
    """

    def s(key, default=''):
        return SystemSetting.get_setting(key, default)

    def img(key):
        return SystemSetting.get_image_url(key)

    return {
        'system_name': s('SITE_NAME', 'RonoSystems'),
        'site_tagline': s('SITE_TAGLINE', ''),
        'primary_color': s('PRIMARY_COLOR', '#036a77'),
        'secondary_color': s('SECONDARY_COLOR', '#00b4d8'),

        'site_logo_url': img('SITE_LOGO'),
        'site_favicon_url': img('SITE_FAVICON'),
        'login_background_url': img('LOGIN_BACKGROUND'),

        'system_settings': SystemSetting.as_dict(),
    }