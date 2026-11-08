import json
import time
import logging
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from .models import MpesaConfig, MpesaTransaction
from .services import initiate_payment, query_payment, parse_webhook

logger = logging.getLogger(__name__)


# --------------------------------------------
# Helpers
# --------------------------------------------
def _company_for_request(request):
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
    name = (tx.customer_name or '').strip()
    if name:
        return name
    if tx.phone:
        try:
            from apps.epa_shop.models import Customer
            cust = Customer.objects.filter(company=tx.company, phone=tx.phone).first()
            if cust and cust.name:
                return cust.name.strip()
        except Exception:
            logger.warning('Customer lookup failed for %s', tx.phone, exc_info=True)
    return ''


# ============================================
# LINK PAYMENT TO CHAMA CONTRIBUTION / FINE
# ============================================
def _link_payment_to_chama(tx):
    if not tx or tx.status != 'success' or not tx.company:
        return
    try:
        from apps.chama.models import Contribution, Fine
        from django.utils import timezone

        reference = (getattr(tx, 'account_reference', '') or '').strip()
        if not reference:
            raw = tx.raw_callback or {}
            meta = (((raw.get('Body') or {}).get('stkCallback') or {}).get('CallbackMetadata') or {})
            items = meta.get('Item') or []
            for item in items:
                if item.get('Name') == 'AccountReference':
                    reference = str(item.get('Value') or '').strip()
                    break
        if not reference:
            return

        ref_upper = reference.upper()
        if ref_upper.startswith('C-') or ref_upper.startswith('CONTRIB-'):
            if ref_upper.startswith('CONTRIB-'):
                member_number = reference[len('CONTRIB-'):].strip()
            else:
                member_number = reference[len('C-'):].strip()
            current_month = timezone.localdate().strftime('%Y-%m')
            pending = Contribution.objects.filter(
                company=tx.company, member__member_number=member_number, period=current_month, paid=False
            ).order_by('-created_at').first()
            if pending:
                pending.paid = True
                pending.save(update_fields=['paid'])
                logger.info("Chama: contribution #%s marked paid (member=%s, code=%s)", pending.id, member_number, tx.mpesa_code)

        elif ref_upper.startswith('F-') or ref_upper.startswith('FINE-'):
            if ref_upper.startswith('FINE-'):
                member_number = reference[len('FINE-'):].strip()
            else:
                member_number = reference[len('F-'):].strip()
            pending = Fine.objects.filter(
                company=tx.company, member__member_number=member_number, is_paid=False
            ).order_by('-created_at').first()
            if pending:
                pending.is_paid = True
                pending.save(update_fields=['is_paid'])
                logger.info("Chama: fine #%s marked paid (member=%s, code=%s)", pending.id, member_number, tx.mpesa_code)

    except Exception:
        logger.warning('Chama payment linkage failed for tx %s', tx.id, exc_info=True)


