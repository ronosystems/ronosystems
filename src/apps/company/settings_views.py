import os
import time
import json
import cloudinary
import cloudinary.uploader

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings as django_settings
from django.http import JsonResponse

from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)
from apps.companies.models import Company


# ============================================
# CLOUDINARY HELPERS
# ============================================
ALLOWED_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')


def _cloudinary_configure():
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def _upload_company_media(file_obj, company_id, field_name, resource_type='image'):
    """
    Upload a company media file to Cloudinary at a UNIQUE public_id:

        companies/<company_id>/<field_name>_<timestamp>

    Returns the public_id Cloudinary used.
    """
    _cloudinary_configure()
    public_id = f"companies/{company_id}/{field_name}_{int(time.time())}"

    result = cloudinary.uploader.upload(
        file_obj,
        public_id=public_id,
        overwrite=False,
        resource_type=resource_type,
    )
    return result.get('public_id') or public_id


def _delete_company_media(public_id, resource_type='image'):
    """Delete a Cloudinary asset by its exact public_id. Silent on failure."""
    if not public_id:
        return
    try:
        _cloudinary_configure()
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception:
        pass


def _current_public_id(field_value):
    """Extract the stored public_id from a Company media field value."""
    if not field_value:
        return ''
    key = getattr(field_value, 'name', None) or str(field_value)
    return key.strip().lstrip('/')


def _handle_media_upload(request, company, field_name, post_file_key):
    """
    Shared upload handler for logo, favicon, login_background, and receipt_logo.

    Returns True if an upload was processed, False otherwise.
    Raises ValueError with a user-facing message on invalid input.
    """
    file_obj = request.FILES.get(post_file_key)
    if not file_obj:
        return False

    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(
            'Invalid file format. Please upload JPG, PNG, GIF, SVG, or WEBP.'
        )

    old_public_id = _current_public_id(getattr(company, field_name, ''))

    try:
        new_public_id = _upload_company_media(
            file_obj,
            company.id or company.pk,
            field_name,
            resource_type='image',
        )
    except Exception as e:
        raise ValueError(f'{field_name.replace("_", " ").title()} upload failed: {e}')

    setattr(company, field_name, new_public_id)
    company.save(update_fields=[field_name])

    if old_public_id and old_public_id != new_public_id:
        _delete_company_media(old_public_id, resource_type='image')

    return True


def _handle_media_remove(request, company, field_name, post_remove_key):
    """
    Shared removal handler for logo, favicon, login_background, and receipt_logo.

    Returns True if a removal was processed, False otherwise.
    """
    if request.POST.get(post_remove_key) != 'true':
        return False

    old_public_id = _current_public_id(getattr(company, field_name, ''))
    if old_public_id:
        _delete_company_media(old_public_id, resource_type='image')

    setattr(company, field_name, '')
    company.save(update_fields=[field_name])
    return True


