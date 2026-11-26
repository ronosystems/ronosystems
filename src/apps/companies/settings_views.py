import os
import time
import json
import logging
import cloudinary
import cloudinary.uploader
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
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
from apps.companies.models import Company, Gallery # 👈 Import the new Gallery model
from apps.companies.models import Branch
import time
import random
import logging
from requests.exceptions import ConnectionError as ReqConnErr, SSLError
from urllib3.exceptions import MaxRetryError, ProtocolError




logger = logging.getLogger(__name__)


# ============================================
# CLOUDINARY HELPERS
# ============================================
ALLOWED_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')
ALLOWED_VIDEO_EXTS = ('.mp4', '.webm', '.ogg')


def _cloudinary_configure():
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


import requests

def _upload_company_media(file_obj, company_id, field_name,
                          resource_type='image', max_retries=3):
    """
    Upload a company media file to Cloudinary using requests.Session.
    This bypasses the urllib3 keep-alive bug that causes SSL_EOF.
    """
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    preset = cfg.get('UNSIGNED_PRESET', '')
    cloud_name = cfg.get('CLOUD_NAME', '')

    public_id = f"companies/{company_id}/{field_name}_{int(time.time())}"
    api_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/{resource_type}/upload"

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            # Fresh session each attempt → fresh socket, fresh TLS
            session = requests.Session()
            session.headers.update({
                'Connection': 'close',
                'User-Agent': 'curl/8.5.0', 
            })

            try:
                file_obj.seek(0)
            except Exception:
                pass
            
            file_bytes = file_obj.read()
            filename = getattr(file_obj, 'name', 'upload.bin')

            files = {'file': (filename, file_bytes)}
            data = {
                'upload_preset': preset,
                'public_id': public_id,
                'timestamp': int(time.time()),
            }

            resp = session.post(api_url, files=files, data=data, timeout=600)
            session.close()

            if resp.status_code in (200, 201):
                result = resp.json()
                return result.get('public_id') or public_id

            # If Cloudinary rejects it (e.g. file too large), show the real error
            raise ValueError(f"Cloudinary rejected upload: {resp.text}")

        except Exception as e:
            last_err = e
            logger.warning(
                'Cloudinary upload attempt %d/%d failed: %r',
                attempt, max_retries, e,
            )
            if attempt >= max_retries:
                raise
            time.sleep((2 ** attempt) + random.uniform(0, 1))

    raise last_err
    

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


def _handle_media_upload(request, company, field_name, post_file_key, resource_type='image'):
    """
    Shared upload handler for logo, favicon, login_background, receipt_logo, and hero media.
    Returns True if an upload was processed, False otherwise.
    Raises ValueError with a user-facing message on invalid input.
    """
    file_obj = request.FILES.get(post_file_key)
    if not file_obj:
        return False

    ext = os.path.splitext(file_obj.name)[1].lower()
    
    if resource_type == 'video':
        if ext not in ALLOWED_VIDEO_EXTS:
            raise ValueError('Invalid video format. Please upload MP4, WEBM, or OGG.')
    else:
        if ext not in ALLOWED_IMAGE_EXTS:
            raise ValueError('Invalid file format. Please upload JPG, PNG, GIF, SVG, or WEBP.')

    old_public_id = _current_public_id(getattr(company, field_name, ''))

    try:
        new_public_id = _upload_company_media(
            file_obj,
            company.id or company.pk,
            field_name,
            resource_type=resource_type,
        )
    except Exception as e:
        raise ValueError(f'{field_name.replace("_", " ").title()} upload failed: {e}')

    setattr(company, field_name, new_public_id)
    company.save(update_fields=[field_name])

    if old_public_id and old_public_id != new_public_id:
        _delete_company_media(old_public_id, resource_type=resource_type)

    return True


def _handle_media_remove(request, company, field_name, post_remove_key, resource_type='image'):
    """
    Shared removal handler for media fields.
    Returns True if a removal was processed, False otherwise.
    """
    if request.POST.get(post_remove_key) != 'true':
        return False

    old_public_id = _current_public_id(getattr(company, field_name, ''))
    if old_public_id:
        _delete_company_media(old_public_id, resource_type=resource_type)

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
    branches = Branch.objects.filter(company=company) 

    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'is_viewing_company': is_viewing_company,
        'branches': branches,
    }
    return render(request, 'companies/settings/dashboard.html', context)




