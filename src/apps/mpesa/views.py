import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from .models import MpesaConfig, MpesaTransaction
from .services import send_stk_push, query_stk_status

logger = logging.getLogger(__name__)


# --------------------------------------------
# Helpers
# --------------------------------------------
def _company_for_request(request):
    """
    Resolve the tenant company for the current request.
    Prefer the user's company, fall back to request.company (middleware).
    """
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and getattr(user, 'company', None):
        return user.company
    return getattr(request, 'company', None)


def _branch_for_request(request, branch_id):
    if not branch_id:
        return None
    from apps.company.models import Branch
    company = _company_for_request(request)
    if not company:
        return None
    return Branch.objects.filter(pk=branch_id, company=company).first()


def _resolve_customer_name(tx):
    """
    Return the best available name for this transaction:

      1. Name from Safaricom's callback (production only — sandbox
         usually omits FirstName/MiddleName/LastName).
      2. Name from a previous purchase on the same phone (local DB).
      3. Empty string.
    """
    # 1) Direct name from the callback
    name = (tx.customer_name or '').strip()
    if name:
        return name

    # 2) Fall back to the Customer table by phone
    if tx.phone:
        try:
            from apps.epa_shop.models import Customer
            cust = Customer.objects.filter(
                company=tx.company,
                phone=tx.phone,
            ).first()
            if cust and cust.name:
                return cust.name.strip()
        except Exception:
            logger.warning(
                'Customer lookup failed for %s', tx.phone, exc_info=True
            )

    return ''


# ============================================
# STK PUSH
# ============================================
@csrf_exempt
@require_POST
def mpesa_stk_push(request):
    payload   = json.loads(request.body.decode('utf-8') or '{}')
    phone     = str(payload.get('phone', '')).strip()
    amount    = payload.get('amount')
    branch_id = payload.get('branch_id')

    company = _company_for_request(request)
    if not company:
        return JsonResponse(
            {'success': False, 'error': 'No company in session.'},
            status=400,
        )

    branch = _branch_for_request(request, branch_id)
    cfg = MpesaConfig.for_branch(company, branch)
    if not cfg:
        return JsonResponse({
            'success': False,
            'error': 'No M-Pesa configuration found for this company/branch. '
                     'Ask your administrator to set one up.'
        }, status=400)

    try:
        data = send_stk_push(cfg, phone, amount)
    except Exception as e:
        logger.exception('STK push failed')
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    # Log the transaction, scoped to this company
    tx = MpesaTransaction.objects.create(
        company=company,
        branch=branch,
        mpesa_config=cfg,
        checkout_request_id=data['CheckoutRequestID'],
        merchant_request_id=data.get('MerchantRequestID', ''),
        phone=phone,
        amount=amount,
        status='pending',
    )

    return JsonResponse({
        'success': True,
        'checkout_request_id': data['CheckoutRequestID'],
        'transaction_id': tx.id,
    })


# ============================================
# STK STATUS
# ============================================
@require_GET
def mpesa_stk_status(request):
    request_id = request.GET.get('request_id', '').strip()
    if not request_id:
        return JsonResponse(
            {'status': 'failed', 'message': 'request_id is required.'},
            status=400,
        )

    company = _company_for_request(request)
    qs = MpesaTransaction.objects.filter(checkout_request_id=request_id)
    if company:
        qs = qs.filter(company=company)

    tx = qs.first()
    if not tx:
        return JsonResponse({'status': 'pending'})

    if tx.status == 'success':
        # Some sandbox callbacks omit MpesaReceiptNumber. If we have no code
        # yet, try Daraja's STK query — it usually has it.
        if not tx.mpesa_code and tx.mpesa_config:
            try:
                daraja = query_stk_status(tx.mpesa_config, request_id)
                receipt = daraja.get('MpesaReceiptNumber', '')
                if receipt:
                    tx.mpesa_code = receipt
                    tx.save(update_fields=['mpesa_code', 'updated_at'])
            except Exception:
                logger.warning(
                    'Receipt recovery failed for %s', request_id, exc_info=True
                )

        return JsonResponse({
            'status': 'success',
            'mpesa_code': tx.mpesa_code or '',
            'amount': float(tx.amount or 0),
            'customer_name': _resolve_customer_name(tx),
            'customer_phone': tx.phone,
        })

    if tx.status in ('failed', 'cancelled', 'timeout'):
        return JsonResponse({
            'status': tx.status,
            'message': tx.result_desc or '',
        })

    # Still pending — ask Daraja directly
    try:
        if tx.mpesa_config:
            daraja = query_stk_status(tx.mpesa_config, request_id)
            code = str(daraja.get('ResultCode', ''))

            if code == '0':
                # Persist so mpesa_confirm can find it later
                receipt = daraja.get('MpesaReceiptNumber', '') or tx.mpesa_code
                if receipt and not tx.mpesa_code:
                    tx.mpesa_code = receipt
                tx.status = 'success'
                tx.result_desc = daraja.get('ResultDesc', '')
                tx.save(update_fields=[
                    'status', 'mpesa_code', 'result_desc', 'updated_at',
                ])

                return JsonResponse({
                    'status': 'success',
                    'mpesa_code': tx.mpesa_code,
                    'amount': float(tx.amount or 0),
                    'customer_name': _resolve_customer_name(tx),   # 👈
                    'customer_phone': tx.phone,
                })

            if code in ('1032', '1037', '2001'):
                tx.status = 'failed'
                tx.result_desc = daraja.get('ResultDesc', '')
                tx.save(update_fields=['status', 'result_desc', 'updated_at'])
                return JsonResponse({
                    'status': 'failed',
                    'message': tx.result_desc,
                })

    except Exception:
        logger.warning('Daraja query failed for %s', request_id, exc_info=True)

    return JsonResponse({'status': 'pending'})


