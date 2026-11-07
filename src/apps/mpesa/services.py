import base64
import logging
from datetime import datetime
from decimal import Decimal
import requests
from django.core.cache import cache
from .models import MpesaConfig

logger = logging.getLogger(__name__)
TOKEN_CACHE_PREFIX = 'mpesa_token_'
TOKEN_CACHE_SECONDS = 3000

def normalise_phone(raw: str) -> str:
    if not raw: return ''
    digits = ''.join(c for c in str(raw) if c.isdigit())
    if digits.startswith('254') and len(digits) == 12: return digits
    if digits.startswith('0') and len(digits) == 10: return '254' + digits[1:]
    if digits.startswith('7') and len(digits) == 9: return '254' + digits
    if digits.startswith('1') and len(digits) == 9: return '254' + digits
    return digits

def _daraja_base_url(cfg: MpesaConfig) -> str:
    return 'https://api.safaricom.co.ke' if cfg.environment == 'production' else 'https://sandbox.safaricom.co.ke'

def _daraja_tx_type(cfg: MpesaConfig) -> str:
    return 'CustomerBuyGoodsOnline' if cfg.shortcode_type == 'till' else 'CustomerPayBillOnline'

def _timestamp() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S')

def _password(shortcode: str, passkey: str, timestamp: str) -> str:
    return base64.b64encode(f'{shortcode}{passkey}{timestamp}'.encode()).decode()

def get_access_token(cfg: MpesaConfig) -> str:
    cache_key = f'{TOKEN_CACHE_PREFIX}{cfg.shortcode}'
    cached = cache.get(cache_key)
    if cached: return cached
    url = f'{_daraja_base_url(cfg)}/oauth/v1/generate?grant_type=client_credentials'
    auth = base64.b64encode(f'{cfg.consumer_key}:{cfg.consumer_secret}'.encode()).decode()
    resp = requests.get(url, headers={'Authorization': f'Basic {auth}'}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    token = data.get('access_token')
    if not token: raise RuntimeError(f'Daraja did not return an access token: {data}')
    cache.set(cache_key, token, TOKEN_CACHE_SECONDS)
    return token

def send_stk_push(cfg: MpesaConfig, phone: str, amount, account_reference: str = '', description: str = 'POS Payment') -> dict:
    phone = normalise_phone(phone)
    if not phone or len(phone) != 12: raise ValueError(f'Invalid phone number: {phone!r}')
    amount_int = int(Decimal(str(amount)))
    if amount_int <= 0: raise ValueError('Amount must be greater than 0.')
    token = get_access_token(cfg)
    ts = _timestamp()
    pw = _password(cfg.shortcode, cfg.passkey, ts)
    url = f'{_daraja_base_url(cfg)}/mpesa/stkpush/v1/processrequest'
    ref = (account_reference or cfg.account_reference or 'POS-SALE')[:12]
    desc = (description or 'POS Payment')[:13]
    body = {
        'BusinessShortCode': cfg.shortcode, 'Password': pw, 'Timestamp': ts,
        'TransactionType': _daraja_tx_type(cfg), 'Amount': amount_int,
        'PartyA': phone, 'PartyB': cfg.shortcode, 'PhoneNumber': phone,
        'CallBackURL': cfg.callback_url, 'AccountReference': ref, 'TransactionDesc': desc,
    }
    resp = requests.post(url, json=body, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, timeout=20)
    data = resp.json()
    if str(data.get('ResponseCode')) != '0':
        raise RuntimeError(data.get('ResponseDescription') or data.get('errorMessage') or 'STK push rejected by Daraja.')
    return data

def query_stk_status(cfg: MpesaConfig, checkout_request_id: str) -> dict:
    token = get_access_token(cfg)
    ts = _timestamp()
    pw = _password(cfg.shortcode, cfg.passkey, ts)
    url = f'{_daraja_base_url(cfg)}/mpesa/stkpushquery/v1/query'
    body = {'BusinessShortCode': cfg.shortcode, 'Password': pw, 'Timestamp': ts, 'CheckoutRequestID': checkout_request_id}
    resp = requests.post(url, json=body, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, timeout=20)
    return resp.json()

# ============================================
# PROVIDER FACTORY
# ============================================
def get_provider(cfg):
    from .providers.daraja import DarajaProvider
    from .providers.kopokopo import KopokopoProvider
    if cfg.provider == 'kopokopo':
        return KopokopoProvider(cfg)
    return DarajaProvider(cfg)

def initiate_payment(cfg, *, phone, amount, account_reference='', description='POS Payment', callback_url=None):
    provider = get_provider(cfg)
    return provider.initiate_payment(
        phone=phone, amount=amount,
        account_reference=account_reference,
        description=description,
        callback_url=callback_url or cfg.callback_url,
    )

def query_payment(cfg, *, provider_ref):
    return get_provider(cfg).query_payment(provider_ref=provider_ref)

def parse_webhook(cfg, request):
    return get_provider(cfg).parse_webhook(request)