# ============================================
# COMPANY SETTINGS
# ============================================
@login_required
def settings_company(request):
    """
    Company settings — update company info, logo, favicon, login background, receipt logo,
    hero media (video/image), hero text, gallery, and about page content.
    """
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            # ---------- 1) Media removals ----------
            removed_logo = _handle_media_remove(request, company, 'logo', 'remove_logo')
            removed_favicon = _handle_media_remove(request, company, 'favicon', 'remove_favicon')
            removed_bg = _handle_media_remove(request, company, 'login_background', 'remove_login_background')
            removed_receipt_logo = _handle_media_remove(request, company, 'receipt_logo', 'remove_receipt_logo')
            
            # Hero removals
            removed_hero_video = _handle_media_remove(
                request, company, 'hero_video', 'remove_hero_video', resource_type='video'
            )
            removed_hero_image = _handle_media_remove(
                request, company, 'hero_image', 'remove_hero_image'
            )

            # ---------- 2) Media uploads ----------
            uploaded_logo = False
            uploaded_favicon = False
            uploaded_bg = False
            uploaded_receipt_logo = False
            uploaded_hero_video = False
            uploaded_hero_image = False
            uploaded_gallery = False

            try:
                if not removed_logo:
                    uploaded_logo = _handle_media_upload(request, company, 'logo', 'company_logo')
                if not removed_favicon:
                    uploaded_favicon = _handle_media_upload(request, company, 'favicon', 'company_favicon')
                if not removed_bg:
                    uploaded_bg = _handle_media_upload(request, company, 'login_background', 'company_login_background')
                if not removed_receipt_logo:
                    uploaded_receipt_logo = _handle_media_upload(request, company, 'receipt_logo', 'company_receipt_logo')
            

            
                # Hero uploads
                if not removed_hero_video:
                    # 1. Check if the browser uploaded it directly to Cloudinary
                    direct_video_id = request.POST.get('company_hero_video', '').strip()
                    
                    if direct_video_id and not request.FILES.get('company_hero_video'):
                        old_video_id = _current_public_id(company.hero_video)
                        
                        # Save the new ID to the database
                        company.hero_video = direct_video_id
                        company.save(update_fields=['hero_video'])
                        
                        # Delete the old video from Cloudinary if it exists
                        if old_video_id and old_video_id != direct_video_id:
                            _delete_company_media(old_video_id, resource_type='video')
                            
                        uploaded_hero_video = True
                    else:
                        # 2. Fallback for standard Django uploads (if any)
                        uploaded_hero_video = _handle_media_upload(
                            request, company, 'hero_video', 'company_hero_video', resource_type='video'
                        )
                if not removed_hero_image:
                    uploaded_hero_image = _handle_media_upload(
                        request, company, 'hero_image', 'company_hero_image'
                    )

                # 👈 NEW: Gallery Upload
                gallery_photo = request.FILES.get('gallery_photo')
                gallery_title = request.POST.get('gallery_title', '').strip()
                gallery_desc = request.POST.get('gallery_description', '').strip()

                if gallery_photo and gallery_title:
                    public_id = _upload_company_media(
                        gallery_photo, 
                        company.id, 
                        'gallery', 
                        resource_type='image'
                    )
                    Gallery.objects.create(
                        company=company,
                        title=gallery_title,
                        description=gallery_desc,
                        image=public_id
                    )
                    uploaded_gallery = True

            except ValueError as e:
                messages.error(request, str(e))
                return redirect('companies:company-settings-company')

            # ---------- 3) Text fields ----------
            company_name = request.POST.get('company_name')
            company_email = request.POST.get('company_email')
            company_phone = request.POST.get('company_phone')
            company_address = request.POST.get('company_address')
            company_pin     = request.POST.get('company_pin')
            hero_title      = request.POST.get('hero_title', '')
            hero_subtitle   = request.POST.get('hero_subtitle', '')

            # New About Page Fields
            about_tagline     = request.POST.get('about_tagline', '')
            about_mission     = request.POST.get('about_mission', '')
            about_vision      = request.POST.get('about_vision', '')
            about_story       = request.POST.get('about_story', '')
            founded_year_raw  = request.POST.get('founded_year', '').strip()
            years_biz_raw     = request.POST.get('years_in_business', '').strip()

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
            if company_pin is not None and company.company_pin != company_pin:
                company.company_pin = company_pin
                text_changed = True
            if company.hero_title != hero_title:
                company.hero_title = hero_title
                text_changed = True
            if company.hero_subtitle != hero_subtitle:
                company.hero_subtitle = hero_subtitle
                text_changed = True

            # About Page Fields
            if company.about_tagline != about_tagline:
                company.about_tagline = about_tagline
                text_changed = True
            if company.about_mission != about_mission:
                company.about_mission = about_mission
                text_changed = True
            if company.about_vision != about_vision:
                company.about_vision = about_vision
                text_changed = True
            if company.about_story != about_story:
                company.about_story = about_story
                text_changed = True

                
            # --- NEW: Social Media Links ---
            facebook_url    = request.POST.get('facebook_url', '').strip()
            twitter_url     = request.POST.get('twitter_url', '').strip()
            instagram_url   = request.POST.get('instagram_url', '').strip()
            linkedin_url    = request.POST.get('linkedin_url', '').strip()
            telegram_url    = request.POST.get('telegram_url', '').strip()
            whatsapp_number = request.POST.get('whatsapp_number', '').strip()

            if company.facebook_url != facebook_url:
                company.facebook_url = facebook_url
                text_changed = True
            if company.twitter_url != twitter_url:
                company.twitter_url = twitter_url
                text_changed = True
            if company.instagram_url != instagram_url:
                company.instagram_url = instagram_url
                text_changed = True
            if company.linkedin_url != linkedin_url:
                company.linkedin_url = linkedin_url
                text_changed = True
            if company.telegram_url != telegram_url:
                company.telegram_url = telegram_url
                text_changed = True
            if company.whatsapp_number != whatsapp_number:
                company.whatsapp_number = whatsapp_number
                text_changed = True

            # Safe integer parsing
            try:
                new_founded = int(founded_year_raw) if founded_year_raw else None
                if company.founded_year != new_founded:
                    company.founded_year = new_founded
                    text_changed = True
            except ValueError:
                pass

            try:
                new_years = int(years_biz_raw) if years_biz_raw else None
                if company.years_in_business != new_years:
                    company.years_in_business = new_years
                    text_changed = True
            except ValueError:
                pass

            if text_changed:
                company.save()

            # ---------- 4) JSON-backed settings ----------
            save_company_settings(company, request.POST)

            # ---------- 5) Final message ----------
            messages.success(request, 'Company settings updated successfully!')

            return redirect('companies:company-settings-company')

        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')

    settings_data = get_company_settings(company)

    # 👈 Fetch gallery images for the template
    gallery_images = Gallery.objects.filter(company=company).order_by('-created_at')

    context = {
        'company': company,
        'settings': settings_data,
        'is_settings': True,
        'active_tab': 'company',
        'is_viewing_company': is_viewing_company,
        'gallery_images': gallery_images,
        'CLOUDINARY_CLOUD_NAME': getattr(django_settings, 'CLOUDINARY_STORAGE', {}).get('CLOUD_NAME', ''),
        'CLOUDINARY_UNSIGNED_PRESET': getattr(django_settings, 'CLOUDINARY_STORAGE', {}).get('UNSIGNED_PRESET', ''),
    }
    return render(request, 'companies/settings/dashboard.html', context)




