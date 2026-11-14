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
    """Homepage for RonoSystems"""
    return render(request, 'home.html')


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
    if request.method == 'POST':
        name    = (request.POST.get('name') or '').strip()
        email   = (request.POST.get('email') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        message = (request.POST.get('message') or '').strip()

        if not name or not email or not message:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'contact.html')

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

    return render(request, 'contact.html')


# ============================================
# PWA: MANIFEST
# ============================================

@no_session
def manifest_view(request):
    from apps.companies.models import Company
    from django.templatetags.static import static
    from django.http import JsonResponse
    
    # Try to import SystemSetting for the main site logo
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

    # 3. Match the domain name to a company (for custom domains like fieldmax.shop)
    if not company:
        host = request.get_host().split(':')[0] # e.g., 'fieldmax.shop' or 'ronosystems.onrender.com'
        try:
            # Check custom domain first
            company = Company.objects.filter(custom_domain__iexact=host).first()
            
            # Fallback: If host contains 'fieldmax', find company named 'fieldmax'
            if not company and 'fieldmax' in host:
                company = Company.objects.filter(display_name__icontains='fieldmax').first()
        except Exception:
            pass

    # ============================================
    # BUILD MANIFEST DATA
    # ============================================
    
    # Defaults (Main Site)
    company_name = "RONOSYSTEMS"
    icon_192 = request.build_absolute_uri(static('images/icon-192.png'))
    icon_512 = request.build_absolute_uri(static('images/icon-512.png'))

    if company:
        # === TENANT LOGIC (e.g., fieldmax.shop) ===
        if company.display_name:
            company_name = company.display_name.upper()
            
        if company.logo:
            try:
                # Get the raw URL (Cloudinary or local)
                raw_logo = company.logo_url if hasattr(company, 'logo_url') and company.logo_url else company.logo.url
                
                # If Cloudinary: Force exact 192x192 and 512x512 sizes in PNG format
                if 'cloudinary' in raw_logo:
                    icon_192 = raw_logo.replace('/upload/', '/upload/w_192,h_192,c_fill,f_png/')
                    icon_512 = raw_logo.replace('/upload/', '/upload/w_512,h_512,c_fill,f_png/')
                # If local PNG: Use it for both (assuming it's high-res enough)
                elif raw_logo.endswith('.png'):
                    icon_192 = raw_logo
                    icon_512 = raw_logo
            except Exception:
                pass # Fallback to default static icons
    else:
        # === MAIN SITE LOGIC (ronosystems.onrender.com) ===
        if SystemSetting:
            try:
                # Get the main site logo from your settings app
                site_logo = SystemSetting.get_setting('SITE_LOGO_URL', '')
                if site_logo:
                    if 'cloudinary' in site_logo:
                        icon_192 = site_logo.replace('/upload/', '/upload/w_192,h_192,c_fill,f_png/')
                        icon_512 = site_logo.replace('/upload/', '/upload/w_512,h_512,c_fill,f_png/')
                    elif site_logo.endswith('.png'):
                        icon_192 = site_logo
                        icon_512 = site_logo
            except Exception:
                pass


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
        
        # Dynamic Icons (Safely resized for PWABuilder)
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
        
        # Screenshots (Required by PWABuilder)
        "screenshots": [
            {
                "src": request.build_absolute_uri(static('images/screenshot-wide.png')),
                "sizes": "1280x720",
                "type": "image/png",
                "form_factor": "wide",
                "label": "Dashboard view"
            },
            {
                "src": request.build_absolute_uri(static('images/screenshot-narrow.png')),
                "sizes": "720x1280",
                "type": "image/png",
                "form_factor": "narrow",
                "label": "Mobile view"
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