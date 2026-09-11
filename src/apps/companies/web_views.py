# apps/companies/web_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect, csrf_exempt
import json
import uuid

from .models import Company, BusinessType
from apps.plans.models import Plan, Subscription


# ============================================
# HELPERS
# ============================================

def _parse_dt(value):
    """Parse a datetime-local string (e.g. '2026-09-11T14:30') into aware datetime."""
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _resolve_plan(plan_id):
    """Return the Plan object or None."""
    if not plan_id:
        return None
    return Plan.objects.filter(pk=plan_id).first()


def _sync_company_from_subscription(company, plan, start_dt, end_dt, status):
    """
    Update Company.plan + subscription dates and keep the Subscription row in sync.
    Prefers the existing active row, else the latest row, else creates a new one.
    """
    company.plan = plan
    company.subscription_start = start_dt
    company.subscription_end = end_dt
    company.save(update_fields=['plan', 'subscription_start', 'subscription_end'])

    if not plan:
        return None

    target = (
        company.subscriptions.filter(status='active').order_by('-created_at').first()
        or company.subscriptions.order_by('-created_at').first()
    )

    if target:
        target.plan = plan
        target.start_date = start_dt or target.start_date
        target.end_date = end_dt
        if status:
            target.status = status
        target.save()
        return target

    return Subscription.objects.create(
        company=company,
        plan=plan,
        start_date=start_dt or timezone.now(),
        end_date=end_dt,
        status=status or 'active',
    )


def _subscription_is_valid(sub):
    """True if the subscription row currently grants access."""
    if not sub:
        return False
    if sub.status != 'active':
        return False
    if sub.end_date and timezone.now() > sub.end_date:
        return False
    return True


# ============================================
# SUBSCRIPTION EXPIRED LANDING PAGE
# ============================================

@login_required
def subscription_expired(request):
    """Landing page for users whose company subscription has expired."""
    company = getattr(request.user, 'company', None)
    sub = company.latest_subscription if company else None

    context = {
        'company': company,
        'subscription': sub,
        'days_since_expiry': (
            (timezone.now() - sub.end_date).days
            if sub and sub.end_date else None
        ),
        'page_title': 'Subscription Expired',
        'page_subtitle': 'Your subscription has ended',
    }
    return render(request, 'companies/subscription_expired.html', context)


# ============================================
# COMPANY LIST
# ============================================

@login_required
@staff_member_required
def company_list(request):
    """List all companies with plan details."""
    companies = (
        Company.objects
        .select_related('plan', 'business_type')
        .prefetch_related('subscriptions__plan')
        .order_by('-created_at')
    )

    total_companies = companies.count()
    active_companies = companies.filter(is_active=True).count()
    inactive_companies = companies.filter(is_active=False).count()
    expired_companies = companies.filter(
        subscriptions__status='expired',
    ).distinct().count()

    context = {
        'companies': companies,
        'total_companies': total_companies,
        'active_companies': active_companies,
        'inactive_companies': inactive_companies,
        'expired_companies': expired_companies,
        'page_title': 'Companies',
        'page_subtitle': 'Manage all companies',
    }
    return render(request, 'companies/list.html', context)


# ============================================
# COMPANY CREATE
# ============================================

@login_required
@staff_member_required
def company_create(request):
    """Create a new company + initial subscription."""
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')

    if request.method == 'POST':
        name = request.POST.get('name')
        business_type_id = request.POST.get('business_type')
        plan_id = request.POST.get('plan')

        start_raw = request.POST.get('subscription_start')
        end_raw = request.POST.get('subscription_end')
        sub_status = request.POST.get('subscription_status', 'active')

        if not name:
            messages.error(request, 'Company name is required.')
            return render(request, 'companies/create.html', {
                'business_types': business_types,
                'plans': plans,
                'form_data': request.POST,
            })

        try:
            plan = _resolve_plan(plan_id)
            start_dt = _parse_dt(start_raw) or timezone.now()
            end_dt = _parse_dt(end_raw)

            company = Company.objects.create(
                name=name,
                business_type_id=business_type_id or None,
                registration_number=request.POST.get('registration_number', ''),
                address=request.POST.get('address', ''),
                city=request.POST.get('city', ''),
                state=request.POST.get('state', ''),
                country=request.POST.get('country', ''),
                postal_code=request.POST.get('postal_code', ''),
                email=request.POST.get('email', ''),
                phone=request.POST.get('phone', ''),
                website=request.POST.get('website', ''),
                plan=plan,
                subscription_start=start_dt,
                subscription_end=end_dt,
                created_by=request.user,
                is_active=True,
                status='active',
            )

            if plan:
                Subscription.objects.create(
                    company=company,
                    plan=plan,
                    start_date=start_dt,
                    end_date=end_dt,
                    status=sub_status,
                )

            messages.success(request, f'Company "{name}" created successfully!')
            return redirect('companies:company-detail', pk=company.pk)

        except Exception as e:
            messages.error(request, f'Error creating company: {str(e)}')

    context = {
        'business_types': business_types,
        'plans': plans,
        'page_title': 'Create Company',
        'page_subtitle': 'Add a new company',
    }
    return render(request, 'companies/create.html', context)