@login_required
@require_POST
def company_gallery_upload(request):
    # Use your safe get_active_company method to prevent super admins from breaking it
    company, _ = get_active_company(request) 
    
    if not company:
        messages.error(request, "No active company found.")
        return redirect(request.META.get("HTTP_REFERER", "company-settings-company"))

    title = request.POST.get("gallery_title", "").strip()
    description = request.POST.get("gallery_description", "").strip()
    photo = request.FILES.get("gallery_photo")

    if not title or not photo:
        messages.error(request, "Title and photo are required.")
        return redirect(request.META.get("HTTP_REFERER", "company-settings-company"))

    try:
        # 1. Upload the photo to Cloudinary FIRST
        public_id = _upload_company_media(
            photo,
            company.id,
            'gallery',
            resource_type='image'
        )
        
        # 2. Save the Cloudinary ID to the database
        Gallery.objects.create(
            company=company,
            title=title,
            description=description,
            image=public_id,
        )
        messages.success(request, "Photo uploaded to gallery.")
    except Exception as e:
        messages.error(request, f"Gallery upload failed: {str(e)}")

    return redirect(request.META.get("HTTP_REFERER", "company-settings-company"))


# ============================================
# GALLERY DELETE
# ============================================
@login_required
def settings_gallery_delete(request, pk):
    """Delete a gallery image."""
    company, _ = get_active_company(request)
    if not company:
        return redirect('/dashboard/')

    gallery_item = get_object_or_404(Gallery, pk=pk, company=company)
    
    # Delete from Cloudinary first
    if gallery_item.image:
        _delete_company_media(gallery_item.image)
    
    # Delete from DB
    gallery_item.delete()
    messages.success(request, 'Gallery photo removed.')
    return redirect('companies:company-settings-company')
    

