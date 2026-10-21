import base64
import logging
from datetime import datetime
from decimal import Decimal

import requests
from django.core.cache import cache

from .models import MpesaConfig

logger = logging.getLogger(__name__)

TOKEN_CACHE_PREFIX = 'mpesa_token_'
TOKEN_CACHE_SECONDS = 3000   # Safaricom tokens last ~1h


# ============================================
# PHONE NORMALISATION
# ============================================
def normalise_phone(raw: str) -> str:
    """
    Turn '0712 345 678' / '+254 712 345 678' / '712345678'
    into '254712345678'.
    """
    if not raw:
        return ''
    digits = ''.join(c for c in str(raw) if c.isdigit())
    if digits.startswith('254') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '254' + digits[1:]
    if digits.startswith('7') and len(digits) == 9:
        return '254' + digits
    if digits.startswith('1') and len(digits) == 9:
        return '254' + digits
    return digits


# ============================================
# DARAJA PRIMITIVES
# ============================================
def _timestamp() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S')


def _password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f'{shortcode}{passkey}{timestamp}'.encode()
    return base64.b64encode(raw).decode()


def get_access_token(cfg: MpesaConfig) -> str:
    """
    Get (and cache) a Daraja access token, per config.
    Cache key includes the shortcode so multi-tenant configs don't collide.
    """
    cache_key = f'{TOKEN_CACHE_PREFIX}{cfg.shortcode}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f'{cfg.base_url}/oauth/v1/generate?grant_type=client_credentials'
    auth = base64.b64encode(
        f'{cfg.consumer_key}:{cfg.consumer_secret}'.encode()
    ).decode()

    resp = requests.get(
        url,
        headers={'Authorization': f'Basic {auth}'},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    token = data.get('access_token')
    if not token:
        raise RuntimeError(f'Daraja did not return an access token: {data}')

    cache.set(cache_key, token, TOKEN_CACHE_SECONDS)
    return token


# ============================================
# STK PUSH
# ============================================
def send_stk_push(cfg: MpesaConfig, phone: str, amount, account_reference: str = '',
                  description: str = 'POS Payment') -> dict:
    """
    Fire an STK push using the given config.
    Returns the raw Daraja JSON on success (with ResponseCode == '0'),
    or raises RuntimeError on failure.
    """
    phone = normalise_phone(phone)
    if not phone or len(phone) != 12:
        raise ValueError(f'Invalid phone number: {phone!r}')

    amount_int = int(Decimal(str(amount)))
    if amount_int <= 0:
        raise ValueError('Amount must be greater than 0.')

    token = get_access_token(cfg)
    ts = _timestamp()
    pw = _password(cfg.shortcode, cfg.passkey, ts)

    url = f'{cfg.base_url}/mpesa/stkpush/v1/processrequest'

    # Safaricom limits: AccountReference max 12 chars, TransactionDesc max 13 chars
    ref = (account_reference or cfg.account_reference or 'POS-SALE')[:12]
    desc = (description or 'POS Payment')[:13]

    body = {
        'BusinessShortCode': cfg.shortcode,
        'Password':          pw,
        'Timestamp':         ts,
        'TransactionType':   cfg.transaction_type,
        'Amount':            amount_int,
        'PartyA':            phone,
        'PartyB':            cfg.shortcode,
        'PhoneNumber':       phone,
        'CallBackURL':       cfg.callback_url,
        'AccountReference':  ref,
        'TransactionDesc':   desc,
    }

    resp = requests.post(
        url,
        json=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json',
        },
        timeout=20,
    )
    data = resp.json()

    if str(data.get('ResponseCode')) != '0':
        raise RuntimeError(
            data.get('ResponseDescription')
            or data.get('errorMessage')
            or 'STK push rejected by Daraja.'
        )

    return data


# ============================================
# STK QUERY  (Safaricom's own status endpoint)
# ============================================
def query_stk_status(cfg: MpesaConfig, checkout_request_id: str) -> dict:
    token = get_access_token(cfg)
    ts = _timestamp()
    pw = _password(cfg.shortcode, cfg.passkey, ts)

    url = f'{cfg.base_url}/mpesa/stkpushquery/v1/query'

    body = {
        'BusinessShortCode': cfg.shortcode,
        'Password':          pw,
        'Timestamp':         ts,
        'CheckoutRequestID': checkout_request_id,
    }

    resp = requests.post(
        url,
        json=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json',
        },
        timeout=20,
    )
    return resp.json()