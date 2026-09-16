# apps/companies/kopokopo.py

import logging
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class KopoKopoError(Exception):
    pass


def _base_url():
    """Sandbox vs production based on settings.KOPOKOPO_ENV."""
    env = getattr(settings, 'KOPOKOPO_ENV', 'sandbox').lower()
    if env == 'production':
        return 'https://api.kopokopo.com'
    return 'https://sandbox.kopokopo.com'


def get_access_token():
    """
    Fetch an OAuth 2.0 access token from Kopo Kopo.
    
    Token lifetime is 3600 seconds (1 hour) [citation:2].
    Cached for 55 minutes to avoid unnecessary requests.
    """
    cached = cache.get('kopokopo_access_token')
    if cached:
        return cached

    url = f'{_base_url()}/oauth/token'
    payload = {
        'client_id': settings.KOPOKOPO_CLIENT_ID,
        'client_secret': settings.KOPOKOPO_CLIENT_SECRET,
        'grant_type': 'client_credentials',
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'YourApp/1.0',
    }

    resp = requests.post(url, data=payload, headers=headers, timeout=15)

    if resp.status_code != 200:
        logger.error("Kopo Kopo OAuth failed: %s %s", resp.status_code, resp.text)
        raise KopoKopoError(f"OAuth failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    token = data.get('access_token')
    expires_in = int(data.get('expires_in', 3600))

    if not token:
        raise KopoKopoError(f"No access_token in response: {data}")

    # Cache for 55 minutes (token lives 1 hour)
    cache.set('kopokopo_access_token', token, timeout=expires_in - 300)
    return token


def _normalize_phone(phone):
    """
    Convert '0712345678', '+254712345678', '254712345678'
    into '+254712345678' (Kopo Kopo expects +254 format) [citation:6].
    """
    p = str(phone).strip().replace(' ', '').replace('-', '')
    if p.startswith('0'):
        p = '+254' + p[1:]
    elif p.startswith('254'):
        p = '+' + p
    elif p.startswith('7') or p.startswith('1'):
        p = '+254' + p
    elif not p.startswith('+'):
        p = '+' + p
    return p


def initiate_stk_push(first_name, last_name, phone, email, amount,
                      account_reference, description, callback_url, till_number=None):
    """
    Send a real STK Push request via Kopo Kopo.
    
    Returns the parsed JSON response (contains the Location URL for status polling)
    or raises KopoKopoError.
    
    Reference: https://developers.kopokopo.com/guides/receive-money/mpesa-stk.html [citation:6]
    """
    token = get_access_token()

    payload = {
        'payment_channel': 'M-PESA STK Push',
        'till_number': till_number or settings.KOPOKOPO_TILL_NUMBER,
        'subscriber': {
            'first_name': first_name,
            'last_name': last_name,
            'phone_number': _normalize_phone(phone),
            'email': email,
        },
        'amount': {
            'currency': 'KES',
            'value': int(amount),
        },
        'metadata': {
            'reference': account_reference,
            'notes': description,
        },
        '_links': {
            'callback_url': callback_url,
        },
    }

    url = f'{_base_url()}/api/v2/incoming_payments'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'YourApp/1.0',
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)

    logger.info("Kopo Kopo STK push response: %s %s", resp.status_code, resp.text)

    if resp.status_code not in (200, 201):
        raise KopoKopoError(
            f"STK push failed ({resp.status_code}): {resp.text}"
        )

    # Kopo Kopo returns a Location header pointing to the payment resource
    location_url = resp.headers.get('Location')
    data = resp.json() if resp.text else {}

    return {
        'location_url': location_url,
        'response': data,
    }


def query_payment_status(location_url):
    """
    Query the status of an STK Push request using the Location URL
    returned from initiate_stk_push() [citation:1].
    """
    token = get_access_token()

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }

    resp = requests.get(location_url, headers=headers, timeout=15)

    if resp.status_code != 200:
        raise KopoKopoError(f"Status query failed ({resp.status_code}): {resp.text}")

    return resp.json()