# apps/mpesa/providers/daraja.py
from .base import BaseProvider
from ..services import send_stk_push, query_stk_status
import json

class DarajaProvider(BaseProvider):
    def initiate_payment(self, *, phone, amount, account_reference, description, callback_url):
        # Use existing service
        data = send_stk_push(
            self.cfg, phone, amount, 
            account_reference=account_reference, 
            description=description
        )
        return {
            'provider_ref': data['CheckoutRequestID'],
            'raw': data
        }

    def query_payment(self, *, provider_ref):
        daraja = query_stk_status(self.cfg, provider_ref)
        code = str(daraja.get('ResultCode', ''))
        
        status = 'pending'
        if code == '0':
            status = 'success'
        elif code in ('1032', '1037', '2001'):
            status = 'failed'

        return {
            'status': status,
            'code': daraja.get('MpesaReceiptNumber', ''),
            'amount': float(daraja.get('Amount', 0)),
            'phone': daraja.get('PhoneNumber', ''),
            'raw': daraja
        }

    def parse_webhook(self, request):
        data = json.loads(request.body.decode('utf-8') or '{}')
        stk = data.get('Body', {}).get('stkCallback', {})
        meta = {i['Name']: i.get('Value') for i in (stk.get('CallbackMetadata') or {}).get('Item', [])}
        
        return {
            'provider_ref': stk.get('CheckoutRequestID'),
            'status': 'success' if str(stk.get('ResultCode')) == '0' else 'failed',
            'code': meta.get('MpesaReceiptNumber', ''),
            'amount': float(meta.get('Amount', 0)),
            'phone': str(meta.get('PhoneNumber', '')),
            'first_name': meta.get('FirstName', ''),
            'middle_name': meta.get('MiddleName', ''),
            'last_name': meta.get('LastName', ''),
            'raw': data
        }