from django.http import JsonResponse
from django.shortcuts import render
import base64
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

@csrf_exempt
def qz_sign(request):
    """
    Sign QZ Tray print requests so the browser doesn't get the
    'Untrusted website' prompt.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # QZ Tray sends the message to sign in the POST body
    message = request.body.decode('utf-8')

    key_path = os.path.join(settings.BASE_DIR, 'qz_keys', 'private.key')
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


# core/views.py  (or wherever your qz_sign lives)
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings as django_settings


def contact(request):
    """
    Handle GET (show form) and POST (send message).
    """
    if request.method == 'POST':
        name    = (request.POST.get('name') or '').strip()
        email   = (request.POST.get('email') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        message = (request.POST.get('message') or '').strip()

        # Basic validation
        if not name or not email or not message:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'contact.html')

        # Compose the email
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

        # Send to the address in settings, fallback to a default
        recipient = getattr(django_settings, 'CONTACT_EMAIL', None)
        if not recipient:
            # try the SystemSetting "EMAIL_FROM" address
            try:
                from apps.settings.models import SystemSetting
                recipient = SystemSetting.get_setting('EMAIL_FROM', 'support@ronosystems.com')
            except Exception:
                recipient = 'support@ronosystems.com'

        from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@ronosystems.com')

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

    # GET
    return render(request, 'contact.html')