# ============================================
# COMPANY DETAIL
# ============================================

@login_required
@staff_member_required
def company_detail(request, pk):
    """View company details."""
    company = get_object_or_404(
        Company.objects.select_related('plan', 'business_type'),
        pk=pk,
    )

    employee_count = company.users.count()
    subscription = company.active_subscription
    limits = company.limits
    features = company.plan_features

    employee_usage_pct = 0
    if limits.get('employees'):
        employee_usage_pct = min(
            100,
            int((employee_count / limits['employees']) * 100),
        )

    context = {
        'company': company,
        'employee_count': employee_count,
        'plan': company.current_plan,
        'subscription': subscription,
        'limits': limits,
        'features': features,
        'employee_usage_pct': employee_usage_pct,
        'page_title': company.name,
        'page_subtitle': 'Company details',
    }
    return render(request, 'companies/detail.html', context)


# ============================================
# COMPANY EDIT
# ============================================

@login_required
@staff_member_required
def company_edit(request, pk):
    """Edit a company + its subscription."""
    company = get_object_or_404(Company, pk=pk)
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')

    if request.method == 'POST':
        name = request.POST.get('name')
        business_type_id = request.POST.get('business_type')
        plan_id = request.POST.get('plan')
        is_active = request.POST.get('is_active') == 'on'

        start_raw = request.POST.get('subscription_start')
        end_raw = request.POST.get('subscription_end')
        sub_status = request.POST.get('subscription_status', 'active')

        # ---------- Validate ----------
        if not name:
            messages.error(request, 'Company name is required.')
            return render(request, 'companies/edit.html', {
                'company': company,
                'business_types': business_types,
                'plans': plans,
                'form_data': request.POST,
            })

        try:
            # ---------- Update scalar fields ----------
            company.name = name
            company.business_type_id = business_type_id or None
            company.registration_number = request.POST.get('registration_number', '')
            company.address = request.POST.get('address', '')
            company.city = request.POST.get('city', '')
            company.state = request.POST.get('state', '')
            company.country = request.POST.get('country', '')
            company.postal_code = request.POST.get('postal_code', '')
            company.email = request.POST.get('email', '')
            company.phone = request.POST.get('phone', '')
            company.website = request.POST.get('website', '')

            # ---------- Sync is_active ↔ status ----------
            if is_active:
                if company.status in ('inactive', ''):
                    company.status = 'active'
                company.is_active = True
            else:
                company.status = 'inactive'
                company.is_active = False

            # ---------- Plan + subscription ----------
            new_plan = _resolve_plan(plan_id)
            start_dt = _parse_dt(start_raw)
            end_dt = _parse_dt(end_raw)

            _sync_company_from_subscription(
                company=company,
                plan=new_plan,
                start_dt=start_dt,
                end_dt=end_dt,
                status=sub_status,
            )

            # ---------- Consistency check ----------
            latest = company.latest_subscription
            sub_valid = _subscription_is_valid(latest)

            if is_active and not sub_valid:
                messages.warning(
                    request,
                    'Company set to Active, but the subscription is not currently '
                    'valid. Adjust the subscription dates or status to fully '
                    'restore access.'
                )

            company.save()
            messages.success(request, f'Company "{name}" updated successfully!')
            return redirect('companies:company-detail', pk=company.pk)

        except Exception as e:
            messages.error(request, f'Error updating company: {str(e)}')

    context = {
        'company': company,
        'business_types': business_types,
        'plans': plans,
        'page_title': 'Edit Company',
        'page_subtitle': f'Editing {company.name}',
    }
    return render(request, 'companies/edit.html', context)


# ============================================
# COMPANY DELETE
# ============================================

@login_required
@staff_member_required
def company_delete(request, pk):
    """Delete a company."""
    company = get_object_or_404(Company, pk=pk)

    if request.method == 'POST':
        try:
            name = company.name
            company.delete()
            messages.success(request, f'Company "{name}" deleted successfully!')
            return redirect('companies:company-list')
        except Exception as e:
            messages.error(request, f'Error deleting company: {str(e)}')

    context = {
        'company': company,
        'page_title': 'Delete Company',
        'page_subtitle': f'Confirm deletion of {company.name}',
    }
    return render(request, 'companies/delete.html', context)


