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
