import os
import re
import cloudinary
import cloudinary.uploader
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings as django_settings
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .models import SystemSetting


# ----------------------------------------------------------------------
# Schema — which settings exist, their type, category, and defaults.
# ----------------------------------------------------------------------
SETTINGS_SCHEMA = [
    # --- General ---
    {'key': 'SITE_NAME', 'type': 'text', 'category': 'general', 'label': 'Site Name',
     'default': 'RonoSystems', 'required': True, 'order': 1},
    {'key': 'SITE_TAGLINE', 'type': 'text', 'category': 'general', 'label': 'Tagline',
     'default': 'Enterprise Management Platform', 'order': 2},
    {'key': 'TIMEZONE', 'type': 'select', 'category': 'general', 'label': 'Timezone',
     'default': 'Africa/Nairobi', 'order': 3,
     'options': [
         {'value': 'UTC', 'label': 'UTC'},
         {'value': 'Africa/Nairobi', 'label': 'Africa/Nairobi'},
         {'value': 'America/New_York', 'label': 'America/New_York'},
         {'value': 'Europe/London', 'label': 'Europe/London'},
         {'value': 'Asia/Dubai', 'label': 'Asia/Dubai'},
     ]},
    {'key': 'DATE_FORMAT', 'type': 'select', 'category': 'general', 'label': 'Date Format',
     'default': 'Y-m-d', 'order': 4,
     'options': [
         {'value': 'Y-m-d', 'label': 'YYYY-MM-DD'},
         {'value': 'd/m/Y', 'label': 'DD/MM/YYYY'},
         {'value': 'm/d/Y', 'label': 'MM/DD/YYYY'},
         {'value': 'd M Y', 'label': 'DD Mon YYYY'},
     ]},
    {'key': 'ITEMS_PER_PAGE', 'type': 'select', 'category': 'general', 'label': 'Items Per Page',
     'default': '25', 'order': 5,
     'options': [
         {'value': '10', 'label': '10'},
         {'value': '25', 'label': '25'},
         {'value': '50', 'label': '50'},
         {'value': '100', 'label': '100'},
     ]},

    # --- Branding ---
    {'key': 'PRIMARY_COLOR', 'type': 'color', 'category': 'branding', 'label': 'Primary Color',
     'default': '#036a77', 'order': 1},
    {'key': 'SECONDARY_COLOR', 'type': 'color', 'category': 'branding', 'label': 'Secondary Color',
     'default': '#00b4d8', 'order': 2},
    {'key': 'SITE_LOGO', 'type': 'image', 'category': 'branding', 'label': 'Site Logo',
     'default': '', 'order': 3,
     'help_text': 'Recommended 200×60px. PNG or JPG.'},
    {'key': 'SITE_FAVICON', 'type': 'image', 'category': 'branding', 'label': 'Favicon',
     'default': '', 'order': 4,
     'help_text': 'Recommended 32×32px. PNG.'},
    {'key': 'LOGIN_BACKGROUND', 'type': 'image', 'category': 'branding', 'label': 'Login Background',
     'default': '', 'order': 5,
     'help_text': 'Recommended 1920×1080px. JPG or AVIF.'},

    # --- Email ---
    {'key': 'EMAIL_HOST', 'type': 'text', 'category': 'email', 'label': 'SMTP Host',
     'default': 'smtp.gmail.com', 'order': 1},
    {'key': 'EMAIL_PORT', 'type': 'integer', 'category': 'email', 'label': 'SMTP Port',
     'default': '587', 'order': 2},
    {'key': 'EMAIL_USERNAME', 'type': 'text', 'category': 'email', 'label': 'SMTP Username',
     'default': '', 'order': 3},
    {'key': 'EMAIL_PASSWORD', 'type': 'password', 'category': 'email', 'label': 'SMTP Password',
     'default': '', 'order': 4},
    {'key': 'EMAIL_FROM', 'type': 'email', 'category': 'email', 'label': 'From Email',
     'default': 'noreply@example.com', 'order': 5},
    {'key': 'EMAIL_TLS', 'type': 'boolean', 'category': 'email', 'label': 'Enable TLS',
     'default': True, 'order': 6},

    # --- Payment ---
    {'key': 'CURRENCY', 'type': 'select', 'category': 'payment', 'label': 'Default Currency',
     'default': 'KES', 'order': 1,
     'options': [
         {'value': 'KES', 'label': 'Kenyan Shilling (KES)'},
         {'value': 'USD', 'label': 'US Dollar (USD)'},
         {'value': 'EUR', 'label': 'Euro (EUR)'},
         {'value': 'GBP', 'label': 'British Pound (GBP)'},
     ]},
    {'key': 'CURRENCY_SYMBOL', 'type': 'text', 'category': 'payment', 'label': 'Currency Symbol',
     'default': 'KSh', 'order': 2},
    {'key': 'TAX_RATE', 'type': 'float', 'category': 'payment', 'label': 'Tax Rate (%)',
     'default': '0', 'order': 3},
    {'key': 'ENABLE_DISCOUNT', 'type': 'boolean', 'category': 'payment', 'label': 'Enable Discounts',
     'default': True, 'order': 4},
    {'key': 'ENABLE_TAX', 'type': 'boolean', 'category': 'payment', 'label': 'Enable Tax',
     'default': False, 'order': 5},

    # --- Preferences ---
    {'key': 'NOTIFICATIONS', 'type': 'boolean', 'category': 'preferences', 'label': 'Notifications',
     'default': True, 'order': 1},
    {'key': 'EMAIL_NOTIFICATIONS', 'type': 'boolean', 'category': 'preferences', 'label': 'Email Notifications',
     'default': True, 'order': 2},
    {'key': 'PUSH_NOTIFICATIONS', 'type': 'boolean', 'category': 'preferences', 'label': 'Push Notifications',
     'default': False, 'order': 3},
]


