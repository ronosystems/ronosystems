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
    company = getattr(request, 'current_company', None)
    
    if company:
        bt_slug = ""
        if company.business_type:
            from apps.business_types.business_type_registry import BusinessTypeEnum
            bt_enum = BusinessTypeEnum.get_by_name(company.business_type.name)
            if bt_enum:
                bt_slug = bt_enum.value['slug']

        # 1. Calculate Cart Count
        cart = request.session.get('epa_cart', {})
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
    """
    # Determine the correct template based on the domain
    is_company_domain = getattr(request, 'current_company', None)
    template_name = 'website/company_contact.html' if is_company_domain else 'website/contact.html'

    if request.method == 'POST':
        name    = (request.POST.get('name') or '').strip()
        email   = (request.POST.get('email') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        message = (request.POST.get('message') or '').strip()

        if not name or not email or not message:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, template_name) # <-- Updated this render call

        full_subject = f"[Contact] {subject or 'New message'} — from {name}"
        body = (
            f"New contact form submission\n"
            f"----------------------------------------\n"
            f"Name:    {name}\n"
            f"Email:   {email}\n"
            f"Subject: {subject or '(none)'}\n"
            f"----------------------------------------\n\n"
            f"{message}\n"
        )

        recipient = getattr(settings, 'CONTACT_EMAIL', None)
        if not recipient:
            try:
                from apps.settings.models import SystemSetting
                recipient = SystemSetting.get_setting('EMAIL_FROM', 'support@ronosystems.com')
            except Exception:
                recipient = 'support@ronosystems.com'

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@ronosystems.com')

        try:
            send_mail(
                subject=full_subject,
                message=body,
                from_email=from_email,
                recipient_list=[recipient],
                fail_silently=False,
            )
            messages.success(request, 'Thanks! Your message has been sent — we will reply shortly.')
        except Exception as e:
            messages.error(request, f'Sorry, we could not send your message right now. ({e})')

        return redirect('contact')

    return render(request, template_name) # <-- Updated this render call too


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
        ]
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