# ============================================
# STK PUSH (INITIATE PAYMENT)
# ============================================
@csrf_exempt
@require_POST
def mpesa_stk_push(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload.'}, status=400)

    phone     = str(payload.get('phone', '')).strip()
    amount    = payload.get('amount')
    branch_id = payload.get('branch_id')
    account_ref = str(payload.get('account_ref', '')).strip()
    description = str(payload.get('description', '')).strip()

    company = _company_for_request(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company in session.'}, status=400)

    branch = _branch_for_request(request, branch_id)
    cfg = MpesaConfig.for_branch(company, branch)
    
    if not cfg:
        return JsonResponse({'success': False, 'error': 'No M-Pesa configuration found for this company/branch.'}, status=200) 

    try:
        data = initiate_payment(cfg, phone=phone, amount=amount, account_reference=account_ref, description=description)
    except Exception as e:
        logger.exception('Payment initiation failed')
        return JsonResponse({'success': False, 'error': str(e)}, status=200)

    tx = MpesaTransaction.objects.create(
        company=company,
        branch=branch,
        mpesa_config=cfg,
        provider=cfg.provider,
        provider_ref=data['provider_ref'],
        merchant_request_id=data['raw'].get('MerchantRequestID', '') if 'raw' in data else '',
        phone=phone,
        amount=amount,
        status='pending',
        account_reference=account_ref,
    )

    return JsonResponse({
        'success': True,
        'checkout_request_id': data['provider_ref'],
        'transaction_id': tx.id,
    })


# ============================================
# STK STATUS (POLL PAYMENT STATUS)
# ============================================
@require_GET
def mpesa_stk_status(request):
    request_id = request.GET.get('request_id', '').strip()
    if not request_id:
        return JsonResponse({'status': 'failed', 'message': 'request_id is required.'}, status=400)

    company = _company_for_request(request)
    qs = MpesaTransaction.objects.filter(provider_ref=request_id)
    if company:
        qs = qs.filter(company=company)

    tx = qs.first()
    if not tx:
        return JsonResponse({'status': 'pending'})

    if tx.status == 'success':
        if not tx.mpesa_code and tx.mpesa_config:
            try:
                parsed = query_payment(tx.mpesa_config, provider_ref=request_id)
                receipt = parsed.get('code', '')
                if receipt:
                    tx.mpesa_code = receipt
                    tx.save(update_fields=['mpesa_code', 'updated_at'])
            except Exception:
                logger.warning('Receipt recovery failed for %s', request_id, exc_info=True)

        return JsonResponse({
            'status': 'success',
            'mpesa_code': tx.mpesa_code or '',
            'amount': float(tx.amount or 0),
            'customer_name': _resolve_customer_name(tx),
            'customer_phone': tx.phone,
        })

    if tx.status in ('failed', 'cancelled', 'timeout'):
        return JsonResponse({'status': tx.status, 'message': tx.result_desc or ''})

    try:
        if tx.mpesa_config and not request_id.startswith("pending_"):
            parsed = query_payment(tx.mpesa_config, provider_ref=request_id)
            status = parsed.get('status')

            if status == 'success':
                tx.status = 'success'
                tx.mpesa_code = parsed.get('code', '') or tx.mpesa_code
                tx.result_desc = 'Success'
                tx.save(update_fields=['status', 'mpesa_code', 'result_desc', 'updated_at'])
                _link_payment_to_chama(tx)

                return JsonResponse({
                    'status': 'success',
                    'mpesa_code': tx.mpesa_code,
                    'amount': float(tx.amount or 0),
                    'customer_name': _resolve_customer_name(tx),
                    'customer_phone': tx.phone,
                })

            if status == 'failed':
                tx.status = 'failed'
                tx.result_desc = 'Payment failed'
                tx.save(update_fields=['status', 'result_desc', 'updated_at'])
                return JsonResponse({'status': 'failed', 'message': tx.result_desc})

    except Exception:
        logger.warning('Provider query failed for %s', request_id, exc_info=True)

    return JsonResponse({'status': 'pending'})


# ============================================
# CONFIRM (MANUAL CODE ENTRY)
# ============================================
@csrf_exempt
@require_POST
def mpesa_confirm(request):
    payload = json.loads(request.body.decode('utf-8') or '{}')
    code     = str(payload.get('transaction_code', '')).strip().upper()
    expected = float(payload.get('expected_amount') or 0)

    if not code:
        return JsonResponse({'success': False, 'error': 'Transaction code is required.'}, status=400)

    company = _company_for_request(request)
    qs = MpesaTransaction.objects.filter(mpesa_code__iexact=code)
    if company:
        qs = qs.filter(company=company)

    tx = qs.first()
    if not tx:
        return JsonResponse({'success': False, 'error': f'No transaction found for code {code}.'}, status=404)

    if tx.status != 'success':
        return JsonResponse({'success': False, 'error': f'Transaction {code} is {tx.status}, not completed.'}, status=400)

    _link_payment_to_chama(tx)

    if abs(float(tx.amount) - expected) > 0.01:
        return JsonResponse({'success': False, 'error': f'Amount mismatch: received KSh {tx.amount}, expected KSh {expected:.2f}.'}, status=400)

    return JsonResponse({'success': True, 'mpesa_code': tx.mpesa_code, 'amount': float(tx.amount), 'transaction_id': tx.id})


# ============================================
# SAFARICOM CALLBACK
# ============================================
@csrf_exempt
@require_POST
def mpesa_callback(request):
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
        stk  = data['Body']['stkCallback']
        req_id = stk.get('CheckoutRequestID')
        shortcode = stk.get('BusinessShortCode')

        tx = MpesaTransaction.objects.filter(provider_ref=req_id).first()

        if not tx and shortcode and req_id:
            cfg = MpesaConfig.objects.filter(shortcode=str(shortcode)).first()
            if cfg:
                tx = MpesaTransaction.objects.create(
                    company=cfg.company, branch=cfg.branch, mpesa_config=cfg, provider=cfg.provider, provider_ref=req_id,
                    merchant_request_id=stk.get('MerchantRequestID', ''), status='pending',
                )

        if tx is None:
            logger.warning('Callback for unknown CheckoutRequestID: %s', req_id)
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Ignored'})

        meta = {i['Name']: i.get('Value') for i in (stk.get('CallbackMetadata') or {}).get('Item', [])}
        tx.result_desc  = stk.get('ResultDesc', '')
        tx.raw_callback = data

        if str(stk.get('ResultCode')) == '0':
            tx.status     = 'success'
            tx.mpesa_code = meta.get('MpesaReceiptNumber', '')
            tx.amount     = meta.get('Amount', tx.amount or 0)
            tx.phone      = meta.get('PhoneNumber', tx.phone)
            tx.customer_first_name  = meta.get('FirstName',  '') or ''
            tx.customer_middle_name = meta.get('MiddleName', '') or ''
            tx.customer_last_name   = meta.get('LastName',   '') or ''
        else:
            tx.status = 'failed'

        tx.save()
        _link_payment_to_chama(tx)

    except Exception:
        logger.exception('Callback processing failed')

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})


