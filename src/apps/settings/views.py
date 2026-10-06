import time
import cloudinary
import cloudinary.uploader
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings as django_settings
from django.views.decorators.http import require_http_methods
from apps.plans.models import Subscription
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

    # --- Payment: core ---
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

    # --- Payment: M-Pesa STK ---
    {'key': 'PAYMENT_MPESA_STK_ENABLED', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable M-Pesa STK Push', 'default': True, 'order': 10,
     'help_text': 'Automatic STK push. Disable if KCB/STK is not live yet.'},

    # --- Payment: Buy Goods (Till) ---
    {'key': 'PAYMENT_BUY_GOODS_ENABLED', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable Buy Goods (Till)', 'default': False, 'order': 11},
    {'key': 'PAYMENT_BUY_GOODS_TILL', 'type': 'text', 'category': 'payment',
     'label': 'Buy Goods Till Number', 'default': '', 'order': 12,
     'help_text': 'e.g. 123456'},
    {'key': 'PAYMENT_BUY_GOODS_NAME', 'type': 'text', 'category': 'payment',
     'label': 'Buy Goods Business Name', 'default': '', 'order': 13,
     'help_text': 'Shown to the customer so they know who they are paying.'},

    # --- Payment: Paybill ---
    {'key': 'PAYMENT_PAYBILL_ENABLED', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable Paybill', 'default': False, 'order': 14},
    {'key': 'PAYMENT_PAYBILL_NUMBER', 'type': 'text', 'category': 'payment',
     'label': 'Paybill Number', 'default': '', 'order': 15,
     'help_text': 'e.g. 522522'},
    {'key': 'PAYMENT_PAYBILL_ACCOUNT', 'type': 'text', 'category': 'payment',
     'label': 'Paybill Account Number', 'default': '', 'order': 16,
     'help_text': 'Usually the company ID / invoice number. Use {company_id} to auto-fill.'},
    {'key': 'PAYMENT_PAYBILL_NAME', 'type': 'text', 'category': 'payment',
     'label': 'Paybill Business Name', 'default': '', 'order': 17},

    # --- Payment: Send Money ---
    {'key': 'PAYMENT_SEND_MONEY_ENABLED', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable Send Money (Phone)', 'default': False, 'order': 18},
    {'key': 'PAYMENT_SEND_MONEY_PHONE', 'type': 'text', 'category': 'payment',
     'label': 'Send Money Phone Number', 'default': '', 'order': 19,
     'help_text': 'e.g. 0712345678'},
    {'key': 'PAYMENT_SEND_MONEY_NAME', 'type': 'text', 'category': 'payment',
     'label': 'Send Money Recipient Name', 'default': '', 'order': 20},

    # --- Payment: Bank Transfer ---
    {'key': 'PAYMENT_BANK_ENABLED', 'type': 'boolean', 'category': 'payment',
     'label': 'Enable Bank Transfer', 'default': False, 'order': 21},
    {'key': 'PAYMENT_BANK_NAME', 'type': 'text', 'category': 'payment',
     'label': 'Bank Name', 'default': '', 'order': 22},
    {'key': 'PAYMENT_BANK_ACCOUNT_NAME', 'type': 'text', 'category': 'payment',
     'label': 'Bank Account Name', 'default': '', 'order': 23},
    {'key': 'PAYMENT_BANK_ACCOUNT_NUMBER', 'type': 'text', 'category': 'payment',
     'label': 'Bank Account Number', 'default': '', 'order': 24},
    {'key': 'PAYMENT_BANK_BRANCH', 'type': 'text', 'category': 'payment',
     'label': 'Bank Branch', 'default': '', 'order': 25},
    {'key': 'PAYMENT_BANK_SWIFT', 'type': 'text', 'category': 'payment',
     'label': 'SWIFT / Bank Code', 'default': '', 'order': 26},

    # --- Payment: instructions ---
    {'key': 'PAYMENT_MANUAL_INSTRUCTIONS', 'type': 'textarea', 'category': 'payment',
     'label': 'Manual Payment Instructions', 'default': '', 'order': 27,
     'help_text': 'Shown below the manual payment options.'},

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
    """Convert a Python value into the string form we store in `SystemSetting.value`."""
    if t == 'boolean':
        return 'true' if value else 'false'
    if value is None:
        return ''
    return str(value)


def _ensure_schema_rows():
    """Make sure every key in SETTINGS_SCHEMA exists as a SystemSetting row."""
    for spec in SETTINGS_SCHEMA:
        obj, created = SystemSetting.objects.get_or_create(
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

        if not created:
            changed = False
            if obj.options != spec.get('options', []):
                obj.options = spec.get('options', [])
                changed = True
            if obj.label != spec.get('label', spec['key']):
                obj.label = spec.get('label', spec['key'])
                changed = True
            if obj.help_text != spec.get('help_text', ''):
                obj.help_text = spec.get('help_text', '')
                changed = True
            if obj.setting_type != spec['type']:
                obj.setting_type = spec['type']
                changed = True
            if changed:
                obj.save()


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
    Upload to Cloudinary with a unique public_id per upload:
        settings/<key>_<timestamp>
    Returns the public_id Cloudinary used.
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


def _pending_manual_payments_count():
    """Number of manual payments awaiting verification."""
    try:
        return (
            Subscription.objects
            .filter(status='pending')
            .exclude(payment_method__in=['', 'mpesa', 'stk'])
            .count()
        )
    except Exception:
        return 0


# ======================================================================
# Views
# ======================================================================
@login_required
@user_passes_test(_is_admin)
def settings_dashboard(request):
    """Render the System Settings dashboard with all categories and pending payment count."""
    _ensure_schema_rows()

    # ---------- Build the categories dict from the schema ----------
    categories = {}
    for spec in SETTINGS_SCHEMA:
        cat = spec['category']
        categories.setdefault(cat, [])

        try:
            obj = SystemSetting.objects.get(key=spec['key'])
        except SystemSetting.DoesNotExist:
            continue

        categories[cat].append({
            'key':       obj.key,
            'label':     obj.label or obj.key,
            'type':      obj.setting_type,
            'value':     obj.value,
            'url':       obj.get_url(),
            'help_text': obj.help_text,
            'required':  obj.is_required,
            'options':   obj.options or [],
        })

    # ---------- Pending manual payments (for the notification badge) ----------
    pending_payments_count = _pending_manual_payments_count()

    return render(request, 'superadmin/settings.html', {
        'categories':             categories,
        'category_labels':        dict(SystemSetting.CATEGORIES),
        'pending_payments_count': pending_payments_count,
    })


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def settings_update(request):
    """
    Save changes to SystemSetting rows.

    Important nuance:
    - A ticked HTML checkbox posts `name=on`.
    - An UNticked checkbox posts NOTHING.

    So boolean keys must be handled by iterating over the SCHEMA — not over
    `request.POST` — otherwise unticking a box is a silent no-op.
    """
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

    # ---------- 3) Booleans: iterate over SCHEMA, not over POST ----------
    # This is the key fix: an unticked checkbox is missing from request.POST,
    # so we must ask the schema which boolean keys to check and write 'false'
    # for any that are not present as 'on' in the request.
    for spec in SETTINGS_SCHEMA:
        if spec['type'] != 'boolean':
            continue

        key = spec['key']

        # Skip if this key had a file upload this round (unlikely for booleans
        # but harmless to guard)
        if key in uploaded_keys or key in request.FILES:
            continue

        try:
            obj = SystemSetting.objects.get(key=key)
        except SystemSetting.DoesNotExist:
            continue

        # The browser sends `key=on` when ticked, nothing when unticked.
        new_val = 'true' if request.POST.get(key) == 'on' else 'false'

        if obj.value != new_val:
            obj.value = new_val
            obj.save(update_fields=['value'])
            updated += 1

    # ---------- 4) Non-boolean plain values: iterate over POST ----------
    for key, raw in request.POST.items():
        if key == 'csrfmiddlewaretoken' or key.startswith('remove_'):
            continue

        try:
            obj = SystemSetting.objects.get(key=key)
        except SystemSetting.DoesNotExist:
            continue

        # Skip uploads and booleans (handled above)
        if obj.setting_type in ('image', 'video', 'boolean'):
            continue

        val = raw.strip() if isinstance(raw, str) else raw

        if obj.setting_type == 'integer':
            try:
                new_val = str(int(val or 0))
            except (TypeError, ValueError):
                new_val = '0'
        elif obj.setting_type == 'float':
            try:
                new_val = str(float(val or 0))
            except (TypeError, ValueError):
                new_val = '0'
        else:
            new_val = val

        if obj.value != new_val:
            obj.value = new_val
            obj.save(update_fields=['value'])
            updated += 1

    # ---------- 5) User feedback ----------
    if errors:
        for e in errors:
            messages.error(request, f'Upload failed — {e}')
    if updated:
        messages.success(
            request,
            f'Saved ({updated} change{"s" if updated != 1 else ""}).'
        )
    elif not errors:
        messages.info(request, 'No changes.')

    return redirect('settings:dashboard')


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def settings_reset_category(request):
    """Reset every setting in a given category to its schema default."""
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
        obj.save(update_fields=['value'])
        count += 1

    messages.success(request, f'Reset {count} setting(s) in "{category}".')
    return redirect('settings:dashboard')