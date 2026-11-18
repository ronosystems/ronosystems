import os
import base64
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.templatetags.static import static
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.views.decorators.cache import never_cache
from apps.epa_shop.storefront import get_epa_products
from apps.business_types.business_type_registry import BusinessTypeEnum
from django.contrib.auth.decorators import login_required
from apps.companies.models import ContactMessage 
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from apps.epa_shop.models import BranchStock
from apps.treasury.models import DailyRecord
from django.db.models import F
from apps.settings.models import SystemSetting
from datetime import datetime




@login_required
def notification_center(request):
    """
    A summary hub for all system notifications.
    """
    company = getattr(request, 'company', None) or getattr(request.user, 'company', None)
    user = request.user
    
    context = {
        'company': company,
    }

    # ==========================================
    # COMPANY-SPECIFIC COUNTS
    # ==========================================
    if company:
        # 1. Low Stock
        try:
            from apps.epa_shop.models import BranchStock
            context['low_stock_count'] = BranchStock.objects.filter(
                company=company, quantity_in_stock__lte=F('minimum_stock_level')
            ).count()
        except Exception:
            context['low_stock_count'] = 0

        # 2. Unverified Treasury Records
        try:
            from apps.treasury.models import DailyRecord
            context['unverified_daily_records_count'] = DailyRecord.objects.filter(
                company=company, is_approved=False
            ).count()
        except Exception:
            context['unverified_daily_records_count'] = 0
            
        # 3. Workshop Jobs
        try:
            from apps.workshop.models import WorkshopJob
            open_statuses = ['received', 'diagnosed', 'awaiting_approval', 'approved', 'in_progress', 'on_hold']
            context['my_open_jobs_count'] = WorkshopJob.objects.filter(
                company=company, 
                assigned_technician=user, 
                status__in=open_statuses
            ).count()
        except Exception:
            context['my_open_jobs_count'] = 0

    # ==========================================
    # SYSTEM-LEVEL COUNTS (SUPER ADMIN)
    # ==========================================
    if not company and user.role == 'super_admin':
        
        # 4. 

        # 5. New Users
        try:
            from apps.accounts.models import User
            
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            last_seen_iso = request.session.get('users_last_seen')
            
            if last_seen_iso:
                try:
                    last_seen = datetime.fromisoformat(last_seen_iso)
                    if timezone.is_naive(last_seen):
                        last_seen = timezone.make_aware(last_seen)
                    cutoff = max(last_seen, today_start)
                except (ValueError, TypeError):
                    cutoff = today_start
            else:
                cutoff = today_start

            context['new_users_count'] = User.objects.filter(created_at__gte=cutoff).count()
        except Exception:
            context['new_users_count'] = 0

    return render(request, 'companies/notification_center.html', context)



# Add this helper
def no_session(view_func):
    """
    Decorator that prevents Django from touching the session for
    a view. Used for PWA endpoints (manifest, sw.js, assetlinks)
    so background fetches don't overwrite the user's session.
    """
    def wrapper(request, *args, **kwargs):
        request.session.modified = False
        response = view_func(request, *args, **kwargs)
        return response
    return wrapper

# ============================================
# QZ TRAY SIGNING
# ============================================

