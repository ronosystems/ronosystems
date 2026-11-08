# apps/mpesa/providers/kopokopo.py
import base64
import logging
import json
import hmac
import hashlib
import requests
from decimal import Decimal
from django.core.cache import cache
from .base import BaseProvider
from ..services import normalise_phone

logger = logging.getLogger(__name__)

KOPOKOPO_BASE = 'https://api.kopokopo.com'
TOKEN_CACHE_PREFIX = 'kopokopo_token_'

class KopokopoProvider(BaseProvider):
    def _get_token(self):
        key = f'{TOKEN_CACHE_PREFIX}{self.cfg.kopokopo_client_id}'
        tok = cache.get(key)
        if tok:
            return tok
            
        auth = base64.b64encode(
            f'{self.cfg.kopokopo_client_id}:{self.cfg.kopokopo_client_secret}'.encode()
        ).decode()
        
        r = requests.post(
            f'{KOPOKOPO_BASE}/oauth/token',
            headers={'Authorization': f'Basic {auth}'},
            data={'grant_type': 'client_credentials'},
            timeout=15,
        )
        
        try:
            data = r.json()
        except Exception:
            raise RuntimeError(f"Kopokopo Auth failed ({r.status_code}): {r.text[:200]}")
            
        r.raise_for_status()
        tok = data.get('access_token')
        if not tok:
            raise RuntimeError(f"Kopokopo Auth returned no token: {data}")
            
        cache.set(key, tok, max(int(data.get('expires_in', 3600)) - 60, 60))
        return tok

    def initiate_payment(self, *, phone, amount, account_reference, description, callback_url):
        phone = normalise_phone(phone)
        headers = {
            'Authorization': f'Bearer {self._get_token()}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        body = {
            'payment_channel': 'M-PESA STK Push',
            'till_number': self.cfg.kopokopo_till_number,
            'subscriber': {
                'first_name': 'Customer',
                'last_name': 'Payment',
                'phone_number': phone,
                'email': 'customer@kopokopo.com'
            },
            'amount': {
                'currency': 'KES',
                'value': int(Decimal(str(amount)))
            },
            'metadata': {
                'account_reference': account_reference[:50],
                'description': description[:100]
            },
            '_links': {
                'callback_url': callback_url
            }
        }
        
        r = requests.post(f'{KOPOKOPO_BASE}/api/v1/incoming_payments', json=body, headers=headers, timeout=20)
        
        # 👈 Handle Kopokopo's empty 201 response
        if not r.text:
            logger.warning(f"KOPOKOPO EMPTY RESPONSE (Status {r.status_code}). Assuming accepted.")
            # Return a temporary ID. The webhook handler will match it by phone/amount.
            import time
            return {
                'provider_ref': f"pending_{phone}_{int(time.time())}",
                'raw': {'status': 'pending_webhook'}
            }
        
        try:
            data = r.json()
        except Exception:
            logger.error(f"Kopokopo returned non-JSON: {r.status_code} - {r.text[:500]}")
            raise RuntimeError(f"Kopokopo API error ({r.status_code}): {r.text[:200]}")
        
        if r.status_code not in (200, 201):
            logger.error(f"Kopokopo rejected request: {r.status_code} - {data}")
            error_msg = data.get('error') or data.get('message') or str(data)
            raise RuntimeError(f"Kopokopo rejected request: {error_msg}")
            
        return {
            'provider_ref': data.get('id') or data.get('resourceId'),
            'raw': data
        }

    def query_payment(self, *, provider_ref):
        r = requests.get(
            f'{KOPOKOPO_BASE}/api/v1/incoming_payments/{provider_ref}',
            headers={'Authorization': f'Bearer {self._get_token()}', 'Accept': 'application/json'},
            timeout=20,
        )
        
        try:
            d = r.json()
        except Exception:
            logger.warning(f"Kopokopo query returned non-JSON: {r.status_code}")
            return {'status': 'pending', 'code': '', 'amount': 0, 'phone': '', 'raw': {}}

        raw_status = (d.get('status') or '').lower()
        status = 'success' if raw_status == 'success' else ('failed' if raw_status == 'failed' else 'pending')
        
        return {
            'status': status,
            'code': (d.get('transaction_reference') or '').upper(),
            'amount': float((d.get('amount') or {}).get('value') or 0),
            'phone': ((d.get('subscriber') or {}).get('phone_number') or '').replace('+', ''),
            'raw': d
        }


    def parse_webhook(self, request):
        raw_body = request.body
        sig = request.headers.get('X-Kopokopo-Signature', '')
        
        if self.cfg.kopokopo_webhook_secret and sig:
            expected = base64.b64encode(
                hmac.new(self.cfg.kopokopo_webhook_secret.encode(), raw_body, hashlib.sha256).digest()
            ).decode()
            if not hmac.compare_digest(sig, expected):
                logger.warning(f"Kopokopo Signature mismatch for {self.cfg.company.name}.")

        try:
            data = json.loads(raw_body.decode('utf-8') or '{}')
        except Exception:
            raise ValueError("Invalid JSON in Kopokopo webhook")

        # 👈 Get the type from the 'data' object, not the root
        event_data = data.get('data', {})
        event_type = event_data.get('type', '') 
        attributes = event_data.get('attributes', {})
        
        resource = (attributes.get('event') or {}).get('resource') or {}
        status = attributes.get('status', '').lower()

        # Handle Incoming Payment (STK Push)
        if event_type == 'incoming_payment':
            amount_obj = resource.get('amount')
            amount_val = amount_obj.get('value', 0) if isinstance(amount_obj, dict) else (amount_obj or 0)
            
            # If status is Success, Kopokopo uses "Received" inside the resource
            is_success = status == 'success' or (resource.get('status') or '').lower() == 'received'

            return {
                'provider_ref': event_data.get('id') or resource.get('id'),
                'status': 'success' if is_success else 'failed',
                'code': (resource.get('reference') or '').upper(),
                'amount': float(amount_val),
                'phone': (resource.get('sender_phone_number') or '').replace('+', ''),
                'first_name': resource.get('sender_first_name') or '',
                'middle_name': resource.get('sender_middle_name') or '',
                'last_name': resource.get('sender_last_name') or '',
                'raw': data
            }

        # Handle Buy Goods (Till)
        elif event_type == 'buygoods_transaction':
            amount_val = resource.get('amount', 0)
            if isinstance(amount_val, dict):
                amount_val = amount_val.get('value', 0)
                
            return {
                'provider_ref': resource.get('system_reference') or event_data.get('id'),
                'status': 'success' if status == 'success' else 'failed',
                'code': (resource.get('transaction_reference') or '').upper(),
                'amount': float(amount_val),
                'phone': (resource.get('sender_phone_number') or '').replace('+', ''),
                'first_name': resource.get('sender_first_name') or '',
                'middle_name': '',
                'last_name': resource.get('sender_last_name') or '',
                'raw': data
            }

        # Unknown format
        else:
            logger.error(f"Unknown Kopokopo Webhook format: {event_type}")
            return {
                'provider_ref': None,
                'status': 'pending',
                'code': '',
                'amount': 0,
                'phone': '',
                'first_name': '',
                'middle_name': '',
                'last_name': '',
                'raw': data
            }

            