# ============================================
# DASHBOARD
# ============================================
@login_required
def settings_dashboard(request):
    """Company settings dashboard"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    settings_data = get_company_settings(company)

    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/settings/dashboard.html', context)


# ============================================
# COMPANY SETTINGS
# ============================================
@login_required
def settings_company(request):
    """Company settings — update company info, logo, favicon, login background, receipt logo"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            # ---------- 1) Media removals ----------
            removed_logo = _handle_media_remove(
                request, company, 'logo', 'remove_logo'
            )
            removed_favicon = _handle_media_remove(
                request, company, 'favicon', 'remove_favicon'
            )
            removed_bg = _handle_media_remove(
                request, company, 'login_background', 'remove_login_background'
            )
            removed_receipt_logo = _handle_media_remove(
                request, company, 'receipt_logo', 'remove_receipt_logo'
            )

            if removed_logo:
                messages.success(request, 'Company logo removed.')
            if removed_favicon:
                messages.success(request, 'Favicon removed.')
            if removed_bg:
                messages.success(request, 'Login background removed.')
            if removed_receipt_logo:
                messages.success(request, 'Receipt logo removed.')

            # ---------- 2) Media uploads ----------
            uploaded_logo = False
            uploaded_favicon = False
            uploaded_bg = False
            uploaded_receipt_logo = False

            try:
                if not removed_logo:
                    uploaded_logo = _handle_media_upload(
                        request, company, 'logo', 'company_logo'
                    )
                if not removed_favicon:
                    uploaded_favicon = _handle_media_upload(
                        request, company, 'favicon', 'company_favicon'
                    )
                if not removed_bg:
                    uploaded_bg = _handle_media_upload(
                        request, company, 'login_background',
                        'company_login_background'
                    )
                if not removed_receipt_logo:
                    uploaded_receipt_logo = _handle_media_upload(
                        request, company, 'receipt_logo',
                        'company_receipt_logo'
                    )
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('company-settings-company')

            if uploaded_logo:
                messages.success(request, 'Company logo updated.')
            if uploaded_favicon:
                messages.success(request, 'Favicon updated.')
            if uploaded_bg:
                messages.success(request, 'Login background updated.')
            if uploaded_receipt_logo:
                messages.success(request, 'Receipt logo updated.')

            # ---------- 3) Text fields ----------
            company_name = request.POST.get('company_name')
            company_email = request.POST.get('company_email')
            company_phone = request.POST.get('company_phone')
            company_address = request.POST.get('company_address')

            text_changed = False
            if company_name and company.name != company_name:
                company.name = company_name
                text_changed = True
            if company_email and company.email != company_email:
                company.email = company_email
                text_changed = True
            if company_phone and company.phone != company_phone:
                company.phone = company_phone
                text_changed = True
            if company_address and company.address != company_address:
                company.address = company_address
                text_changed = True

            if text_changed:
                company.save()

            # ---------- 4) JSON-backed settings ----------
            save_company_settings(company, request.POST)

            # ---------- 5) Final message ----------
            if not any([removed_logo, removed_favicon, removed_bg,
                        removed_receipt_logo,
                        uploaded_logo, uploaded_favicon, uploaded_bg,
                        uploaded_receipt_logo,
                        text_changed]):
                messages.info(request, 'No changes.')
            else:
                messages.success(request, 'Company settings updated successfully!')

            return redirect('company-settings-company')

        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')

    settings_data = get_company_settings(company)

    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'company',
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/settings/company.html', context)