def _ensure_schema_rows():
    """Create any missing SystemSetting rows for keys in SETTINGS_SCHEMA."""
    for spec in SETTINGS_SCHEMA:
        defaults = {
            'value': _stringify(spec['default'], spec['type']),
            'setting_type': spec['type'],
            'category': spec['category'],
            'label': spec.get('label', spec['key']),
            'description': spec.get('description', ''),
            'help_text': spec.get('help_text', ''),
            'order': spec.get('order', 0),
            'is_required': spec.get('required', False),
            'options': spec.get('options', []),
        }
        SystemSetting.objects.get_or_create(key=spec['key'], defaults=defaults)


def _stringify(value, setting_type):
    if setting_type == 'boolean':
        return 'true' if value else 'false'
    if value is None:
        return ''
    return str(value)


def _is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _sanitize_filename(raw_name, fallback='upload'):
    """
    Turn an arbitrary filename into a safe basename.
    Handles pathological cases where the browser sends a full path or URL.
    """
    if not raw_name:
        return fallback
    base = os.path.basename(str(raw_name).replace('\\', '/'))
    base = re.sub(r'[:*?"<>|]+', '_', base)
    stem, ext = os.path.splitext(base)
    stem = slugify(stem) or 'file'
    ext = ext.lower()
    return f'{stem}{ext}'


def _cloudinary_config():
    """Return the Cloudinary config dict from Django settings."""
    return getattr(django_settings, 'CLOUDINARY_STORAGE', {})


def _upload_to_cloudinary(file_obj, key):
    """
    Upload a file to Cloudinary under 'settings/<setting-key>'.

    Returns the storage key (e.g. 'settings/site-logo') on success,
    or raises on failure.

    We bypass django-cloudinary-storage entirely because its save() and url()
    methods produce inconsistent keys and incomplete URLs.
    """
    cfg = _cloudinary_config()

    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )

    # Use the setting key as the public ID — deterministic and stable.
    # e.g. SITE_LOGO → "settings/site-logo"
    prefix = key.lower().replace('_', '-')
    public_id = f'settings/{prefix}'

    result = cloudinary.uploader.upload(
        file_obj,
        public_id=public_id,
        overwrite=True,
        resource_type='image',
        invalidate=True,
    )

    returned_id = result.get('public_id', public_id)
    return returned_id