# ============================================
# PAYMENT SETTINGS
# ============================================
@login_required
def settings_payment(request):
    """Payment settings — supports granular M-Pesa STK / Buy Goods / Paybill / Bank"""
    from django.db import models as _models
    from django.utils import timezone as _tz

    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # ── Gate: require the active plan to include M-Pesa integration ──
    has_mpesa = False

    active_sub = (
        company.subscriptions
        .filter(status='active')
        .filter(
            _models.Q(end_date__isnull=True)
            | _models.Q(end_date__gt=_tz.now())
        )
        .select_related('plan')
        .first()
    )

    if active_sub:
        has_mpesa = bool(active_sub.plan.has_mpesa_integration)
    elif not company.subscriptions.exists():
        # No subscription rows at all → fall back to cached plan
        has_mpesa = bool(company.plan and company.plan.has_mpesa_integration)

    if not has_mpesa:
        messages.error(
            request,
            'Your current plan does not include M-Pesa integration. '
            'Upgrade your subscription to configure payment settings.',
        )
        return redirect('companies:company-settings-company')

    # ── Normal view logic ──
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
                'mpesa_branch':     (request.POST.get('mpesa_branch') or '').strip(),
                'mpesa_provider':   (request.POST.get('mpesa_provider') or 'daraja').strip(),
                'mpesa_stk_shortcode': request.POST.get('mpesa_stk_shortcode', ''),
                'mpesa_stk_passkey': request.POST.get('mpesa_stk_passkey', ''),

                # ---------- M-Pesa STK Push: Daraja credentials (per company) ----------
                'mpesa_consumer_key':       request.POST.get('mpesa_consumer_key', '').strip(),
                'mpesa_consumer_secret':    request.POST.get('mpesa_consumer_secret', '').strip(),
                'mpesa_environment':        request.POST.get('mpesa_environment', 'sandbox'),
                'mpesa_callback_url':       request.POST.get('mpesa_callback_url', '').strip(),
                'mpesa_shortcode_type':     request.POST.get('mpesa_shortcode_type', 'paybill'),
                'mpesa_account_reference':  request.POST.get('mpesa_account_reference', '').strip(),

                # ---------- M-Pesa STK Push: Kopokopo credentials (per company) ----------
                'kopokopo_client_id':       request.POST.get('kopokopo_client_id', '').strip(),
                'kopokopo_client_secret':   request.POST.get('kopokopo_client_secret', '').strip(),
                'kopokopo_till_number':     request.POST.get('kopokopo_till_number', '').strip(),
                'kopokopo_webhook_secret':  request.POST.get('kopokopo_webhook_secret', '').strip(),
                'kopokopo_callback_url':    request.POST.get('kopokopo_callback_url', '').strip(),

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

                # ---------- Legacy aliases ----------
                'enable_mpesa': (
                    request.POST.get('enable_mpesa_stk') == 'on'
                    or request.POST.get('enable_buy_goods') == 'on'
                    or request.POST.get('enable_paybill') == 'on'
                ),
                'mpesa_till': request.POST.get('buy_goods_till', ''),
                'mpesa_paybill': request.POST.get('paybill_number', ''),
            }

            save_company_settings(company, payment_settings, 'payment')

            # Mirror the saved settings into an MpesaConfig row (per company)
            _sync_mpesa_config(company, payment_settings, request=request)

            messages.success(request, 'Payment settings updated successfully!')
            return redirect('companies:company-settings-payment')

        except Exception as e:
            messages.error(request, f'Error updating payment settings: {str(e)}')

    settings_data = get_company_settings(company)
    branches = Branch.objects.filter(company=company)

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
        'branches': branches,
    }
    return render(request, 'companies/settings/dashboard.html', context)




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
                'show_company_name':      request.POST.get('show_company_name') == 'on',
                'show_branch':            request.POST.get('show_branch') == 'on',
                'show_company_email':     request.POST.get('show_company_email') == 'on',
                'show_company_phone':     request.POST.get('show_company_phone') == 'on',
                'show_company_pin':       request.POST.get('show_company_pin') == 'on',
                'show_receipt_title':     request.POST.get('show_receipt_title') == 'on',
                'show_receipt_header':    request.POST.get('show_receipt_header') == 'on',
                'show_receipt_footer':    request.POST.get('show_receipt_footer') == 'on',
                'show_thank_you':         request.POST.get('show_thank_you') == 'on',
                'show_receipt_info':      request.POST.get('show_receipt_info') == 'on',
                'show_next_of_kin':       request.POST.get('show_next_of_kin') == 'on',
                'show_subtotal':          request.POST.get('show_subtotal') == 'on',
                'show_vat':               request.POST.get('show_vat') == 'on',
                'show_payment_method':    request.POST.get('show_payment_method') == 'on',
                'show_payment_status':    request.POST.get('show_payment_status') == 'on',
                'show_customer_phone':    request.POST.get('show_customer_phone') == 'on',
                'show_customer_id':       request.POST.get('show_customer_id') == 'on',
                'show_next_of_kin_phone': request.POST.get('show_next_of_kin_phone') == 'on',
                'receipt_title':          request.POST.get('receipt_title', 'RECEIPT'),
                'thank_you_message':      request.POST.get('thank_you_message', 'Thank you for your business!'),
                'include_barcode':        request.POST.get('include_barcode') == 'on',
                'print_copies':           int(request.POST.get('print_copies', 1)),
                'auto_print':             request.POST.get('auto_print') == 'on',
                'receipt_font_size':      request.POST.get('receipt_font_size', '14'),
                'receipt_width':          request.POST.get('receipt_width', '80'),
                'custom_css':             request.POST.get('custom_css', ''),
                'receipt_company_name':   request.POST.get('receipt_company_name', ''),
                'receipt_address':        request.POST.get('receipt_address', ''),
                'receipt_phone':          request.POST.get('receipt_phone', ''),
                'receipt_email':          request.POST.get('receipt_email', ''),
                'show_sale_barcode':      request.POST.get('show_sale_barcode') == 'on',
                'show_payment_stamp':     request.POST.get('show_payment_stamp') == 'on',
                'stamp_style':            request.POST.get('stamp_style', 'inline'),
                'stamp_show_date':        request.POST.get('stamp_show_date') == 'on',
            }
            save_company_settings(company, receipt_settings, 'receipt')
            messages.success(request, 'Receipt settings updated successfully!')
            return redirect('companies:company-settings-receipt')

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
    return render(request, 'companies/settings/dashboard.html', context)


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

    preview_email   = settings_data['receipt'].get('receipt_email')   or company.email   or '—'
    preview_phone   = settings_data['receipt'].get('receipt_phone')   or company.phone   or '—'
    preview_address = settings_data['receipt'].get('receipt_address') or company.address or '—'
    preview_name    = settings_data['receipt'].get('receipt_company_name') or company.name

    context = {
        'company': company,
        'settings': settings_data,
        'receipt': receipt_data,
        'is_viewing_company': is_viewing_company,
        'preview_email':   preview_email,
        'preview_phone':   preview_phone,
        'preview_address': preview_address,
        'preview_name':    preview_name,
    }
    return render(request, 'companies/settings/dashboard.html', context)