# ============================================
# CONFIRM (manual code entry)
# ============================================
@csrf_exempt
@require_POST
def mpesa_confirm(request):
    payload = json.loads(request.body.decode('utf-8') or '{}')
    code     = str(payload.get('transaction_code', '')).strip().upper()
    expected = float(payload.get('expected_amount') or 0)

    if not code:
        return JsonResponse(
            {'success': False, 'error': 'Transaction code is required.'},
            status=400,
        )

    company = _company_for_request(request)

    qs = MpesaTransaction.objects.filter(mpesa_code__iexact=code)
    if company:
        qs = qs.filter(company=company)

    tx = qs.first()
    if not tx:
        return JsonResponse({
            'success': False,
            'error': f'No transaction found for code {code}.'
        }, status=404)

    if tx.status != 'success':
        return JsonResponse({
            'success': False,
            'error': f'Transaction {code} is {tx.status}, not completed.'
        }, status=400)

    if abs(float(tx.amount) - expected) > 0.01:
        return JsonResponse({
            'success': False,
            'error': (
                f'Amount mismatch: received KSh {tx.amount}, '
                f'expected KSh {expected:.2f}.'
            )
        }, status=400)

    return JsonResponse({
        'success': True,
        'mpesa_code': tx.mpesa_code,
        'amount': float(tx.amount),
        'transaction_id': tx.id,
    })


# ============================================
# CALLBACK (from Safaricom)
# ============================================
@csrf_exempt
@require_POST
def mpesa_callback(request):
    """
    Safaricom POSTs the STK result here.

    We look up MpesaTransaction by CheckoutRequestID (globally unique
    across tenants). If not found and a shortcode is present, we resolve
    the company by shortcode and create a placeholder row.
    """
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
        stk  = data['Body']['stkCallback']
        req_id = stk.get('CheckoutRequestID')
        shortcode = stk.get('BusinessShortCode')

        tx = MpesaTransaction.objects.filter(
            checkout_request_id=req_id
        ).first()

        if not tx and shortcode and req_id:
            cfg = MpesaConfig.objects.filter(
                shortcode=str(shortcode)
            ).first()
            if cfg:
                tx = MpesaTransaction.objects.create(
                    company=cfg.company,
                    branch=cfg.branch,
                    mpesa_config=cfg,
                    checkout_request_id=req_id,
                    merchant_request_id=stk.get('MerchantRequestID', ''),
                    status='pending',
                )

        if tx is None:
            logger.warning(
                'Callback for unknown CheckoutRequestID: %s', req_id
            )
            return JsonResponse(
                {'ResultCode': 0, 'ResultDesc': 'Ignored'}
            )

        meta = {
            i['Name']: i.get('Value')
            for i in (stk.get('CallbackMetadata') or {}).get('Item', [])
        }

        tx.result_desc  = stk.get('ResultDesc', '')
        tx.raw_callback = data

        if str(stk.get('ResultCode')) == '0':
            tx.status     = 'success'
            tx.mpesa_code = meta.get('MpesaReceiptNumber', '')
            tx.amount     = meta.get('Amount', tx.amount or 0)
            tx.phone      = meta.get('PhoneNumber', tx.phone)

            # 👇 Production only — Safaricom sandbox usually omits these.
            tx.customer_first_name  = meta.get('FirstName',  '') or ''
            tx.customer_middle_name = meta.get('MiddleName', '') or ''
            tx.customer_last_name   = meta.get('LastName',   '') or ''
        else:
            tx.status = 'failed'

        tx.save()

    except Exception:
        logger.exception('Callback processing failed')

    # Always 200 so Safaricom stops retrying
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})