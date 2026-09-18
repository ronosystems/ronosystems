import time
import cloudinary
import cloudinary.uploader
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings as django_settings
from django.views.decorators.http import require_http_methods

from .models import SystemSetting


# ======================================================================
# SCHEMA — one entry per setting
# ======================================================================
SETTINGS_SCHEMA = [
    # --- General ---
    {'key': 'SITE_NAME', 'type': 'text', 'category': 'general',
     'label': 'Site Name', 'default': 'RonoSystems', 'required': True, 'order': 1},
    {'key': 'SITE_TAGLINE', 'type': 'text', 'category': 'general',
     'label': 'Tagline', 'default': 'Enterprise Management Platform', 'order': 2},
    {'key': 'TIMEZONE', 'type': 'select', 'category': 'general',
     'label': 'Timezone', 'default': 'Africa/Nairobi', 'order': 3,
     'options': [
         {'value': 'UTC', 'label': 'UTC'},
         {'value': 'Africa/Nairobi', 'label': 'Africa/Nairobi'},
         {'value': 'America/New_York', 'label': 'America/New_York'},
         {'value': 'Europe/London', 'label': 'Europe/London'},
         {'value': 'Asia/Dubai', 'label': 'Asia/Dubai'},
     ]},
    {'key': 'DATE_FORMAT', 'type': 'select', 'category': 'general',
     'label': 'Date Format', 'default': 'Y-m-d', 'order': 4,
     'options': [
         {'value': 'Y-m-d', 'label': 'YYYY-MM-DD'},
         {'value': 'd/m/Y', 'label': 'DD/MM/YYYY'},
         {'value': 'm/d/Y', 'label': 'MM/DD/YYYY'},
         {'value': 'd M Y', 'label': 'DD Mon YYYY'},
     ]},
    {'key': 'ITEMS_PER_PAGE', 'type': 'select', 'category': 'general',
     'label': 'Items Per Page', 'default': '25', 'order': 5,
     'options': [
         {'value': '10', 'label': '10'},
         {'value': '25', 'label': '25'},
         {'value': '50', 'label': '50'},
         {'value': '100', 'label': '100'},
     ]},

    # --- Branding ---
    {'key': 'PRIMARY_COLOR', 'type': 'color', 'category': 'branding',
     'label': 'Primary Color', 'default': '#036a77', 'order': 1},
    {'key': 'SECONDARY_COLOR', 'type': 'color', 'category': 'branding',
     'label': 'Secondary Color', 'default': '#00b4d8', 'order': 2},
    {'key': 'SITE_LOGO', 'type': 'image', 'category': 'branding',
     'label': 'Site Logo', 'default': '', 'order': 3,
     'help_text': 'Recommended 200×60px. PNG or JPG.'},
    {'key': 'SITE_FAVICON', 'type': 'image', 'category': 'branding',
     'label': 'Favicon', 'default': '', 'order': 4,
     'help_text': 'Recommended 32×32px. PNG.'},
    {'key': 'LOGIN_BACKGROUND', 'type': 'image', 'category': 'branding',
     'label': 'Login Background', 'default': '', 'order': 5,
     'help_text': 'Recommended 1920×1080px. JPG.'},
    {'key': 'LANDING_VIDEO', 'type': 'video', 'category': 'branding',
     'label': 'Landing Video', 'default': '', 'order': 6,
     'help_text': 'MP4 or WebM, up to 50MB. Plays inline on the landing page.'},
    {'key': 'LANDING_VIDEO_POSTER', 'type': 'image', 'category': 'branding',
     'label': 'Video Thumbnail', 'default': '', 'order': 7,
     'help_text': 'Optional. Shown before the video plays. 1280×720px.'},

    # --- Email ---
    {'key': 'EMAIL_HOST', 'type': 'text', 'category': 'email',
     'label': 'SMTP Host', 'default': 'smtp.gmail.com', 'order': 1},
    {'key': 'EMAIL_PORT', 'type': 'integer', 'category': 'email',
     'label': 'SMTP Port', 'default': '587', 'order': 2},
    {'key': 'EMAIL_USERNAME', 'type': 'text', 'category': 'email',
     'label': 'SMTP Username', 'default': '', 'order': 3},
    {'key': 'EMAIL_PASSWORD', 'type': 'password', 'category': 'email',
     'label': 'SMTP Password', 'default': '', 'order': 4},
    {'key': 'EMAIL_FROM', 'type': 'email', 'category': 'email',
     'label': 'From Email', 'default': 'noreply@example.com', 'order': 5},
    {'key': 'EMAIL_TLS', 'type': 'boolean', 'category': 'email',
     'label': 'Enable TLS', 'default': True, 'order': 6},

    # --- Payment ---
    {'key': 'CURRENCY', 'type': 'select', 'category': 'payment',
     'label': 'Default Currency', 'default': 'KES', 'order': 1,
     'options': [
         {'value': 'KES', 'label': 'Kenyan Shilling (KES)'},
         {'value': 'USD', 'label': 'US Dollar (USD)'},
         {'value': 'EUR', 'label': 'Euro (EUR)'},
         {'value': 'GBP', 'label': 'British Pound (GBP)'},
     ]},
    {'key': 'CURRENCY_SYMBOL', 'type': 'text', 'category': 'payment',
     'label': 'Currency Symbol', 'default': 'KSh', 'order': 2},
    {'key': 'TAX_RATE', 'type': 'float', 'category': 'payment',
     'label': 'Tax Rate (%)', 'default': '0', 'order': 3},
    {'key': 'ENABLE_DISCOUNT', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable Discounts', 'default': True, 'order': 4},
    {'key': 'ENABLE_TAX', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable Tax', 'default': False, 'order': 5},

    # --- Preferences ---
    {'key': 'NOTIFICATIONS', 'type': 'boolean', 'category': 'preferences',
     'label': 'Notifications', 'default': True, 'order': 1},
    {'key': 'EMAIL_NOTIFICATIONS', 'type': 'boolean', 'category': 'preferences',
     'label': 'Email Notifications', 'default': True, 'order': 2},
    {'key': 'PUSH_NOTIFICATIONS', 'type': 'boolean', 'category': 'preferences',
     'label': 'Push Notifications', 'default': False, 'order': 3},
]


# ======================================================================
# Helpers
# ======================================================================
def _is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _stringify(value, t):
    if t == 'boolean':
        return 'true' if value else 'false'
    if value is None:
        return ''
    return str(value)


def _ensure_schema_rows():
    for spec in SETTINGS_SCHEMA:
        SystemSetting.objects.get_or_create(
            key=spec['key'],
            defaults={
                'value': _stringify(spec['default'], spec['type']),
                'setting_type': spec['type'],
                'category': spec['category'],
                'label': spec.get('label', spec['key']),
                'help_text': spec.get('help_text', ''),
                'order': spec.get('order', 0),
                'is_required': spec.get('required', False),
                'options': spec.get('options', []),
            },
        )


def _cloudinary():
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def _upload_media(file_obj, setting_key, resource_type='image'):
    """
    Upload to Cloudinary with a UNIQUE public_id per upload:
        settings/<key>_<timestamp>

    Why unique: Cloudinary's CDN caches by public_id. With a fixed
    public_id + overwrite=True, replacing an image/video serves the
    OLD cached version even though the new file is uploaded. A unique
    public_id makes every upload a brand-new asset → CDN never serves
    stale content.

    Returns the public_id Cloudinary used (e.g. 'settings/site_logo_1789754321').
    """
    _cloudinary()
    key_lower = setting_key.lower()
    public_id = f"settings/{key_lower}_{int(time.time())}"

    result = cloudinary.uploader.upload(
        file_obj,
        public_id=public_id,
        overwrite=False,
        resource_type=resource_type,
    )
    return result.get('public_id') or public_id


def _delete_media(public_id, resource_type='image'):
    """Delete a Cloudinary asset by its exact public_id. Silent on failure."""
    if not public_id:
        return
    try:
        _cloudinary()
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception:
        pass


# ======================================================================
# Views
# ======================================================================
@login_required
@user_passes_test(_is_admin)
def settings_dashboard(request):
    _ensure_schema_rows()

    categories = {}
    for spec in SETTINGS_SCHEMA:
        cat = spec['category']
        categories.setdefault(cat, [])
        try:
            obj = SystemSetting.objects.get(key=spec['key'])
        except SystemSetting.DoesNotExist:
            continue
        categories[cat].append({
            'key': obj.key,
            'label': obj.label or obj.key,
            'type': obj.setting_type,
            'value': obj.value,
            'url': obj.get_url(),
            'help_text': obj.help_text,
            'required': obj.is_required,
            'options': obj.options or [],
        })

    return render(request, 'superadmin/settings.html', {
        'categories': categories,
        'category_labels': dict(SystemSetting.CATEGORIES),
    })


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def settings_update(request):
    _ensure_schema_rows()

    updated = 0
    errors = []
    uploaded_keys = set()

    # ---------- 1) Uploads: one file at a time, one setting at a time ----------
    for key, file_obj in request.FILES.items():
        try:
            obj = SystemSetting.objects.get(key=key)
        except SystemSetting.DoesNotExist:
            continue
        if obj.setting_type not in ('image', 'video'):
            continue

        resource_type = 'video' if obj.setting_type == 'video' else 'image'

        try:
            new_value = _upload_media(file_obj, key, resource_type=resource_type)
        except Exception as e:
            errors.append(f'{key}: {e}')
            continue

        old_value = obj.value
        obj.value = new_value
        obj.save()
        uploaded_keys.add(key)
        updated += 1

        # Delete the previous asset if it was a different one
        if old_value and old_value != new_value:
            _delete_media(old_value, resource_type=resource_type)

    # ---------- 2) Removals: only for keys with no upload in this request ----------
    for post_key in list(request.POST.keys()):
        if not post_key.startswith('remove_'):
            continue
        real_key = post_key[len('remove_'):]
        if not request.POST.get(post_key):
            continue
        if real_key in uploaded_keys or real_key in request.FILES:
            continue

        try:
            obj = SystemSetting.objects.get(key=real_key)
        except SystemSetting.DoesNotExist:
            continue
        if obj.setting_type not in ('image', 'video'):
            continue

        resource_type = 'video' if obj.setting_type == 'video' else 'image'
        old = obj.value
        obj.value = ''
        obj.save()
        if old:
            _delete_media(old, resource_type=resource_type)
        updated += 1

    # ---------- 3) Plain values ----------
    for key, raw in request.POST.items():
        if key == 'csrfmiddlewaretoken' or key.startswith('remove_'):
            continue
        try:
            obj = SystemSetting.objects.get(key=key)
        except SystemSetting.DoesNotExist:
            continue
        if obj.setting_type in ('image', 'video'):
            continue

        val = raw.strip() if isinstance(raw, str) else raw

        if obj.setting_type == 'boolean':
            new_val = 'true' if raw == 'on' else 'false'
        elif obj.setting_type == 'integer':
            try:
                new_val = str(int(val or 0))
            except ValueError:
                new_val = '0'
        elif obj.setting_type == 'float':
            try:
                new_val = str(float(val or 0))
            except ValueError:
                new_val = '0'
        else:
            new_val = val

        if obj.value != new_val:
            obj.value = new_val
            obj.save()
            updated += 1

    if errors:
        for e in errors:
            messages.error(request, f'Upload failed — {e}')
    if updated:
        messages.success(request, f'Saved ({updated} change{"s" if updated != 1 else ""}).')
    elif not errors:
        messages.info(request, 'No changes.')

    return redirect('settings:dashboard')


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def settings_reset_category(request):
    category = request.POST.get('category')
    if not category:
        messages.error(request, 'No category specified.')
        return redirect('settings:dashboard')

    count = 0
    for spec in SETTINGS_SCHEMA:
        if spec['category'] != category:
            continue
        try:
            obj = SystemSetting.objects.get(key=spec['key'])
        except SystemSetting.DoesNotExist:
            continue

        if obj.setting_type in ('image', 'video') and obj.value:
            resource_type = 'video' if obj.setting_type == 'video' else 'image'
            _delete_media(obj.value, resource_type=resource_type)

        obj.value = _stringify(spec['default'], spec['type'])
        obj.save()
        count += 1

    messages.success(request, f'Reset {count} setting(s) in "{category}".')
    return redirect('settings:dashboard')