# ============================================
# HELPER FUNCTIONS
# ============================================

def _as_settings_dict(value):
    """
    Normalize `company.company_settings` into a plain dict.
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
            'mpesa_branch':     '',
            'mpesa_provider':   'daraja',
            'mpesa_stk_shortcode': '',
            'mpesa_stk_passkey': '',

            # ---------- M-Pesa STK Push: Daraja credentials (per company) ----------
            'mpesa_consumer_key':       '',
            'mpesa_consumer_secret':    '',
            'mpesa_environment':        'sandbox',
            'mpesa_callback_url':       '',
            'mpesa_shortcode_type':     'paybill',
            'mpesa_account_reference':  '',

            # ---------- M-Pesa STK Push: Kopokopo credentials (per company) ----------
            'kopokopo_client_id':       '',
            'kopokopo_client_secret':   '',
            'kopokopo_till_number':     '',
            'kopokopo_webhook_secret':  '',
            'kopokopo_callback_url':    '',

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
            'show_sale_barcode': False,
            'show_payment_stamp': False,
            'stamp_style': 'inline',
            'stamp_show_date': True,
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


def _sync_mpesa_config(company, payment_settings, request=None):
    """
    Mirror the per-company payment settings into an MpesaConfig row.
    """
    try:
        from apps.mpesa.models import MpesaConfig
    except Exception:
        # mpesa app not installed yet — silently skip
        return

    from django.core.exceptions import ValidationError
    from django.contrib import messages

    enabled         = bool(payment_settings.get('enable_mpesa_stk'))
    provider        = (payment_settings.get('mpesa_provider') or 'daraja').strip() or 'daraja'

    # 👈 GET THE BRANCH
    branch_id       = payment_settings.get('mpesa_branch')
    branch          = None
    if branch_id:
        branch = Branch.objects.filter(id=branch_id, company=company).first()

    # Daraja fields
    shortcode       = (payment_settings.get('mpesa_stk_shortcode') or '').strip()
    consumer_key    = (payment_settings.get('mpesa_consumer_key') or '').strip()
    consumer_secret = (payment_settings.get('mpesa_consumer_secret') or '').strip()
    passkey         = (payment_settings.get('mpesa_stk_passkey') or '').strip()
    daraja_callback = (payment_settings.get('mpesa_callback_url') or '').strip()
    environment     = (payment_settings.get('mpesa_environment') or 'sandbox').strip()
    shortcode_type  = (payment_settings.get('mpesa_shortcode_type') or 'paybill').strip()
    account_ref     = (payment_settings.get('mpesa_account_reference') or '').strip()

    # Kopokopo fields
    kk_client_id     = (payment_settings.get('kopokopo_client_id') or '').strip()
    kk_client_secret = (payment_settings.get('kopokopo_client_secret') or '').strip()
    kk_till          = (payment_settings.get('kopokopo_till_number') or '').strip()
    kk_webhook_secret= (payment_settings.get('kopokopo_webhook_secret') or '').strip()
    kk_callback      = (payment_settings.get('kopokopo_callback_url') or '').strip()

    # 👈 FILTER BY BRANCH
    existing_qs = MpesaConfig.objects.filter(
        company=company, 
        branch=branch, 
        provider=provider
    )
    existing = existing_qs.first()

    # ---------- Deactivate if STK is off ----------
    if not enabled:
        if existing and existing.is_active:
            existing.is_active = False
            try:
                existing.save(update_fields=['is_active', 'updated_at'])
            except ValidationError:
                MpesaConfig.objects.filter(pk=existing.pk).update(is_active=False)
        return

    # ---------- Per-provider required fields ----------
    if provider == 'kopokopo':
        if not (kk_client_id and kk_client_secret and kk_till and kk_callback):
            return
    else:  # daraja
        if not (shortcode and consumer_key and consumer_secret and passkey and daraja_callback):
            return

    # ---------- Create or update ----------
    try:
        if existing is None:
            cfg = MpesaConfig(
                company=company,
                branch=branch,  # 👈 ASSIGN BRANCH
                provider=provider,
                label=f"{branch.name if branch else 'Company-wide'} M-Pesa", # 👈 Dynamic Label
                environment=environment,
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                shortcode=shortcode,
                passkey=passkey,
                callback_url=(daraja_callback if provider == 'daraja' else kk_callback),
                shortcode_type=shortcode_type,
                account_reference=account_ref,
                kopokopo_client_id=kk_client_id,
                kopokopo_client_secret=kk_client_secret,
                kopokopo_till_number=kk_till,
                kopokopo_webhook_secret=kk_webhook_secret,
                is_active=True,
            )
            cfg.save()
        else:
            existing.branch                = branch
            existing.provider              = provider
            existing.environment           = environment
            existing.consumer_key          = consumer_key
            existing.consumer_secret       = consumer_secret
            existing.shortcode             = shortcode
            existing.passkey               = passkey
            existing.callback_url          = (daraja_callback if provider == 'daraja' else kk_callback)
            existing.shortcode_type        = shortcode_type
            existing.account_reference     = account_ref
            existing.kopokopo_client_id    = kk_client_id
            existing.kopokopo_client_secret= kk_client_secret
            existing.kopokopo_till_number  = kk_till
            existing.kopokopo_webhook_secret = kk_webhook_secret
            existing.is_active             = True
            existing.save()
    except ValidationError as e:
        # Surface to the UI, but don't crash the settings save.
        if request is not None:
            try:
                for field, errs in (e.message_dict or {}).items():
                    for err in errs:
                        messages.error(request, f'M-Pesa config: {field}: {err}')
            except Exception:
                pass
        else:
            logger.warning(
                'MpesaConfig validation failed for %s: %s',
                company.name, getattr(e, 'message_dict', e),
                exc_info=True,
            )


@login_required
def api_get_branch_mpesa_config(request):
    """Fetch the saved M-Pesa config for a specific branch to populate the UI."""
    company, _ = get_active_company(request)
    branch_id = request.GET.get('branch_id')
    
    data = {
        'provider': 'daraja',
        'mpesa_stk_shortcode': '',
        'mpesa_stk_passkey': '',
        'mpesa_consumer_key': '',
        'mpesa_consumer_secret': '',
        'mpesa_environment': 'sandbox',
        'mpesa_callback_url': '',
        'mpesa_shortcode_type': 'paybill',
        'mpesa_account_reference': '',
        'kopokopo_client_id': '',
        'kopokopo_client_secret': '',
        'kopokopo_till_number': '',
        'kopokopo_webhook_secret': '',
        'kopokopo_callback_url': '',
        'is_configured': False,
    }

    if company and branch_id:
        from apps.mpesa.models import MpesaConfig
        cfg = MpesaConfig.objects.filter(company=company, branch_id=branch_id).first()
        
        if cfg:
            data.update({
                'provider': cfg.provider,
                'mpesa_stk_shortcode': cfg.shortcode,
                'mpesa_stk_passkey': cfg.passkey,
                'mpesa_consumer_key': cfg.consumer_key,
                'mpesa_consumer_secret': cfg.consumer_secret,
                'mpesa_environment': cfg.environment,
                'mpesa_callback_url': cfg.callback_url if cfg.provider == 'daraja' else '',
                'mpesa_shortcode_type': cfg.shortcode_type,
                'mpesa_account_reference': cfg.account_reference,
                'kopokopo_client_id': cfg.kopokopo_client_id,
                'kopokopo_client_secret': cfg.kopokopo_client_secret,
                'kopokopo_till_number': cfg.kopokopo_till_number,
                'kopokopo_webhook_secret': cfg.kopokopo_webhook_secret,
                'kopokopo_callback_url': cfg.callback_url if cfg.provider == 'kopokopo' else '',
                'is_configured': True,
            })
            
    return JsonResponse(data)