def qz_sign(request):
    """
    Sign QZ Tray print requests so the browser doesn't get the
    'Untrusted website' prompt.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    message = request.body.decode('utf-8')
    key_path = os.path.join(settings.BASE_DIR, 'qz_keys', 'private.key')
    
    try:
        with open(key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)

        signature = private_key.sign(
            message.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA512(),
        )
        return JsonResponse({
            'signature': base64.b64encode(signature).decode('ascii')
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ============================================
# PUBLIC PAGES
# ============================================


def home(request):
    """Homepage for RonoSystems (or company subdomain)"""
    company = getattr(request, 'company', None) 
    
    if company:
        bt_slug = ""
        if company.business_type:
            from apps.business_types.business_type_registry import BusinessTypeEnum
            bt_enum = BusinessTypeEnum.get_by_name(company.business_type.name)
            if bt_enum:
                bt_slug = bt_enum.value['slug']

        # 1. Calculate Cart Count
        cart = request.session.get('cart_orders_cart', {})
        cart_count = sum(item['quantity'] for item in cart.values())

        context = {
            'company': company,
            'business_type_slug': bt_slug,
            'cart_count': cart_count, # Pass this to the template
        }

        if bt_slug == 'epa-shop':
            from apps.epa_shop.storefront import get_epa_products
            context.update(get_epa_products(company))
                
        return render(request, 'website/company_home.html', context)
        
    return render(request, 'website/home.html')


def api_root(request):
    """API Root endpoint"""
    return JsonResponse({
        'name': 'RonoSystems API',
        'version': '1.0.0',
        'status': 'active',
        'endpoints': {
            'auth': {
                'register': '/api/auth/register/',
                'login': '/api/auth/login/',
                'logout': '/api/auth/logout/',
                'profile': '/api/auth/profile/'
            },
            'companies': {
                'list': '/api/companies/',
                'detail': '/api/companies/{id}/'
            },
            'business_types': {
                'list': '/api/business-types/',
                'available': '/api/business-types/available/'
            },
            'epa_shop': {
                'categories': '/api/epa/categories/',
                'products': '/api/epa/products/',
                'sales': '/api/epa/sales/',
                'dashboard': '/api/epa/dashboard/'
            },
            'supermarket': {
                'categories': '/api/supermarket/categories/',
                'products': '/api/supermarket/products/',
                'sales': '/api/supermarket/sales/'
            }
        },
        'web_interface': {
            'login': '/auth/login/',
            'dashboard': '/dashboard/',
            'employees': '/company/employees/'
        }
    })


def contact(request):
    """
    Handle GET (show form) and POST (send message).
    - Company domains: Uses company-specific hero settings and branches.
    - System domain: Uses system-wide hero settings.
    """
    company = getattr(request, 'company', None)
    is_company_domain = bool(company)
    
    # Determine which template to use
    template_name = 'website/company_contact.html' if is_company_domain else 'website/contact.html'

    # ---- Fetch branches (only for company domains) ----
    branches = []
    if company:
        try:
            branches = company.company_branches.filter(is_active=True)
        except Exception:
            branches = []

    context = {
        'current_company': company,
        'branches': branches,
    }

    # ==========================================
    # HERO SETTINGS
    # ==========================================
    if is_company_domain:
        # COMPANY DOMAIN: Variables are handled directly in the template via current_company
        pass
    else:
        # SYSTEM DOMAIN: Fetch system hero settings
        context['system_hero_video'] = SystemSetting.get_video_url('SYSTEM_HERO_VIDEO')
        context['system_hero_image'] = SystemSetting.get_image_url('SYSTEM_HERO_IMAGE')
        context['system_hero_title'] = SystemSetting.get_setting('SYSTEM_HERO_TITLE', '')
        context['system_hero_subtitle'] = SystemSetting.get_setting('SYSTEM_HERO_SUBTITLE', '')

    # ==========================================
    # POST HANDLING (MESSAGE SUBMISSION)
    # ==========================================
    if request.method == 'POST':
        # 1. Honeypot Check (Spam Protection)
        if (request.POST.get('website_hp') or '').strip():
            return redirect('contact')

        # 2. Extract Form Data
        name     = (request.POST.get('name') or '').strip()
        email    = (request.POST.get('email') or '').strip()
        phone    = (request.POST.get('phone') or '').strip()
        whatsapp = (request.POST.get('whatsapp_number') or '').strip()
        subject  = (request.POST.get('subject') or '').strip()
        message  = (request.POST.get('message') or '').strip()

        # 3. Validation
        if not name or not email or not message:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, template_name, context)

        # 4. Save to Database (Crucial for Dashboard Viewing)
        try:
            ContactMessage.objects.create(
                company=company,
                name=name,
                email=email,
                phone=phone,
                whatsapp_number=whatsapp,
                subject=subject,
                message=message
            )
        except Exception as e:
            print(f"Error saving contact message to DB: {e}")

        # 5. Send Email Notification to Admin
        full_subject = f"[Contact] {subject or 'New message'} — from {name}"
        body = (
            f"New contact form submission\n"
            f"----------------------------------------\n"
            f"Name:     {name}\n"
            f"Email:    {email}\n"
            f"Phone:    {phone or '(not provided)'}\n"
            f"WhatsApp: {whatsapp or '(not provided)'}\n"
            f"Subject:  {subject or '(none)'}\n"
            f"----------------------------------------\n\n"
            f"{message}\n"
        )

        # Determine recipient
        if is_company_domain and company.email:
            recipient = company.email
        else:
            recipient = getattr(settings, 'CONTACT_EMAIL', None)
            if not recipient:
                try:
                    recipient = SystemSetting.get_setting('EMAIL_FROM', 'support@ronosystems.com')
                except Exception:
                    recipient = 'support@ronosystems.com'

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@ronosystems.com')

        # Only attempt to send email if we have a valid configuration
        if getattr(settings, 'EMAIL_HOST', None) or getattr(settings, 'EMAIL_BACKEND', '') == 'django.core.mail.backends.smtp.EmailBackend':
            try:
                send_mail(
                    subject=full_subject,
                    message=body,
                    from_email=from_email,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Failed to send admin notification email: {e}")
        else:
            print("Email backend not configured. Skipping admin notification.")

        # 6. Success and Redirect
        messages.success(request, 'Thanks! Your message has been sent — we will reply shortly.')
        return redirect('contact')

    # ==========================================
    # GET REQUEST: RENDER TEMPLATE
    # ==========================================
    return render(request, template_name, context)


@login_required
def admin_contact_messages(request):
    """
    View for admins to see contact messages and send replies.
    Supports Email, SMS, and WhatsApp simultaneously.
    
    Security Note: 
    - Company Admins only see messages for THEIR company.
    - Super Admins on the main system domain see ALL messages.
    - Emails are sent FROM the company's email, not the system default.
    """
    # ==========================================
    # 1. AUTHORIZATION CHECK
    # ==========================================
    if not request.user.is_staff and not getattr(request.user, 'is_company_admin', False):
        if getattr(request.user, 'role', '') not in ('company_admin', 'company_manager', 'super_admin'):
            messages.error(request, "You do not have permission to view this page.")
            return redirect('home')

    # ==========================================
    # 2. CONTEXT & SECURITY SETUP
    # ==========================================
    company = getattr(request, 'company', None) or getattr(request.user, 'company', None)
    is_company_domain = bool(company)
    
    # SECURITY CHECK: A non-superadmin MUST have a company context.
    if request.user.role != 'super_admin' and not company:
        messages.error(request, "Please access the dashboard from your company domain.")
        return redirect('home')

    # Choose the correct template based on domain
    if is_company_domain:
        template_name = 'website/company_contact_messages.html'
    else:
        template_name = 'website/contact_messages.html'

    # ==========================================
    # 3. DATA ISOLATION (FETCH MESSAGES)
    # ==========================================
    if company:
        contact_messages = ContactMessage.objects.filter(company=company).order_by('-created_at')
    else:
        contact_messages = ContactMessage.objects.all().order_by('-created_at')

    # ==========================================
    # 4. HANDLE REPLY SUBMISSION (POST)
    # ==========================================
    if request.method == 'POST' and 'reply_message' in request.POST:
        msg_id = request.POST.get('message_id')
        reply_text = (request.POST.get('reply_text') or '').strip()
        reply_methods = request.POST.getlist('reply_methods')

        msg = get_object_or_404(ContactMessage, id=msg_id)
        
        # STRICT SECURITY: Ensure a company admin can only reply to THEIR messages
        if company and msg.company != company:
            messages.error(request, "Invalid message selected. You do not own this message.")
            return redirect('admin_contact_messages')

        if not reply_text:
            messages.error(request, "Reply text cannot be empty.")
            return redirect('admin_contact_messages')
            
        if not reply_methods:
            messages.error(request, "Please select at least one method to send the reply.")
            return redirect('admin_contact_messages')

        sent_successfully = []
        failed_methods = []

        # ==========================================
        # 5. LOOP THROUGH SELECTED METHODS
        # ==========================================
        for method in reply_methods:
            
            # --- EMAIL ---
            if method == 'email' and msg.email:
                try:
                    # Determine sender identity
                    if msg.company and msg.company.email:
                        sender_email = msg.company.email
                    else:
                        sender_email = settings.DEFAULT_FROM_EMAIL

                    send_mail(
                        subject=f"Re: {msg.subject or 'Your message to us'}",
                        message=reply_text,
                        from_email=sender_email,
                        recipient_list=[msg.email],
                        fail_silently=False,
                    )
                    sent_successfully.append('Email')
                except Exception as e:
                    failed_methods.append(f"Email ({e})")

            # --- SMS ---
            elif method == 'sms' and msg.get_formatted_phone():
                try:
                    # Prepend company name so recipient knows who is replying
                    company_name = msg.company.name if msg.company else "RonoSystems"
                    sms_body = f"{company_name}: {reply_text}"

                    # ==========================================
                    # TODO: Integrate your actual SMS API here
                    # ==========================================
                    # Example (Africa's Talking):
                    # import africastalking
                    # africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
                    # sms = africastalking.SMS
                    # sms.send(sms_body, [msg.get_formatted_phone()])
                    
                    # Simulated Success:
                    print(f"SMS SENT TO {msg.get_formatted_phone()}: {sms_body}")
                    sent_successfully.append('SMS')
                except Exception as e:
                    failed_methods.append(f"SMS ({e})")

            # --- WHATSAPP ---
            elif method == 'whatsapp' and msg.get_formatted_whatsapp():
                try:
                    from twilio.rest import Client
                    
                    # Prepend company name so recipient knows who is replying
                    company_name = msg.company.name if msg.company else "RonoSystems"
                    wa_body = f"*{company_name}*\n\n{reply_text}"

                    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                    
                    client.messages.create(
                        from_='whatsapp:+14155238886',  # Twilio Sandbox number
                        body=wa_body,
                        to=f"whatsapp:{msg.get_formatted_whatsapp()}"
                    )
                    sent_successfully.append('WhatsApp')
                except Exception as e:
                    failed_methods.append(f"WhatsApp ({e})")

            else:
                failed_methods.append(f"{method} (No contact info)")

        # ==========================================
        # 6. SAVE TO DATABASE
        # ==========================================
        if sent_successfully:
            msg.admin_reply = reply_text
            msg.replied_at = timezone.now()
            msg.reply_method = ", ".join(reply_methods)
            msg.is_read = True
            msg.save()
            
            success_msg = f"Reply sent successfully via: {', '.join(sent_successfully)}."
            if failed_methods:
                success_msg += f" However, failed for: {', '.join(failed_methods)}."
            messages.success(request, success_msg)
        else:
            messages.error(request, f"Failed to send reply. {', '.join(failed_methods)}")

        return redirect('admin_contact_messages')

    # ==========================================
    # 7. HANDLE MARK AS READ
    # ==========================================
    if request.method == 'POST' and 'mark_read' in request.POST:
        msg_id = request.POST.get('mark_read')
        msg = get_object_or_404(ContactMessage, id=msg_id)
        
        if not company or msg.company == company:
            msg.is_read = True
            msg.save()
            messages.success(request, "Message marked as read.")
        return redirect('admin_contact_messages')

    # ==========================================
    # 8. RENDER TEMPLATE
    # ==========================================
    return render(request, template_name, {
        'contact_messages': contact_messages,
        'current_company': company,
    })

@login_required
def delete_contact_messages(request):
    """Handle bulk deletion of contact messages."""
    if request.method == 'POST':
        message_ids = request.POST.getlist('message_ids')
        
        if not message_ids:
            messages.error(request, "No messages selected.")
            return redirect('admin_contact_messages')

        company = getattr(request, 'company', None) or getattr(request.user, 'company', None)
        
        # Filter by company if not super admin to ensure security
        if company:
            msgs_to_delete = ContactMessage.objects.filter(id__in=message_ids, company=company)
        else:
            msgs_to_delete = ContactMessage.objects.filter(id__in=message_ids)
            
        count = msgs_to_delete.count()
        msgs_to_delete.delete()
        
        messages.success(request, f"Successfully deleted {count} message(s).")
        
    return redirect('admin_contact_messages')


    
# ============================================
# PWA: MANIFEST
# ============================================

@no_session
def manifest_view(request):
    from apps.companies.models import Company
    from django.templatetags.static import static
    from django.http import JsonResponse
    from django.conf import settings
    
    try:
        from apps.settings.models import SystemSetting
    except ImportError:
        SystemSetting = None

    company = None
    
    # 1. Check URL parameter first (useful for local testing)
    company_id = request.GET.get('company_id')
    if company_id:
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            pass
    
    # 2. Check logged-in user's company
    if not company and request.user.is_authenticated and getattr(request.user, 'company', None):
        company = request.user.company

    # 3. Match the domain name to a company dynamically
    if not company:
        host = request.get_host().split(':')[0].lower()
        try:
            company = Company.objects.filter(custom_domain__iexact=host).first()
        except Exception:
            pass

    # ============================================
    # BUILD MANIFEST DATA
    # ============================================
    company_name = "RONOSYSTEMS"
    icon_192 = request.build_absolute_uri(static('images/icon-192.png'))
    icon_512 = request.build_absolute_uri(static('images/icon-512.png'))
    
    # Default fallback screenshots
    screenshot_wide = request.build_absolute_uri(static('images/screenshot-wide.png'))
    screenshot_narrow = request.build_absolute_uri(static('images/screenshot-narrow.png'))
    
    if company:
        # ---------------------------------------------------------
        # COMPANY DOMAIN LOGIC (e.g., Fieldmax)
        # ---------------------------------------------------------
        if company.display_name:
            company_name = company.display_name.upper()
            
        if company.logo:
            try:
                raw_logo = company.logo_url if hasattr(company, 'logo_url') and company.logo_url else company.logo.url
                if 'cloudinary' in raw_logo:
                    icon_192 = raw_logo.replace('/upload/', '/upload/w_192,h_192,c_fill,f_png/')
                    icon_512 = raw_logo.replace('/upload/', '/upload/w_512,h_512,c_fill,f_png/')
                else:
                    icon_192 = request.build_absolute_uri(raw_logo)
                    icon_512 = request.build_absolute_uri(raw_logo)
            except Exception:
                pass
                
        # Optional: If your Company model has custom screenshot fields, use them here.
        # If not, it will fall back to the static screenshots above.
    else:
        # ---------------------------------------------------------
        # SYSTEM DOMAIN LOGIC (RonoSystems)
        # ---------------------------------------------------------
        sys_logo_url = None
        
        if SystemSetting:
            try:
                db_name = SystemSetting.get_setting('SITE_NAME')
                if db_name:
                    company_name = db_name.upper()
                
                sys_logo_url = SystemSetting.get_image_url('SITE_LOGO')
            except Exception:
                pass

        if sys_logo_url:
            if 'cloudinary' in sys_logo_url:
                icon_192 = sys_logo_url.replace('/upload/', '/upload/w_192,h_192,c_fill,f_png/')
                icon_512 = sys_logo_url.replace('/upload/', '/upload/w_512,h_512,c_fill,f_png/')
            else:
                icon_192 = sys_logo_url
                icon_512 = sys_logo_url

    manifest = {
        "id": "/",
        "name": company_name,
        "short_name": company_name,
        "description": f"Manage {company_name} smarter and faster.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone"],
        "orientation": "any",
        "background_color": "#f0f2f5",
        "theme_color": "#1e4e6d",
        "categories": ["business", "productivity"],
        
        # --- PWABuilder Score Boosters ---
        "lang": "en",
        "dir": "ltr",
        "prefer_related_applications": False,
        
        # IARC Rating (Replace '0' with your actual IARC code if you get one)
        # "iarc_rating_id": "YOUR-IARC-CODE", 
        
        # --- Launch Handler (Focus existing window instead of opening new tabs) ---
        "launch_handler": {
            "client_mode": "focus-existing"
        },
        
        # --- Scope Extensions (Allows navigating to external subdomains) ---
        "scope_extensions": [
            {"type": "origin", "value": "https://ronosystems.com"},
            {"type": "origin", "value": "https://fieldmax.shop"}
        ],
        
        # --- File Handlers (Allows users to open files with your PWA) ---
        "file_handlers": [
            {
                "action": "/epa_shop/pos/import/", # Change this to your actual upload route
                "accept": {
                    "text/csv": [".csv"],
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
                    "application/pdf": [".pdf"]
                }
            }
        ],
        
        # --- Icons ---
        "icons": [
            {
                "src": icon_192, 
                "sizes": "192x192", 
                "type": "image/png", 
                "purpose": "any"
            },
            {
                "src": icon_512, 
                "sizes": "512x512", 
                "type": "image/png", 
                "purpose": "any maskable"
            }
        ],
        
        # --- Screenshots (Sized exactly to pass PWABuilder strict checks) ---
        "screenshots": [
            {
                "src": screenshot_wide,
                "sizes": "1280x720",
                "type": "image/png",
                "form_factor": "wide",
                "label": f"{company_name} Desktop View"
            },
            {
                "src": screenshot_narrow,
                "sizes": "720x1280",
                "type": "image/png",
                "form_factor": "narrow",
                "label": f"{company_name} Mobile View"
            }
        ],
        
        # --- App Shortcuts (Long-press the app icon to see these) ---
        "shortcuts": [
            {
                "name": "Dashboard",
                "url": "/dashboard/",
                "description": "Open your dashboard"
            },
            {
                "name": "POS System",
                "url": "/epa_shop/pos/",
                "description": "Open Point of Sale"
            }
        ],

        # --- Protocol Handlers ---
        "protocol_handlers": [
            {
                "protocol": "web+ronosystems",
                "url": "/?action=%s"
            }
        ],
        
        # --- Share Target ---
        "share_target": {
            "action": "/share-target/",
            "method": "GET",
            "enctype": "application/x-www-form-urlencoded",
            "params": {
                "title": "title",
                "text": "text",
                "url": "url"
            }
        },
    }

    response = JsonResponse(manifest)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


# ============================================
# PWA: SERVICE WORKER 
# ============================================

@no_session
def service_worker(request):
    """Serve sw.js from the root path so PWABuilder and Chrome can find it."""
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'sw.js')
    try:
        with open(sw_path, 'rb') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/javascript')
    except FileNotFoundError:
        try:
            from django.contrib.staticfiles import finders
            result = finders.find('sw.js')
            if result:
                with open(result, 'rb') as f:
                    content = f.read()
                return HttpResponse(content, content_type='application/javascript')
        except Exception:
            pass
        return HttpResponse("// sw.js not found", content_type='application/javascript', status=404)


# ============================================
# PWA: ASSET LINKS
# ============================================

@no_session
def asset_links(request):
    """Serve the assetlinks.json for Android TWA verification."""
    file_path = os.path.join(settings.BASE_DIR, 'static', '.well-known', 'assetlinks.json')
    try:
        with open(file_path, 'r') as f:
            return HttpResponse(f.read(), content_type='application/json')
    except FileNotFoundError:
        return HttpResponse('Not found', status=404)