# ============================================
# PAYMENT SETTINGS
# ============================================
@login_required
def settings_payment(request):
    """Payment settings — supports granular M-Pesa STK / Buy Goods / Paybill / Bank"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            payment_settings = {
                # ---------- Currency & Tax ----------
                'currency': request.POST.get('currency', 'KES'),
                'currency_symbol': request.POST.get('currency_symbol', 'KSh'),
                'decimal_places': int(request.POST.get('decimal_places', 2)),
                'payment_methods': request.POST.getlist('payment_methods'),

                'enable_discount': request.POST.get('enable_discount') == 'on',
                'enable_tax': request.POST.get('enable_tax') == 'on',
                'default_tax_rate': float(request.POST.get('default_tax_rate', 0)),

                # ---------- Credit & Terms ----------
                'enable_partial_payment': request.POST.get('enable_partial_payment') == 'on',
                'enable_credit': request.POST.get('enable_credit') == 'on',
                'credit_limit': float(request.POST.get('credit_limit', 0)),
                'payment_terms': int(request.POST.get('payment_terms', 30)),

                # ---------- M-Pesa STK Push ----------
                'enable_mpesa_stk': request.POST.get('enable_mpesa_stk') == 'on',
                'mpesa_stk_shortcode': request.POST.get('mpesa_stk_shortcode', ''),
                'mpesa_stk_passkey': request.POST.get('mpesa_stk_passkey', ''),

                # ---------- M-Pesa Buy Goods (Till) ----------
                'enable_buy_goods': request.POST.get('enable_buy_goods') == 'on',
                'buy_goods_till': request.POST.get('buy_goods_till', ''),
                'buy_goods_name': request.POST.get('buy_goods_name', ''),

                # ---------- M-Pesa Paybill ----------
                'enable_paybill': request.POST.get('enable_paybill') == 'on',
                'paybill_number': request.POST.get('paybill_number', ''),
                'paybill_account': request.POST.get('paybill_account', ''),
                'paybill_name': request.POST.get('paybill_name', ''),

                # ---------- Bank Transfer ----------
                'enable_bank': request.POST.get('enable_bank') == 'on',
                'bank_name': request.POST.get('bank_name', ''),
                'bank_account_name': request.POST.get('bank_account_name', ''),
                'bank_account': request.POST.get('bank_account', ''),
                'bank_branch': request.POST.get('bank_branch', ''),
                'bank_swift': request.POST.get('bank_swift', ''),

                # ---------- Legacy aliases (keep old code paths working) ----------
                # `enable_mpesa` is True if ANY M-Pesa variant is on
                'enable_mpesa': (
                    request.POST.get('enable_mpesa_stk') == 'on'
                    or request.POST.get('enable_buy_goods') == 'on'
                    or request.POST.get('enable_paybill') == 'on'
                ),
                # `mpesa_till` / `mpesa_paybill` mirror the new fields
                'mpesa_till': request.POST.get('buy_goods_till', ''),
                'mpesa_paybill': request.POST.get('paybill_number', ''),
            }

            save_company_settings(company, payment_settings, 'payment')
            messages.success(request, 'Payment settings updated successfully!')
            return redirect('company-settings-payment')

        except Exception as e:
            messages.error(request, f'Error updating payment settings: {str(e)}')

    settings_data = get_company_settings(company)

    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'payment',
        'is_viewing_company': is_viewing_company,
        'payment_methods_choices': [
            ('cash', 'Cash'),
            ('m-pesa', 'M-Pesa'),
            ('bank', 'Bank Transfer'),
            ('card', 'Card'),
            ('credit', 'Credit'),
        ],
    }
    return render(request, 'company/settings/payment.html', context)


# ============================================
# RECEIPT SETTINGS
# ============================================
@login_required
def settings_receipt(request):
    """Receipt settings"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            receipt_settings = {
                'receipt_header': request.POST.get('receipt_header', ''),
                'receipt_footer': request.POST.get('receipt_footer', ''),
                'receipt_format': request.POST.get('receipt_format', 'standard'),

                # ---- Master sections ----
                'show_logo':             request.POST.get('show_logo') == 'on',
                'show_company_details':  request.POST.get('show_company_details') == 'on',
                'show_customer_details': request.POST.get('show_customer_details') == 'on',
                'show_items':            request.POST.get('show_items') == 'on',
                'show_totals':           request.POST.get('show_totals') == 'on',
                'show_payment':          request.POST.get('show_payment') == 'on',
                'show_signature':        request.POST.get('show_signature') == 'on',

                # ---- Granular toggles ----
                'show_company_name':     request.POST.get('show_company_name') == 'on',
                'show_branch':           request.POST.get('show_branch') == 'on',
                'show_company_email':    request.POST.get('show_company_email') == 'on',
                'show_company_phone':    request.POST.get('show_company_phone') == 'on',
                'show_company_pin':      request.POST.get('show_company_pin') == 'on',
                'show_receipt_title':    request.POST.get('show_receipt_title') == 'on',
                'show_receipt_header':   request.POST.get('show_receipt_header') == 'on',
                'show_receipt_footer':   request.POST.get('show_receipt_footer') == 'on',
                'show_thank_you':        request.POST.get('show_thank_you') == 'on',
                'show_receipt_info':     request.POST.get('show_receipt_info') == 'on',
                'show_next_of_kin':      request.POST.get('show_next_of_kin') == 'on',
                'show_subtotal':         request.POST.get('show_subtotal') == 'on',
                'show_vat':              request.POST.get('show_vat') == 'on',
                'show_payment_method':   request.POST.get('show_payment_method') == 'on',
                'show_payment_status':   request.POST.get('show_payment_status') == 'on',
                'show_customer_phone':   request.POST.get('show_customer_phone') == 'on',
                'show_customer_id':      request.POST.get('show_customer_id') == 'on',
                'show_next_of_kin_phone': request.POST.get('show_next_of_kin_phone') == 'on',
                'receipt_title':         request.POST.get('receipt_title', 'RECEIPT'),
                'thank_you_message':     request.POST.get('thank_you_message', 'Thank you for your business!'),
                'include_barcode':       request.POST.get('include_barcode') == 'on',
                'print_copies':          int(request.POST.get('print_copies', 1)),
                'auto_print':            request.POST.get('auto_print') == 'on',
                'receipt_font_size':     request.POST.get('receipt_font_size', '14'),
                'receipt_width':         request.POST.get('receipt_width', '80'),
                'custom_css':            request.POST.get('custom_css', ''),
                'receipt_company_name':  request.POST.get('receipt_company_name', ''),
                'receipt_address':       request.POST.get('receipt_address', ''),
                'receipt_phone':         request.POST.get('receipt_phone', ''),
                'receipt_email':         request.POST.get('receipt_email', ''),
            }
            save_company_settings(company, receipt_settings, 'receipt')
            messages.success(request, 'Receipt settings updated successfully!')
            return redirect('company-settings-receipt')

        except Exception as e:
            messages.error(request, f'Error updating receipt settings: {str(e)}')

    settings_data = get_company_settings(company)

    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'receipt',
        'is_viewing_company': is_viewing_company,
        'receipt_formats': [
            ('standard', 'Standard'),
            ('mini', 'Mini Receipt'),
            ('detailed', 'Detailed'),
            ('invoice', 'Invoice Style'),
        ],
    }
    return render(request, 'company/settings/receipt.html', context)


