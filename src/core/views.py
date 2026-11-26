import os
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from apps.companies.business_types import BusinessTypeEnum
from django.contrib.auth.decorators import login_required
from apps.companies.models import ContactMessage
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from apps.settings.models import SystemSetting
from datetime import datetime
from apps.companies.business_types import BusinessTypeEnum
from django.shortcuts import render




@login_required
def notification_center(request):
    company = getattr(request, 'company', None) or getattr(request.user, 'company', None)
    user = request.user
    
    context = {'company': company}


    if company:
        # 1. Low Stock
        try:
            from apps.epa_shop.models import Phone, Electronic, Accessory
            # Use the exact same helpers from inventory_views.py
            from apps.epa_shop.inventory_views import _available_phone_count, _available_electronic_count
            
            low_stock_count = 0
            
            for item in Electronic.objects.filter(company=company, is_active=True):
                if _available_electronic_count(item) <= 5:
                    low_stock_count += 1
                    
            for item in Phone.objects.filter(company=company, is_active=True):
                if _available_phone_count(item) <= 5:
                    low_stock_count += 1
                    
            for item in Accessory.objects.filter(company=company, is_active=True):
                if item.total_quantity_in_stock <= 5:
                    low_stock_count += 1
                    
            context['low_stock_count'] = low_stock_count
            
        except Exception as e:
            print(f"Notification Center Low Stock Error: {e}")
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
                    # Use Django's parse_datetime for safe timezone handling
                    from django.utils.dateparse import parse_datetime
                    last_seen = parse_datetime(last_seen_iso)
                    if not last_seen:
                        last_seen = today_start
                except (ValueError, TypeError):
                    last_seen = today_start
            else:
                last_seen = today_start

            context['new_users_count'] = User.objects.filter(created_at__gte=last_seen).count()
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
# PUBLIC PAGES
# ============================================


