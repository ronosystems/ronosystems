from .settings_data import get_settings, DEFAULT_SETTINGS
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
import os


def _resolve_image_url(image_path):
    """
    Turn a settings.json image value into a browser-usable URL.

    - Empty / None                     → None
    - Absolute URL (http/https///)     → unchanged
    - Anything else (relative path)    → MEDIA_URL + clean_path

    Deliberately does NOT check whether the file exists — that would
    trigger an HTTP roundtrip on Cloudinary per request and cause
    images to disappear silently if the check fails.
    """
    if not image_path:
        return None

    value = str(image_path).strip()

    # Already absolute
    if value.startswith(('http://', 'https://', '//')):
        return value

    # Strip a /media/ or media/ prefix if someone pasted one in
    clean = value
    if clean.startswith('/media/'):
        clean = clean[len('/media/'):]
    elif clean.startswith('media/'):
        clean = clean[len('media/'):]

    clean = clean.strip('/')

    media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
    # MEDIA_URL already ends with '/' in both local and Cloudinary setups
    return f"{media_url}{clean}"


def system_settings(request):
    """Add system settings to all templates."""

    settings_dict = get_settings()

    site_logo = settings_dict.get('SITE_LOGO', '')
    site_favicon = settings_dict.get('SITE_FAVICON', '')
    login_background = settings_dict.get('LOGIN_BACKGROUND', '')

    # Company logo (authenticated users)
    company_logo = None
    company_logo_url = None
    if request.user.is_authenticated:
        try:
            if hasattr(request.user, 'company') and request.user.company:
                company_logo_obj = getattr(request.user.company, 'logo', None)
                if company_logo_obj:
                    company_logo = company_logo_obj
                    if hasattr(company_logo_obj, 'url'):
                        company_logo_url = company_logo_obj.url
                    else:
                        company_logo_url = str(company_logo_obj)
        except Exception:
            pass

    # Storage type (informational)
    storage_backend = str(type(default_storage))
    if 'cloudinary' in storage_backend.lower():
        storage_type = 'cloudinary'
    elif 's3' in storage_backend.lower() or 'boto3' in storage_backend.lower():
        storage_type = 's3'
    else:
        storage_type = 'local'

    context = {
        # Site info
        'system_name': settings_dict.get('SITE_NAME', 'RonoSystems'),
        'site_tagline': settings_dict.get('SITE_TAGLINE', 'Enterprise Management Platform'),

        # Images — raw + resolved
        'site_logo': site_logo,
        'site_logo_url': _resolve_image_url(site_logo),
        'site_favicon': site_favicon,
        'site_favicon_url': _resolve_image_url(site_favicon),
        'login_background': login_background,
        'login_background_url': _resolve_image_url(login_background),

        # Company logo
        'company_logo': company_logo,
        'company_logo_url': company_logo_url,

        # Colors
        'primary_color': settings_dict.get('PRIMARY_COLOR', '#036a77'),
        'secondary_color': settings_dict.get('SECONDARY_COLOR', '#00b4d8'),

        # Full dict for templates that need it
        'system_settings': settings_dict,

        # Storage info
        'media_url': getattr(django_settings, 'MEDIA_URL', '/media/'),
        'storage_type': storage_type,
        'is_cloudinary': storage_type == 'cloudinary',
        'is_s3': storage_type == 's3',
        'is_local': storage_type == 'local',
    }

    if getattr(django_settings, 'DEBUG', False):
        context['storage_backend'] = storage_backend
        context['media_root'] = getattr(django_settings, 'MEDIA_ROOT', None)
        context['base_dir'] = getattr(django_settings, 'BASE_DIR', None)

    return context