# ============================================
# COMPANY PAYMENTS
# ============================================

@login_required
def company_payments(request, pk):
    """
    Renewal / payment page.
    Middleware MUST exempt this URL, otherwise users get stuck in a loop.
    """
    company = get_object_or_404(Company, pk=pk)

    if not request.user.is_superuser:
        if getattr(request.user, 'company_id', None) != company.id:
            messages.error(request, "You don't have access to this payment page.")
            return redirect('subscription-expired')

    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')

    context = {
        'company': company,
        'plans': plans,
        'current_subscription': company.latest_subscription,
        'page_title': 'Renew Subscription',
        'page_subtitle': company.name,
    }
    return render(request, 'companies/payments.html', context)


# ============================================
# M-PESA STK PUSH — INITIATE
# ============================================

@login_required
@require_POST
def company_payments_initiate(request, pk):
    """
    Receives plan_id + phone, sends an M-Pesa STK Push.
    Returns JSON: { success, reference, message }.
    """
    company = get_object_or_404(Company, pk=pk)

    if not request.user.is_superuser:
        if getattr(request.user, 'company_id', None) != company.id:
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    try:
        payload = json.loads(request.body.decode() or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

    plan_id = payload.get('plan_id')
    phone = (payload.get('phone') or '').strip()

    if not plan_id or not phone:
        return JsonResponse(
            {'success': False, 'error': 'Plan and phone are required.'},
            status=400,
        )

    plan = get_object_or_404(Plan, pk=plan_id)

    # ---------- TODO: Replace stub with real Daraja call ----------
    reference = f"STUB-{uuid.uuid4().hex[:12].upper()}"

    Subscription.objects.create(
        company=company,
        plan=plan,
        start_date=timezone.now(),
        end_date=None,
        status='pending',
        payment_method='mpesa',
        payment_reference=reference,
    )

    request.session[f'mpesa_ref_{reference}'] = {
        'checkout_request_id': reference,
        'company_id': company.id,
        'plan_id': plan.id,
        'created_at': timezone.now().isoformat(),
    }

    return JsonResponse({
        'success': True,
        'reference': reference,
        'message': f'STK Push sent to {phone}. Enter your PIN.',
    })


# ============================================
# M-PESA STK PUSH — STATUS POLL
# ============================================

@login_required
@require_GET
def company_payments_status(request, pk):
    """
    Poll payment status. Frontend hits this every 3s.
    Returns JSON: { status: 'pending'|'success'|'failed'|'cancelled', message, reference }
    """
    company = get_object_or_404(Company, pk=pk)
    reference = request.GET.get('ref', '').strip()

    if not reference:
        return JsonResponse({'status': 'failed', 'message': 'Missing reference.'})

    sub = Subscription.objects.filter(
        company=company,
        payment_reference=reference,
    ).order_by('-created_at').first()

    if not sub:
        return JsonResponse({'status': 'failed', 'message': 'Unknown reference.'})

    if sub.status == 'active':
        return JsonResponse({
            'status': 'success',
            'reference': reference,
            'message': 'Payment confirmed.',
        })

    if sub.status in ('cancelled', 'expired'):
        return JsonResponse({
            'status': 'failed',
            'reference': reference,
            'message': 'Payment was cancelled or failed.',
        })

    return JsonResponse({
        'status': 'pending',
        'reference': reference,
    })


# ============================================
# M-PESA STK PUSH — CALLBACK
# ============================================

@csrf_exempt
@require_POST
def company_payments_callback(request, pk):
    """
    M-Pesa callback endpoint. Safaricom POSTs here after the STK push
    is completed (success or failure). CSRF-exempt because Safaricom
    won't send a token — validate source IP in production.
    """
    company = get_object_or_404(Company, pk=pk)

    try:
        payload = json.loads(request.body.decode() or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid JSON'})

    stk = payload.get('Body', {}).get('stkCallback', {})
    checkout_id = stk.get('CheckoutRequestID')
    result_code = stk.get('ResultCode')

    sub = Subscription.objects.filter(
        payment_reference=checkout_id,
        company=company,
    ).first()

    if not sub:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Unknown reference'})

    if str(result_code) == '0':
        # SUCCESS
        sub.status = 'active'
        sub.save(update_fields=['status'])

        company.plan = sub.plan
        company.subscription_start = sub.start_date
        company.subscription_end = sub.end_date
        company.status = 'active'
        company.is_active = True
        company.save(update_fields=[
            'plan', 'subscription_start', 'subscription_end',
            'status', 'is_active',
        ])
    else:
        # FAILED / CANCELLED
        sub.status = 'cancelled'
        sub.save(update_fields=['status'])

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Received'})