@login_required
@user_passes_test(_is_admin)
def settings_dashboard(request):
    """GET: render the settings form."""
    _ensure_schema_rows()

    categories = {}
    for spec in SETTINGS_SCHEMA:
        cat = spec['category']
        categories.setdefault(cat, [])
        try:
            setting = SystemSetting.objects.get(key=spec['key'])
        except SystemSetting.DoesNotExist:
            continue

        categories[cat].append({
            'key': setting.key,
            'label': setting.label or spec['key'],
            'type': setting.setting_type,
            'value': setting.value,
            'url': setting.get_url(),
            'help_text': setting.help_text,
            'required': setting.is_required,
            'options': setting.options or [],
        })

    category_labels = dict(SystemSetting.CATEGORIES)

    context = {
        'categories': categories,
        'category_labels': category_labels,
        'page_title': 'System Settings',
        'page_subtitle': 'Configure your system preferences',
    }
    return render(request, 'superadmin/settings.html', context)


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def settings_update(request):
    """POST: apply changes from the form."""
    _ensure_schema_rows()

    updated = 0
    upload_errors = []

    # ---- 1) Handle uploaded files (direct Cloudinary upload) ----
    for key, file_obj in request.FILES.items():
        try:
            setting = SystemSetting.objects.get(key=key)
        except SystemSetting.DoesNotExist:
            continue

        if setting.setting_type not in ('image', 'file'):
            continue

        try:
            storage_key = _upload_to_cloudinary(file_obj, key)
        except Exception as e:
            upload_errors.append(f'{key}: {e}')
            continue

        setting.value = storage_key
        setting.save()
        updated += 1

    # ---- 2) Handle removals (only when the user actually clicked Remove) ----
    for key in list(request.POST.keys()):
        if not key.startswith('remove_'):
            continue
        real_key = key[len('remove_'):]

        # The hidden field only has a value when the Remove button was clicked.
        # Empty value = the user did NOT ask to remove this image.
        if not request.POST.get(key):
            continue

        try:
            setting = SystemSetting.objects.get(key=real_key)
        except SystemSetting.DoesNotExist:
            continue

        if setting.setting_type in ('image', 'file'):
            setting.delete_file()
            setting.value = ''
            setting.save()
            updated += 1

    # ---- 3) Handle plain values (only count actual changes) ----
    for key, raw in request.POST.items():
        if key == 'csrfmiddlewaretoken' or key.startswith('remove_'):
            continue
        try:
            setting = SystemSetting.objects.get(key=key)
        except SystemSetting.DoesNotExist:
            continue
        if setting.setting_type in ('image', 'file'):
            continue

        value = raw.strip() if isinstance(raw, str) else raw

        if setting.setting_type == 'boolean':
            new_value = 'true' if raw == 'on' else 'false'
        elif setting.setting_type == 'integer':
            try:
                new_value = str(int(value or 0))
            except ValueError:
                new_value = '0'
        elif setting.setting_type == 'float':
            try:
                new_value = str(float(value or 0))
            except ValueError:
                new_value = '0'
        else:
            new_value = value

        if setting.value != new_value:
            setting.value = new_value
            setting.save()
            updated += 1

    if upload_errors:
        for err in upload_errors:
            messages.error(request, f'Upload failed — {err}')

    if updated:
        messages.success(request, f'Settings saved ({updated} changed).')
    elif not upload_errors:
        messages.info(request, 'No changes were made.')

    return redirect('settings:dashboard')


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def settings_reset_category(request):
    """POST: reset every setting in a category to its default."""
    category = request.POST.get('category')
    if not category:
        messages.error(request, 'No category specified.')
        return redirect('settings:dashboard')

    count = 0
    for spec in SETTINGS_SCHEMA:
        if spec['category'] != category:
            continue
        try:
            setting = SystemSetting.objects.get(key=spec['key'])
        except SystemSetting.DoesNotExist:
            continue
        if setting.setting_type in ('image', 'file'):
            setting.delete_file()
        setting.value = _stringify(spec['default'], spec['type'])
        setting.save()
        count += 1

    messages.success(request, f'Reset {count} setting(s) in "{category}".')
    return redirect('settings:dashboard')