# ============================================
# RECEIPT PREVIEW
# ============================================
@login_required
def settings_preview_receipt(request):
    """Preview receipt"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    settings_data = get_company_settings(company)

    receipt_data = {
        'receipt_number': 'RCP-2026-0001',
        'date': '2026-08-27 14:30',
        'customer': 'John Doe',
        'customer_phone': '+254712345678',
        'items': [
            {'name': 'Samsung Galaxy S24', 'qty': 1, 'price': 65000, 'total': 65000},
            {'name': 'Phone Case', 'qty': 2, 'price': 500, 'total': 1000},
            {'name': 'Screen Protector', 'qty': 1, 'price': 300, 'total': 300},
        ],
        'subtotal': 66300,
        'discount': 0,
        'tax': 0,
        'total': 66300,
        'payment_method': 'M-Pesa',
        'payment_status': 'Paid',
        'cashier': 'Admin',
    }

    # Build the effective email/phone/address to display in the preview,
    # preferring the receipt override, then the company value, then a dash.
    preview_email   = settings_data['receipt'].get('receipt_email')   or company.email   or '—'
    preview_phone   = settings_data['receipt'].get('receipt_phone')   or company.phone   or '—'
    preview_address = settings_data['receipt'].get('receipt_address') or company.address or '—'
    preview_name    = settings_data['receipt'].get('receipt_company_name') or company.name

    context = {
        'company': company,
        'settings': settings_data,
        'receipt': receipt_data,
        'is_viewing_company': is_viewing_company,
        # ---- Explicit preview values so the template never
        #      falls back to the logged-in user's email/phone/address ----
        'preview_email':   preview_email,
        'preview_phone':   preview_phone,
        'preview_address': preview_address,
        'preview_name':    preview_name,
    }
    return render(request, 'company/settings/receipt_preview.html', context)


# ============================================
# HELPER FUNCTIONS
# ============================================

def _as_settings_dict(value):
    """
    Normalize `company.company_settings` into a plain dict.

    `company_settings` is a Django JSONField, so on read Django already
    returns a dict. But some legacy rows may have been stored as a JSON
    string (from an older code path). This handles both — and treats
    None / empty as an empty dict.
    """
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def get_company_settings(company):
    """
    Return company settings — defaults merged with whatever is stored on
    `company.company_settings` (a JSONField).

    Each section (company, payment, receipt) is merged separately, so a
    missing section in storage still returns its defaults.
    """
    default_settings = {
        'company': {
            'currency': 'KES',
            'currency_symbol': 'KSh',
            'decimal_places': 2,
        },
        'payment': {
            # ---------- Currency & Tax ----------
            'currency': 'KES',
            'currency_symbol': 'KSh',
            'decimal_places': 2,
            'payment_methods': ['cash', 'm-pesa'],
            'enable_discount': True,
            'enable_tax': False,
            'default_tax_rate': 0,

            # ---------- Credit & Terms ----------
            'enable_partial_payment': False,
            'enable_credit': False,
            'credit_limit': 0,
            'payment_terms': 30,

            # ---------- M-Pesa STK Push ----------
            'enable_mpesa_stk': False,
            'mpesa_stk_shortcode': '',
            'mpesa_stk_passkey': '',

            # ---------- M-Pesa Buy Goods (Till) ----------
            'enable_buy_goods': False,
            'buy_goods_till': '',
            'buy_goods_name': '',

            # ---------- M-Pesa Paybill ----------
            'enable_paybill': False,
            'paybill_number': '',
            'paybill_account': '',
            'paybill_name': '',

            # ---------- Bank Transfer ----------
            'enable_bank': False,
            'bank_name': '',
            'bank_account_name': '',
            'bank_account': '',
            'bank_branch': '',
            'bank_swift': '',

            # ---------- Legacy aliases ----------
            'enable_mpesa': False,
            'mpesa_paybill': '',
            'mpesa_till': '',
        },
        'receipt': {
            'receipt_header': '',
            'receipt_footer': '',
            'receipt_format': 'standard',
            'show_logo': True,
            'show_company_details': True,
            'show_customer_details': True,
            'show_items': True,
            'show_totals': True,
            'show_payment': True,
            'show_signature': True,
            'show_customer_phone':    True,
            'show_customer_id':       True,
            'show_next_of_kin_phone': True,
            # ---- New granular toggles ----
            'show_company_name': True,
            'show_branch': True,
            'show_company_email': True,
            'show_company_phone': True,
            'show_company_pin': True,
            'show_receipt_title': True,
            'show_receipt_header': True,
            'show_receipt_footer': True,
            'show_thank_you': True,
            'show_receipt_info': True,
            'show_next_of_kin': True,
            'show_subtotal': True,
            'show_vat': True,
            'show_payment_method': True,
            'show_payment_status': True,

            'receipt_title': 'RECEIPT',
            'thank_you_message': 'Thank you for your business!',
            'include_barcode': False,
            'print_copies': 1,
            'auto_print': False,
            'receipt_font_size': '14',
            'receipt_width': '80',
            'custom_css': '',
            'receipt_company_name': '',
            'receipt_address': '',
            'receipt_phone': '',
            'receipt_email': '',
        },
    }

    saved = _as_settings_dict(company.company_settings)
    for section, defaults in default_settings.items():
        section_saved = saved.get(section)
        if isinstance(section_saved, dict):
            defaults.update(section_saved)

    return default_settings


def save_company_settings(company, settings_data, section=None):
    """
    Save settings into `company.company_settings` (a JSONField).

    `section` (e.g. 'receipt', 'payment'): replaces that section wholesale.
    No section: updates the 'company' section with the given keys.

    Only writes the `company_settings` column — no full-row UPDATE.
    """
    existing = _as_settings_dict(company.company_settings)

    if section:
        existing[section] = dict(settings_data)
    else:
        company_section = existing.get('company')
        if not isinstance(company_section, dict):
            company_section = {}
            existing['company'] = company_section
        company_section.update(settings_data)

    company.company_settings = existing
    company.save(update_fields=['company_settings'])