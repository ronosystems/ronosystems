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

    Examples:
        companies/42/logo_1789754321
        companies/42/favicon_1789754321
        companies/42/login_background_1789754321

    Why unique: Cloudinary's CDN caches by public_id. Replacing a file with
    a fixed public_id + overwrite=True serves the OLD cached version. A
    unique public_id makes every upload a brand-new asset → no stale content.

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
    """
    Extract the stored public_id from a Company media field value.

    The model stores these as plain strings (CharField). This helper is
    defensive against legacy data where the value may still be a FieldFile.
    """
    if not field_value:
        return ''
    key = getattr(field_value, 'name', None) or str(field_value)
    return key.strip().lstrip('/')


def _handle_media_upload(request, company, field_name, post_file_key):
    """
    Shared upload handler for logo, favicon, and login_background.

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
            field_name,           # 'logo' | 'favicon' | 'login_background'
            resource_type='image',
        )
    except Exception as e:
        raise ValueError(f'{field_name.replace("_", " ").title()} upload failed: {e}')

    setattr(company, field_name, new_public_id)
    company.save(update_fields=[field_name])

    # Clean up the old asset (only if it was a different one)
    if old_public_id and old_public_id != new_public_id:
        _delete_company_media(old_public_id, resource_type='image')

    return True


def _handle_media_remove(request, company, field_name, post_remove_key):
    """
    Shared removal handler for logo, favicon, and login_background.

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
# COMPANY SETTINGS (Cloudinary logo + favicon + login background)
# ============================================
@login_required
def settings_company(request):
    """Company settings — update company info, logo, favicon and login background"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            # ---------- 1) Media removals (checked first — an explicit
            #              "remove" should win over a same-request upload) ----------
            removed_logo = _handle_media_remove(
                request, company, 'logo', 'remove_logo'
            )
            removed_favicon = _handle_media_remove(
                request, company, 'favicon', 'remove_favicon'
            )
            removed_bg = _handle_media_remove(
                request, company, 'login_background', 'remove_login_background'
            )

            if removed_logo:
                messages.success(request, 'Company logo removed.')
            if removed_favicon:
                messages.success(request, 'Favicon removed.')
            if removed_bg:
                messages.success(request, 'Login background removed.')

            # ---------- 2) Media uploads ----------
            uploaded_logo = False
            uploaded_favicon = False
            uploaded_bg = False

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
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('company-settings-company')

            if uploaded_logo:
                messages.success(request, 'Company logo updated.')
            if uploaded_favicon:
                messages.success(request, 'Favicon updated.')
            if uploaded_bg:
                messages.success(request, 'Login background updated.')

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

            # ---------- 4) Other JSON-backed settings ----------
            #    Only run this if the request came from the main settings form
            #    (it re-saves the 'company' section values).
            save_company_settings(company, request.POST)

            # ---------- 5) Final message ----------
            if not any([removed_logo, removed_favicon, removed_bg,
                        uploaded_logo, uploaded_favicon, uploaded_bg,
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
    """Payment settings"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            payment_settings = {
                'currency': request.POST.get('currency', 'KES'),
                'currency_symbol': request.POST.get('currency_symbol', 'KSh'),
                'decimal_places': int(request.POST.get('decimal_places', 2)),
                'payment_methods': request.POST.getlist('payment_methods'),
                'enable_discount': request.POST.get('enable_discount') == 'on',
                'enable_tax': request.POST.get('enable_tax') == 'on',
                'default_tax_rate': float(request.POST.get('default_tax_rate', 0)),
                'enable_partial_payment': request.POST.get('enable_partial_payment') == 'on',
                'enable_credit': request.POST.get('enable_credit') == 'on',
                'credit_limit': float(request.POST.get('credit_limit', 0)),
                'payment_terms': int(request.POST.get('payment_terms', 30)),
                'enable_mpesa': request.POST.get('enable_mpesa') == 'on',
                'mpesa_paybill': request.POST.get('mpesa_paybill', ''),
                'mpesa_till': request.POST.get('mpesa_till', ''),
                'enable_bank': request.POST.get('enable_bank') == 'on',
                'bank_name': request.POST.get('bank_name', ''),
                'bank_account': request.POST.get('bank_account', ''),
                'bank_branch': request.POST.get('bank_branch', ''),
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
                'show_logo': request.POST.get('show_logo') == 'on',
                'show_company_details': request.POST.get('show_company_details') == 'on',
                'show_customer_details': request.POST.get('show_customer_details') == 'on',
                'show_items': request.POST.get('show_items') == 'on',
                'show_totals': request.POST.get('show_totals') == 'on',
                'show_payment': request.POST.get('show_payment') == 'on',
                'show_signature': request.POST.get('show_signature') == 'on',
                'receipt_title': request.POST.get('receipt_title', 'RECEIPT'),
                'thank_you_message': request.POST.get('thank_you_message', 'Thank you for your business!'),
                'include_barcode': request.POST.get('include_barcode') == 'on',
                'print_copies': int(request.POST.get('print_copies', 1)),
                'auto_print': request.POST.get('auto_print') == 'on',
                'receipt_font_size': request.POST.get('receipt_font_size', '14'),
                'receipt_width': request.POST.get('receipt_width', '80'),
                'custom_css': request.POST.get('custom_css', ''),
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

    context = {
        'company': company,
        'settings': settings_data,
        'receipt': receipt_data,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/settings/receipt_preview.html', context)


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_company_settings(company):
    """Get company settings from JSON or defaults"""
    default_settings = {
        'company': {
            'currency': 'KES',
            'currency_symbol': 'KSh',
            'decimal_places': 2,
        },
        'payment': {
            'currency': 'KES',
            'currency_symbol': 'KSh',
            'decimal_places': 2,
            'payment_methods': ['cash', 'm-pesa'],
            'enable_discount': True,
            'enable_tax': False,
            'default_tax_rate': 0,
            'enable_partial_payment': False,
            'enable_credit': False,
            'credit_limit': 0,
            'payment_terms': 30,
            'enable_mpesa': True,
            'mpesa_paybill': '',
            'mpesa_till': '',
            'enable_bank': False,
            'bank_name': '',
            'bank_account': '',
            'bank_branch': '',
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
            'receipt_title': 'RECEIPT',
            'thank_you_message': 'Thank you for your business!',
            'include_barcode': False,
            'print_copies': 1,
            'auto_print': False,
            'receipt_font_size': '14',
            'receipt_width': '80',
            'custom_css': '',
        }
    }

    try:
        if company.company_settings:
            saved_settings = json.loads(company.company_settings)
            for section in default_settings:
                if section in saved_settings:
                    default_settings[section].update(saved_settings[section])
    except Exception:
        pass

    return default_settings


def save_company_settings(company, settings_data, section=None):
    """Save company settings to JSON"""
    try:
        existing = {}
        if company.company_settings:
            existing = json.loads(company.company_settings)

        if section:
            existing[section] = settings_data
        else:
            if 'company' not in existing:
                existing['company'] = {}
            existing['company'].update(settings_data)

        company.company_settings = json.dumps(existing)
        company.save()
    except Exception as e:
        raise e