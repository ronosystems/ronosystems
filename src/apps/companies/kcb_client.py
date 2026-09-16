"""
KCB Buni API Client
Handles OAuth token generation and STK Push requests.
"""

import base64
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class KCBClient:
    """KCB Buni API wrapper."""

    def __init__(self):
        self.base_url = settings.KCB_BASE_URL
        self.consumer_key = settings.KCB_CONSUMER_KEY
        self.consumer_secret = settings.KCB_CONSUMER_SECRET

    # ============================================
    # 1. OAUTH — Get access token
    # ============================================
    def get_access_token(self):
        """
        Generate a Bearer token using HTTP Basic Auth.
        Token is valid for ~1 hour (returned expires_in).
        """
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError('KCB_CONSUMER_KEY and KCB_CONSUMER_SECRET must be set.')

        # Basic Auth: base64("key:secret")
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }

        url = f'{self.base_url}/token?grant_type=client_credentials'
        logger.info(f"KCB OAuth → POST {url}")

        response = requests.post(url, headers=headers, timeout=15)

        if response.status_code != 200:
            logger.error(f"KCB OAuth failed ({response.status_code}): {response.text}")
            raise Exception(f'OAuth failed ({response.status_code}): {response.text}')

        data = response.json()
        token = data.get('access_token')
        if not token:
            raise Exception(f'OAuth response missing access_token: {data}')

        logger.info('✅ KCB access token obtained')
        return token

    # ============================================
    # 2. STK PUSH — Send payment prompt
    # ============================================
    def stk_push(self, phone_number, amount, invoice_number,
                 callback_url=None, description='Payment'):
        """
        Send an STK Push to a customer's phone.

        Args:
            phone_number: e.g. "254722527955" (no +, no spaces)
            amount: Decimal/int — KES amount
            invoice_number: Unique reference for this transaction
            callback_url: Where KCB sends the final result
            description: Short description shown on the prompt

        Returns:
            dict with the KCB response
        """
        token = self.get_access_token()

        # Normalize phone: strip +, spaces
        phone = str(phone_number).replace('+', '').replace(' ', '').strip()
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        if not phone.startswith('254'):
            phone = '254' + phone

        callback_url = callback_url or settings.KCB_CALLBACK_URL

        payload = {
            'phoneNumber': phone,
            'amount': str(amount),
            'invoiceNumber': invoice_number,
            'sharedShortCode': True,          # Use KCB's shared short code
            'orgShortCode': '',
            'orgPassKey': '',
            'transactionDescription': description,
            'callbackUrl': callback_url,
        }

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        url = f'{self.base_url}{settings.KCB_STK_ENDPOINT}'
        logger.info(f"KCB STK Push → POST {url} | phone={phone} | amount={amount}")

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        try:
            data = response.json()
        except Exception:
            data = {'raw': response.text}

        if response.status_code not in (200, 201):
            logger.error(f"KCB STK Push failed ({response.status_code}): {data}")
            raise Exception(
                f"STK Push failed ({response.status_code}): "
                f"{data.get('message') or data.get('errorMessage') or data}"
            )

        logger.info(f"✅ KCB STK Push sent: {data}")
        return data