# ============================================
# KOPOKOPO CALLBACK (WEBHOOK)
# ============================================

@csrf_exempt
@require_POST
def kopokopo_callback(request):
    try:
        company_id = request.GET.get('company_id')
        
        if company_id:
            cfg = MpesaConfig.objects.filter(provider='kopokopo', company_id=company_id, is_active=True).first()
        else:
            cfg = MpesaConfig.objects.filter(provider='kopokopo', is_active=True).first()
            
        if not cfg:
            logger.warning('Kopokopo webhook received but no active config found.')
            return JsonResponse({'status': 'ignored'})

        parsed = parse_webhook(cfg, request)
        logger.info(f"Kopokopo webhook parsed: {parsed}")

        # 1. Try exact provider_ref match
        tx = MpesaTransaction.objects.filter(provider_ref=parsed['provider_ref']).first()

        # 2. Fallback: match by company, phone, and status 'pending'
        if not tx:
            logger.warning(f"No exact match for {parsed['provider_ref']}. Searching for pending transaction by phone.")
            # Clean phone number for comparison (just in case)
            clean_phone = parsed['phone'].replace('+', '').strip()
            
            tx = MpesaTransaction.objects.filter(
                company=cfg.company,
                phone__contains=clean_phone[-9:], # Match the last 9 digits
                status='pending'
            ).order_by('-created_at').first()
            
            if tx:
                logger.info(f"Found pending transaction #{tx.id}. Updating provider_ref to {parsed['provider_ref']}.")
                tx.provider_ref = parsed['provider_ref']

        if not tx:
            logger.warning(f"Kopokopo webhook for unknown payment: {parsed['provider_ref']}")
            return JsonResponse({'status': 'ignored'})

        tx.result_desc = 'Kopokopo Webhook Received'
        tx.raw_callback = parsed['raw']

        if parsed['status'] == 'success':
            tx.status = 'success'
            tx.mpesa_code = parsed['code']
            tx.amount = Decimal(str(parsed['amount']))
            tx.phone = parsed['phone']
            tx.customer_first_name = parsed.get('first_name', '')
            tx.customer_middle_name = parsed.get('middle_name', '')
            tx.customer_last_name = parsed.get('last_name', '')
        elif parsed['status'] == 'failed':
            tx.status = 'failed'
            tx.result_desc = 'Payment failed via Kopokopo'

        tx.save()

        if tx.status == 'success':
            _link_payment_to_chama(tx)
            
            # 👈 WAKE UP THE POS
            # We don't need to do anything else here; the POS polling loop will find it.

    except Exception as e:
        logger.exception('Kopokopo callback processing failed')
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'status': 'ok'})

    