def home(request):
    """Homepage for RonoSystems (or company subdomain)"""
    company = getattr(request, 'company', None) 
    
    if company:
        bt_slug = ""
        if company.business_type:
            from apps.companies.business_types import BusinessTypeEnum
            bt_enum = BusinessTypeEnum.get_by_name(company.business_type.name)
            if bt_enum:
                bt_slug = bt_enum.value['slug']

        # 1. Calculate Cart Count
        cart = request.session.get('cart_orders_cart', {})
        cart_count = sum(item['quantity'] for item in cart.values())

        # 2. Fetch Gallery Images for the public page
        from apps.companies.models import Gallery
        gallery_images = Gallery.objects.filter(company=company).order_by('-created_at')[:6]

        context = {
            'company': company,
            'business_type_slug': bt_slug,
            'cart_count': cart_count, # Pass this to the template
            'gallery_images': gallery_images, 
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
    - Super Admins on the main system domain see ONLY system-level messages (no company).
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
        # On system domain, exclude messages meant for specific companies.
        # Only fetch messages where company is NULL.
        contact_messages = ContactMessage.objects.filter(company__isnull=True).order_by('-created_at')

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

        # STRICT SECURITY: Prevent super admin from replying to company messages via POST
        if not company and msg.company is not None:
            messages.error(request, "You cannot reply to company-specific messages from the system domain.")
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





@login_required
def super_admin_dashboard(request):
    if getattr(request.user, 'role', None) != 'super_admin':
        return redirect('dashboard-router')

    from django.utils import timezone
    from django.db.models import Count
    from datetime import timedelta

    now = timezone.now()
    today = now.date()
    soon = now + timedelta(days=14)
    thirty_ago = now - timedelta(days=30)
    sixty_ago = now - timedelta(days=60)

    stats = {
        'total_companies': 0, 'active_companies': 0,
        'total_users': 0, 'active_users': 0, 'inactive_users': 0,
        'active_subscriptions': 0, 'expiring_soon': 0,
        'expired_subscriptions': 0,
        'mrr': 0, 'arpc': 0,
    }
    business_type_breakdown = []
    recent_companies = []
    attention_companies = []
    plan_distribution = []
    health = {'active_rate': 0, 'growth_rate_30d': 0, 'suspended_rate': 0}

    try:
        from apps.companies.models import Company
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # --- Stats: Companies ---
        total = Company.objects.count()
        stats['total_companies'] = total
        try:
            stats['active_companies'] = Company.objects.filter(status='active').count()
            suspended = Company.objects.filter(status='suspended').count()
        except Exception:
            stats['active_companies'] = Company.objects.filter(is_active=True).count()
            suspended = 0

        # --- Stats: Users ---
        stats['total_users'] = User.objects.count()
        try:
            stats['active_users'] = User.objects.filter(is_active=True).count()
        except Exception:
            stats['active_users'] = stats['total_users']
        stats['inactive_users'] = stats['total_users'] - stats['active_users']

        # --- Health ---
        if total > 0:
            health['active_rate'] = round(stats['active_companies'] / total * 100, 1)
            health['suspended_rate'] = round(suspended / total * 100, 1)
        last_30 = Company.objects.filter(created_at__gte=thirty_ago).count()
        prev_30 = Company.objects.filter(created_at__gte=sixty_ago, created_at__lt=thirty_ago).count()
        if prev_30 > 0:
            health['growth_rate_30d'] = round((last_30 - prev_30) / prev_30 * 100, 1)
        elif last_30 > 0:
            health['growth_rate_30d'] = 100.0

        # --- Business Type Breakdown ---
        # Inahitaji: bt.business_type__name, bt.count
        try:
            business_type_breakdown = list(
                Company.objects.values('business_type__name')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
        except Exception:
            business_type_breakdown = []

        # --- Recent Companies ---
        # Inahitaji: company.name, .business_type.name, .created_at,
        # .custom_domain, .domain_verified, .plan.display_name, .users.count, .is_active, .status
        try:
            recent_companies = list(
                Company.objects.select_related('business_type', 'plan')
                .prefetch_related('users')
                .order_by('-created_at')[:8]
            )
        except Exception:
            recent_companies = list(Company.objects.order_by('-created_at')[:8])

        # --- Subscriptions / MRR / Plan Distribution ---
        # Jaribu kupata Subscription model
        SubModel = None
        for path in [
            'apps.companies.models.CompanySubscription',
            'apps.plans.models.Subscription',
            'apps.companies.models.Subscription',
        ]:
            try:
                mod_path, cls_name = path.rsplit('.', 1)
                import importlib
                mod = importlib.import_module(mod_path)
                SubModel = getattr(mod, cls_name)
                break
            except Exception:
                continue

        if SubModel:
            subs = SubModel.objects.select_related('company', 'plan').all()
            # Active = end_date bado haijaisha + is_active kama ipo
            try:
                active_subs = subs.filter(end_date__gte=today)
                stats['active_subscriptions'] = active_subs.count()
            except Exception:
                try:
                    active_subs = subs.filter(is_active_subscription=True)
                    stats['active_subscriptions'] = active_subs.count()
                except Exception:
                    active_subs = subs
                    stats['active_subscriptions'] = subs.count()

            try:
                stats['expiring_soon'] = active_subs.filter(end_date__lte=soon.date()).count()
            except Exception:
                stats['expiring_soon'] = 0
            try:
                stats['expired_subscriptions'] = subs.filter(end_date__lt=today).count()
            except Exception:
                stats['expired_subscriptions'] = 0

            # MRR = jumla ya bei za plan za active subs
            try:
                mrr = 0
                for s in active_subs:
                    price = getattr(getattr(s, 'plan', None), 'price', 0) or 0
                    # Kama plan ina monthly_price, tumia hiyo
                    if hasattr(getattr(s, 'plan', None), 'monthly_price'):
                        price = getattr(s.plan, 'monthly_price') or price
                    mrr += float(price)
                stats['mrr'] = int(mrr)
            except Exception:
                stats['mrr'] = 0

            if stats['active_subscriptions'] > 0:
                stats['arpc'] = int(stats['mrr'] / stats['active_subscriptions'])

            # Plan Distribution: item.count, item.plan, item.mrr, item.renewal_amount
            try:
                grouped = subs.values('plan').annotate(count=Count('id'))
                for g in grouped:
                    plan_obj = None
                    try:
                        from apps.plans.models import Plan
                        plan_obj = Plan.objects.filter(id=g['plan']).first()
                    except Exception:
                        pass
                    price = float(getattr(plan_obj, 'price', 0) or 0) if plan_obj else 0
                    plan_distribution.append({
                        'plan': plan_obj,
                        'count': g['count'],
                        'mrr': int(price * g['count']),
                        'renewal_amount': int(price * g['count']),
                    })
            except Exception:
                plan_distribution = []

            # Attention Companies: zinazoisha hivi karibuni / expired
            # item.company, item.days_left, item.end_date, item.plan
            try:
                for s in active_subs.filter(end_date__lte=soon.date()).order_by('end_date')[:10]:
                    end = getattr(s, 'end_date', None)
                    days_left = (end - today).days if end else None
                    attention_companies.append({
                        'company': getattr(s, 'company', None),
                        'plan': getattr(s, 'plan', None),
                        'end_date': end,
                        'days_left': days_left,
                        'count': 1,
                    })
            except Exception:
                attention_companies = []

    except Exception as e:
        # Usi-crash dashboard - log error lakini onyesha zeros
        import logging
        logging.getLogger(__name__).exception(f"super_admin_dashboard error: {e}")

    context = {
        'stats': stats,
        'business_type_breakdown': business_type_breakdown,
        'recent_companies': recent_companies,
        'attention_companies': attention_companies,
        'plan_distribution': plan_distribution,
        'health': health,
        # Aliases kwa ajili ya base.html / sidebar
        'total': stats['total_companies'],
        'current_company': None,
        'is_embed': False,
    }
    return render(request, 'superadmin/super_dashboard.html', context)


@login_required
def dashboard_router(request):
    user = request.user

    # 0. SUPER ADMIN -> dashboard yake mwenyewe
    if getattr(user, 'role', None) == 'super_admin':
        # Kama yuko kwenye Support Mode, mpeleke kwenye dashboard ya hiyo company
        support_id = request.session.get('support_company_id')
        if support_id:
            from apps.companies.models import Company
            company = Company.objects.filter(id=support_id).first()
            if company:
                slug = getattr(company, 'business_type_slug', None)
                bt = BusinessTypeEnum.get_by_slug(slug) if slug else None
                url_name = (bt.value.get('integration') or {}).get('web_dashboard_url_name') if bt else None
                if url_name:
                    return redirect(url_name)
        # Sio support mode -> super admin dashboard
        return redirect('super-admin-dashboard')

    # 1. Customer...
    if getattr(user, 'role', None) == 'customer':
        return redirect('customers:dashboard')

    # 2. Pata company
    company = getattr(user, 'company', None)
    if not company:
        company_id = request.session.get('current_company_id') or request.session.get('company_id')
        if company_id:
            from apps.companies.models import Company
            company = Company.objects.filter(id=company_id).first()

    if not company:
        return redirect('companies:company-list')

    # 3. business_type ni FK -> tumia slug
    #    company.business_type_slug inarudi 'epa-shop', 'supermarket', 'kuku-biz', 'chama'
    #    (kutoka models.py:464-465)
    slug = getattr(company, 'business_type_slug', None)
    bt = BusinessTypeEnum.get_by_slug(slug) if slug else None
    integration = bt.value.get('integration') if bt else None
    url_name = (integration or {}).get('web_dashboard_url_name')

    if url_name:
        return redirect(url_name)

    # 4. Fallback: hakuna business_type / inactive
    return redirect('epa_shop:web-dashboard')