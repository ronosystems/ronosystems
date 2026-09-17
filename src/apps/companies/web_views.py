# apps/companies/web_views.py

import json
import logging
import re
import socket
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.epa_shop.models import Branch
from apps.plans.models import Plan, Subscription

from .models import Company, BusinessType, CompanyJoinRequest
from .kcb_client import KCBClient


logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================
# CONSTANTS
# ============================================

SUPPORT_SESSION_KEYS = (
    'support_mode',
    'viewing_company_id',
    'support_started_at',
    'original_user_id',
)

ASSIGNABLE_ROLES = [
    ('company_staff',    'Company Staff'),
    ('company_cashier',  'Company Cashier'),
    ('company_agent',    'Company Agent'),
    ('company_manager',  'Company Manager'),
    ('stock_controller', 'Stock Controller'),
    ('mpesa_agent',      'M-Pesa Agent'),
]

# Domain regex: matches "example.com", "sub.example.co.ke", etc.
DOMAIN_RE = re.compile(
    r'^[a-z0-9]'
    r'([a-z0-9\-]{0,61}[a-z0-9])?'
    r'(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)+$'
)


# ============================================
# HELPERS — DATES / PLANS / DOMAINS
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


def _compute_end_date(plan, start_dt=None):
    """
    Return the end_date for a plan based on its billing_cycle:
        monthly  → start + 30 days
        yearly   → start + 365 days
        lifetime → None
    """
    if not plan:
        return None
    start_dt = start_dt or timezone.now()
    if plan.billing_cycle == 'monthly':
        return start_dt + timedelta(days=30)
    if plan.billing_cycle == 'yearly':
        return start_dt + timedelta(days=365)
    return None  # lifetime


def _normalize_domain(raw):
    """
    Normalize a user-submitted domain:
      - lowercase
      - strip protocol (http:// / https://)
      - strip trailing slashes
      - strip leading 'www.'
    """
    if not raw:
        return ''
    d = raw.strip().lower()
    d = d.replace('https://', '').replace('http://', '')
    d = d.rstrip('/')
    if d.startswith('www.'):
        d = d[4:]
    return d


def _validate_domain(domain, exclude_company_id=None):
    """Return (is_valid, error_message). Empty domain is valid (means: none set)."""
    if not domain:
        return True, None

    if not DOMAIN_RE.match(domain):
        return False, f'Invalid domain format: "{domain}".'

    qs = Company.objects.filter(custom_domain__iexact=domain)
    if exclude_company_id:
        qs = qs.exclude(pk=exclude_company_id)
    if qs.exists():
        return False, f'Domain "{domain}" is already used by another company.'

    return True, None


def _sync_company_from_subscription(company, plan, start_dt, end_dt, status,
                                    renew=False, payment_method='', payment_reference=''):
    """
    Sync Company.plan + dates with a Subscription row.

    renew=False → edit the current row in place (fixing mistakes)
    renew=True  → expire the current row and create a NEW row (real renewal)
    """
    company.plan = plan
    company.subscription_start = start_dt
    company.subscription_end = end_dt
    company.save(update_fields=['plan', 'subscription_start', 'subscription_end'])

    if not plan:
        return None

    # ---------- RENEWAL: always create a new row ----------
    if renew:
        company.subscriptions.filter(status='active').update(status='expired')
        return Subscription.objects.create(
            company=company,
            plan=plan,
            start_date=start_dt or timezone.now(),
            end_date=end_dt,
            status=status or 'active',
            payment_method=payment_method,
            payment_reference=payment_reference,
        )

    # ---------- CORRECTION: edit the existing row ----------
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


def _clear_support_session(request):
    """Completely clear all support-mode session data."""
    for key in SUPPORT_SESSION_KEYS:
        request.session.pop(key, None)

    request.session.modified = True
    request.session.save()
    request.session.cycle_key()


# ============================================
# HELPERS — PERMISSIONS
# ============================================

def _is_super_admin(user):
    """True if the user is a Django superuser OR has the custom super_admin role."""
    return bool(
        user.is_authenticated
        and (user.is_superuser or getattr(user, 'role', None) == 'super_admin')
    )


def _can_manage_company(user, company):
    """True if the user can manage the given company's join requests."""
    if not user.is_authenticated:
        return False
    if _is_super_admin(user):
        return True
    return (
        getattr(user, 'role', None) == 'company_admin'
        and getattr(user, 'company_id', None) == company.id
    )


# ============================================
# JOIN REQUESTS — LIST
# ============================================

@login_required
def company_join_requests(request, company_id):
    """
    Pending / approved / rejected join requests for a company.

    Access:
      - super_admin      → any company
      - company_admin    → only their own company
    """
    company = get_object_or_404(
        Company.objects.select_related('business_type', 'plan'),
        pk=company_id,
    )

    if not _can_manage_company(request.user, company):
        messages.error(request, "You don't have access to this page.")
        return redirect('/no-access/')

    pending = (
        company.join_requests
        .filter(status='pending')
        .select_related('company')
        .order_by('-created_at')
    )
    approved = (
        company.join_requests
        .filter(status='approved')
        .select_related('reviewed_by', 'assigned_user', 'assigned_branch')
        .order_by('-reviewed_at')[:20]
    )
    rejected = (
        company.join_requests
        .filter(status='rejected')
        .select_related('reviewed_by')
        .order_by('-reviewed_at')[:20]
    )

    # Full counts (independent of the [:20] slice)
    approved_count = company.join_requests.filter(status='approved').count()
    rejected_count = company.join_requests.filter(status='rejected').count()

    branches = (
        Branch.objects
        .filter(company=company, is_active=True)
        .order_by('name')
    )

    context = {
        'company': company,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'pending_count': pending.count(),
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'branches': branches,
        'roles': ASSIGNABLE_ROLES,
        'page_title': 'Join Requests',
        'page_subtitle': f'{company.name} ({company.company_id})',
    }
    return render(request, 'companies/join_requests.html', context)


# ============================================
# JOIN REQUESTS — APPROVE
# ============================================

@login_required
@require_POST
def company_join_request_approve(request, company_id, request_id):
    """
    Approve a pending join request → create the User account.

    Reads optional fields from the approve modal:
        role, branch_id, staff_id, department, position

    Also records the actual assignment on the join request
    (assigned_role, assigned_user, assigned_branch) so the
    Approved tab can display what was really given.
    """
    company = get_object_or_404(Company, pk=company_id)
    req = get_object_or_404(CompanyJoinRequest, pk=request_id, company=company)

    if not _can_manage_company(request.user, company):
        messages.error(request, "You don't have access to approve requests.")
        return redirect('/no-access/')

    if req.status != 'pending':
        messages.warning(request, 'This request has already been reviewed.')
        return redirect('companies:company-join-requests', company_id=company.id)

    # ---------- Uniqueness ----------
    if User.objects.filter(username__iexact=req.username).exists():
        messages.error(request, f'Cannot approve — username "{req.username}" is already taken.')
        return redirect('companies:company-join-requests', company_id=company.id)

    if User.objects.filter(email__iexact=req.email).exists():
        messages.error(request, f'Cannot approve — email "{req.email}" is already registered.')
        return redirect('companies:company-join-requests', company_id=company.id)

    # ---------- Values from the approve modal ----------
    requested_role = (request.POST.get('role') or '').strip()
    branch_id      = (request.POST.get('branch_id') or '').strip() or None
    staff_id       = (request.POST.get('staff_id') or '').strip()
    department     = (request.POST.get('department') or '').strip()
    position       = (request.POST.get('position') or '').strip()

    # Validate: only allow assignable roles
    allowed_roles = {value for value, _ in ASSIGNABLE_ROLES}
    if requested_role in allowed_roles:
        role = requested_role
    elif req.requested_role in allowed_roles:
        role = req.requested_role
    else:
        role = 'company_staff'

    # ---------- Create user + mark request atomically ----------
    try:
        with transaction.atomic():
            user = User.objects.create(
                username=req.username,
                email=req.email,
                first_name=req.first_name,
                last_name=req.last_name,
                phone=req.phone,
                role=role,
                company=company,
                branch_id=branch_id,
                staff_id=staff_id,
                department=department,
                position=position,
                password=req.password_hash,
                is_active=True,
                is_verified=True,
            )

            # Resolve the Branch instance (for the assignment record)
            branch_obj = None
            if branch_id:
                branch_obj = Branch.objects.filter(pk=branch_id, company=company).first()

            # Save the assignment on the join request
            req.mark_approved(
                reviewed_by=request.user,
                assigned_user=user,
                assigned_role=role,
                assigned_branch=branch_obj,
            )

        messages.success(
            request,
            f'Approved! {user.first_name or user.username} can now log in as '
            f'{user.get_role_display()}.'
        )
    except Exception as e:
        logger.exception("Failed to approve join request %s", req.id)
        messages.error(request, f'Error creating user: {e}')

    return redirect('companies:company-join-requests', company_id=company.id)


# ============================================
# JOIN REQUESTS — REJECT
# ============================================

@login_required
@require_POST
def company_join_request_reject(request, company_id, request_id):
    """Reject a pending join request and clean up any auto-created user."""
    company = get_object_or_404(Company, pk=company_id)
    req = get_object_or_404(CompanyJoinRequest, pk=request_id, company=company)

    if not _can_manage_company(request.user, company):
        messages.error(request, "You don't have access to reject requests.")
        return redirect('/no-access/')

    if req.status != 'pending':
        messages.warning(request, 'This request has already been reviewed.')
        return redirect('companies:company-join-requests', company_id=company.id)

    reason = (request.POST.get('reason') or '').strip()

    # ---------- Clean up an auto-created User, if any ----------
    stale_qs = User.objects.filter(
        email__iexact=req.email,
        company=company,
        is_active=True,
        is_verified=True,
    )
    deleted_count = stale_qs.count()
    if deleted_count:
        for u in stale_qs:
            logger.info(
                "Reject: deleting auto-created user id=%s username=%s "
                "email=%s role=%s (from join request %s)",
                u.pk, u.username, u.email, u.role, req.pk,
            )
        stale_qs.delete()

    req.mark_rejected(request.user, reason)

    msg = f'Request from {req.full_name} has been rejected.'
    if deleted_count:
        msg += f' {deleted_count} auto-created account(s) removed.'

    messages.success(request, msg)
    return redirect('companies:company-join-requests', company_id=company.id)


# ============================================
# JOIN REQUEST — RESET TO PENDING
# ============================================

@login_required
@require_POST
def company_join_request_reset(request, company_id, request_id):
    """
    Move an already-reviewed join request back to 'pending'.

    Cleanup behavior:
      - If the request was APPROVED and a User account was auto-created by
        the approval flow, that user is DELETED so the request can be
        re-approved cleanly without a username/email collision.
      - Manually-created users are NOT touched.
      - If the request was REJECTED, no user exists → nothing to clean up.
    """
    company = get_object_or_404(Company, pk=company_id)
    req = get_object_or_404(CompanyJoinRequest, pk=request_id, company=company)

    if not _can_manage_company(request.user, company):
        messages.error(request, "You don't have access to modify requests.")
        return redirect('/no-access/')

    if req.status == 'pending':
        messages.info(request, 'This request is already pending.')
        return redirect('companies:company-join-requests', company_id=company.id)

    old_status = req.status
    deleted_count = 0

    # ---------- Clean up an auto-created User, if any ----------
    if old_status == 'approved':
        stale_qs = User.objects.filter(
            email__iexact=req.email,
            company=company,
            is_active=True,
            is_verified=True,
        )
        deleted_count = stale_qs.count()
        if deleted_count:
            for u in stale_qs:
                logger.info(
                    "Reset: deleting auto-created user id=%s username=%s "
                    "email=%s role=%s (from join request %s)",
                    u.pk, u.username, u.email, u.role, req.pk,
                )
            stale_qs.delete()

    # mark_pending clears assigned_role / assigned_user / assigned_branch
    req.mark_pending()

    msg = (
        f'Request from {req.full_name} has been moved back to Pending '
        f'(was {old_status}).'
    )
    if deleted_count:
        msg += f' {deleted_count} auto-created account(s) removed.'

    messages.success(request, msg)
    return redirect('companies:company-join-requests', company_id=company.id)


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

    context = {
        'companies': companies,
        'total_companies': companies.count(),
        'active_companies': companies.filter(is_active=True).count(),
        'inactive_companies': companies.filter(is_active=False).count(),
        'expired_companies': companies.filter(
            subscriptions__status='expired'
        ).distinct().count(),
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

        raw_domain = request.POST.get('custom_domain', '')
        custom_domain = _normalize_domain(raw_domain)
        domain_verified = request.POST.get('domain_verified') == 'on'

        # ---------- Validation ----------
        if not name:
            messages.error(request, 'Company name is required.')
            return render(request, 'companies/create.html', {
                'business_types': business_types,
                'plans': plans,
                'form_data': request.POST,
            })

        domain_ok, domain_err = _validate_domain(custom_domain)
        if not domain_ok:
            messages.error(request, domain_err)
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
                custom_domain=custom_domain or None,
                domain_verified=domain_verified,
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
            messages.error(request, f'Error creating company: {e}')

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

        raw_domain = request.POST.get('custom_domain', '')
        custom_domain = _normalize_domain(raw_domain)
        domain_verified = request.POST.get('domain_verified') == 'on'

        # ---------- Validation ----------
        if not name:
            messages.error(request, 'Company name is required.')
            return render(request, 'companies/edit.html', {
                'company': company,
                'business_types': business_types,
                'plans': plans,
                'form_data': request.POST,
            })

        domain_ok, domain_err = _validate_domain(custom_domain, exclude_company_id=company.pk)
        if not domain_ok:
            messages.error(request, domain_err)
            return render(request, 'companies/edit.html', {
                'company': company,
                'business_types': business_types,
                'plans': plans,
                'form_data': request.POST,
            })

        try:
            # ---------- Scalar fields ----------
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

            # ---------- Custom domain ----------
            if custom_domain != (company.custom_domain or ''):
                company.custom_domain = custom_domain or None
                company.domain_verified = False   # require re-verify
            else:
                company.domain_verified = domain_verified

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

            # ---------- Consistency warning ----------
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
            messages.error(request, f'Error updating company: {e}')

    context = {
        'company': company,
        'business_types': business_types,
        'plans': plans,
        'page_title': 'Edit Company',
        'page_subtitle': f'Editing {company.name}',
    }
    return render(request, 'companies/edit.html', context)


# ============================================
# VERIFY CUSTOM DOMAIN (DNS CHECK)
# ============================================

@login_required
@staff_member_required
@require_POST
def company_verify_domain(request, pk):
    """
    Quick DNS check: does the company's custom_domain resolve to an IP?

    Returns JSON: { success, message, verified, resolved_ip? }
    """
    company = get_object_or_404(Company, pk=pk)

    if not company.custom_domain:
        return JsonResponse({
            'success': False,
            'verified': False,
            'message': 'No custom domain set for this company.',
        }, status=400)

    try:
        resolved_ip = socket.gethostbyname(company.custom_domain)
    except socket.gaierror:
        company.domain_verified = False
        company.save(update_fields=['domain_verified'])
        return JsonResponse({
            'success': False,
            'verified': False,
            'message': f'{company.custom_domain} does not resolve. Check the DNS records.',
        })

    company.domain_verified = True
    company.save(update_fields=['domain_verified'])

    return JsonResponse({
        'success': True,
        'verified': True,
        'resolved_ip': resolved_ip,
        'message': f'{company.custom_domain} resolves to {resolved_ip}. Marked as verified.',
    })


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
            messages.error(request, f'Error deleting company: {e}')

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

    if not _is_super_admin(request.user):
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
# M-PESA STK PUSH — INITIATE (KCB BUNI)
# ============================================

@login_required
@require_POST
def company_payments_initiate(request, pk):
    """
    Initiate an M-Pesa STK Push via KCB Buni.
    Creates a pending Subscription row, then calls the KCB API.
    """
    try:
        company = get_object_or_404(Company, pk=pk)

        if not _is_super_admin(request.user):
            if getattr(request.user, 'company_id', None) != company.id:
                return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        # ---------- Parse payload ----------
        try:
            payload = json.loads(request.body.decode() or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

        plan_id = payload.get('plan_id')
        phone = (payload.get('phone') or '').strip()
        first_name = (payload.get('first_name') or request.user.first_name or 'Customer').strip()
        last_name = (payload.get('last_name') or request.user.last_name or '').strip()

        if not plan_id or not phone:
            return JsonResponse(
                {'success': False, 'error': 'Plan and phone are required.'},
                status=400,
            )

        plan = get_object_or_404(Plan, pk=plan_id)

        start_dt = timezone.now()
        end_dt = _compute_end_date(plan, start_dt)

        # ---------- Create pending Subscription FIRST ----------
        sub = Subscription.objects.create(
            company=company,
            plan=plan,
            start_date=start_dt,
            end_date=end_dt,
            status='pending',
            payment_method='mpesa',
            payment_reference='',  # filled after KCB returns the checkout ID
        )

        # Unique invoice reference KCB will echo back in the callback
        invoice_number = f"CO{company.id}-SUB{sub.id}-{uuid.uuid4().hex[:6].upper()}"

        # ---------- Call KCB Buni ----------
        try:
            client = KCBClient()
            result = client.stk_push(
                phone_number=phone,
                amount=int(plan.price),
                invoice_number=invoice_number,
                description=f"{company.name} subscription",
            )
        except Exception as e:
            sub.status = 'cancelled'
            sub.save(update_fields=['status'])
            logger.error("KCB STK push failed for sub %s: %s", sub.id, e)
            return JsonResponse(
                {'success': False, 'error': str(e)},
                status=502,
            )

        # KCB returns:
        # {
        #   'header': {'statusCode': '0', 'statusDescription': '...'},
        #   'response': {
        #       'MerchantRequestID': '...',
        #       'CheckoutRequestID': 'ws_CO_...',
        #       'ResponseCode': '0',
        #       'CustomerMessage': '...',
        #   }
        # }
        body = result.get('response', result)
        checkout_id = body.get('CheckoutRequestID') or body.get('MerchantRequestID') or ''

        # Store BOTH the invoice_number and checkout_id so the callback can match either
        sub.payment_reference = checkout_id or invoice_number
        sub.save(update_fields=['payment_reference'])

        # Store invoice_number in a safe place for the callback lookup
        # (we stash it on the Subscription row via payment_reference fallback)
        logger.info(
            "KCB STK push sent: sub=%s invoice=%s checkout=%s",
            sub.id, invoice_number, checkout_id,
        )

        return JsonResponse({
            'success': True,
            'reference': sub.payment_reference,
            'invoice_number': invoice_number,
            'checkout_request_id': checkout_id,
            'message': f'STK Push sent to {phone}. Enter your PIN.',
        })

    except Exception as e:
        logger.exception("Payment initiate failed")
        return JsonResponse(
            {'success': False, 'error': f'Server error: {e}'},
            status=500,
        )


# ============================================
# M-PESA STK PUSH — STATUS POLL
# ============================================

@login_required
@require_GET
def company_payments_status(request, pk):
    """
    Poll payment status.

    For KCB, we don't have a direct status API in this integration — we
    rely on the callback to flip the Subscription row to 'active' or
    'cancelled'. This endpoint just reports what the DB says.

    Lookup strategy:
      1. Exact match on CheckoutRequestID (fresh pending row)
      2. Prefix match on CheckoutRequestID (after the callback appended
         the M-Pesa receipt to payment_reference)
      3. Fallback: invoice_number contained in payment_reference
    """
    company = get_object_or_404(Company, pk=pk)
    reference = request.GET.get('ref', '').strip()

    if not reference:
        return JsonResponse({'status': 'failed', 'message': 'Missing reference.'})

    # ---------- (1) Exact match ----------
    sub = Subscription.objects.filter(
        company=company,
        payment_reference=reference,
    ).order_by('-created_at').first()

    # ---------- (2) Prefix match ----------
    # After a successful callback, payment_reference becomes
    # "ws_CO_...|UIG6170F6F", so an exact match on the raw checkout id
    # no longer finds the row. Prefix-match handles that.
    if not sub:
        sub = Subscription.objects.filter(
            company=company,
            payment_reference__startswith=f"{reference}|",
        ).order_by('-created_at').first()

    # ---------- (3) Invoice-number fallback ----------
    # The initiate view stores the checkout ID, but if anything ever
    # writes the invoice number instead, this catches it.
    if not sub:
        sub = Subscription.objects.filter(
            company=company,
            payment_reference__icontains=reference,
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

    # Still pending — wait for KCB callback
    return JsonResponse({
        'status': 'pending',
        'reference': reference,
    })

    

# ============================================
# M-PESA STK PUSH — CALLBACK (KCB BUNI)
# ============================================

@csrf_exempt
@require_POST
def company_payments_callback(request):
    """
    Global KCB Buni callback. Handles BOTH payload shapes:

    A) Flat / wrapped (KCB → your app directly):
       { "CheckoutRequestID": "ws_CO_...", "ResultCode": "0", ... }

    B) Safaricom Daraja nested (KCB relays from M-Pesa):
       {
         "Body": {
           "stkCallback": {
             "MerchantRequestID": "...",
             "CheckoutRequestID": "ws_CO_...",
             "ResultCode": 0,
             "ResultDesc": "...",
             "CallbackMetadata": {
               "Item": [
                 {"Name": "Amount", "Value": 10.0},
                 {"Name": "MpesaReceiptNumber", "Value": "UIG6170AQ4"},
                 {"Name": "PhoneNumber", "Value": 254722527955},
                 ...
               ]
             }
           }
         }
       }
    """
    # ---------- Parse body ----------
    try:
        payload = json.loads(request.body.decode() or '{}')
    except json.JSONDecodeError:
        logger.warning("KCB callback: invalid JSON: %s", request.body[:500])
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'})

    logger.info("KCB CALLBACK RECEIVED: %s", json.dumps(payload, indent=2))

    # ---------- Normalize payload across shapes ----------
    # Shape A: KCB flat / {"response": {...}} / {"data": {...}}
    # Shape B: Safaricom Daraja {"Body": {"stkCallback": {...}}}
    body = payload

    # Unwrap Safaricom's outer "Body"
    if isinstance(body.get('Body'), dict):
        body = body['Body']

    # Unwrap Safaricom's "stkCallback"
    if isinstance(body.get('stkCallback'), dict):
        body = body['stkCallback']

    # Unwrap KCB's "response" / "data"
    if isinstance(body.get('response'), dict):
        body = body['response']
    elif isinstance(body.get('data'), dict):
        body = body['data']

    # ---------- Extract metadata (Safaricom style) ----------
    # Safaricom puts Amount / MpesaReceiptNumber / PhoneNumber under
    # CallbackMetadata.Item as a list of {"Name": ..., "Value": ...}
    metadata = {}
    cb_meta = body.get('CallbackMetadata') or {}
    items = cb_meta.get('Item') if isinstance(cb_meta, dict) else None
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and 'Name' in it:
                metadata[it['Name']] = it.get('Value')

    # ---------- Extract fields (fall back to metadata) ----------
    checkout_id = (
        body.get('CheckoutRequestID')
        or body.get('checkoutRequestID')
        or body.get('MerchantRequestID')
        or body.get('merchantRequestID')
        or ''
    )
    invoice_number = (
        body.get('InvoiceNumber')
        or body.get('invoiceNumber')
        or body.get('AccountReference')
        or body.get('accountReference')
        or ''
    )
    result_code = str(
        body.get('ResultCode')
        if body.get('ResultCode') is not None
        else body.get('ResponseCode')
        if body.get('ResponseCode') is not None
        else body.get('resultCode')
        if body.get('resultCode') is not None
        else ''
    )
    result_desc = (
        body.get('ResultDesc')
        or body.get('ResponseDescription')
        or body.get('resultDesc')
        or ''
    )
    receipt = (
        body.get('MpesaReceiptNumber')
        or body.get('mpesaReceiptNumber')
        or metadata.get('MpesaReceiptNumber')
        or ''
    )

    # ---------- Locate the Subscription ----------
    sub = None

    if checkout_id:
        # (1) Exact match — fresh callback for a pending row
        sub = (
            Subscription.objects
            .filter(payment_reference=checkout_id)
            .select_related('company', 'plan')
            .first()
        )

        # (2) Prefix match — retry after receipt was appended
        if not sub:
            sub = (
                Subscription.objects
                .filter(payment_reference__startswith=f"{checkout_id}|")
                .select_related('company', 'plan')
                .first()
            )

    # (3) Fallback — invoice_number embedded in payment_reference
    if not sub and invoice_number:
        sub = (
            Subscription.objects
            .filter(payment_reference__icontains=invoice_number)
            .select_related('company', 'plan')
            .first()
        )

    if not sub:
        logger.warning("KCB callback: no matching subscription. payload=%s", payload)
        return JsonResponse({'status': 'error', 'message': 'Unknown reference'})

    company = sub.company

    # ---------- Activate or cancel ----------
    if result_code == '0':
        # SUCCESS

        # Expire other active subscriptions for this company
        (
            company.subscriptions
            .filter(status='active')
            .exclude(pk=sub.pk)
            .update(status='expired')
        )

        now = timezone.now()
        if not sub.start_date:
            sub.start_date = now
        if not sub.end_date:
            sub.end_date = _compute_end_date(sub.plan, sub.start_date)

        sub.status = 'active'

        # Idempotent receipt append
        current_ref = sub.payment_reference or ''
        if receipt and f"|{receipt}" not in current_ref:
            sub.payment_reference = f"{current_ref}|{receipt}"

        sub.save(update_fields=[
            'status', 'start_date', 'end_date', 'payment_reference',
        ])

        # Sync Company row
        company.plan = sub.plan
        company.subscription_start = sub.start_date
        company.subscription_end = sub.end_date
        company.status = 'active'
        company.is_active = True
        company.save(update_fields=[
            'plan', 'subscription_start', 'subscription_end',
            'status', 'is_active',
        ])

        logger.info(
            "KCB payment SUCCESS for company=%s sub=%s receipt=%s",
            company.id, sub.id, receipt,
        )
    else:
        # FAILED / CANCELLED — only cancel rows still pending
        if sub.status == 'pending':
            sub.status = 'cancelled'
            sub.save(update_fields=['status'])

        logger.info(
            "KCB payment FAILED for company=%s sub=%s ResultCode=%s ResultDesc=%s",
            company.id, sub.id, result_code, result_desc,
        )

    return JsonResponse({
        'transactionID': receipt or checkout_id or 'N/A',
        'statusCode': '0',
        'statusMessage': 'Notification received',
        'ResultCode': 0,
        'ResultDesc': 'Accepted',
    })

    

# ============================================
# M-PESA STK PUSH — DEV CONFIRM
# ============================================

@login_required
@require_POST
def company_payments_dev_confirm(request, pk):
    """
    DEV ONLY — flips the latest pending subscription to active.
    Never enable this in production.
    """
    if not settings.DEBUG:
        return JsonResponse({'success': False, 'error': 'Not allowed.'}, status=403)

    company = get_object_or_404(Company, pk=pk)
    reference = request.POST.get('ref') or request.GET.get('ref', '').strip()

    sub = Subscription.objects.filter(
        company=company,
        payment_reference=reference,
        status='pending',
    ).first()

    if not sub:
        return JsonResponse(
            {'success': False, 'error': 'No pending subscription found.'},
            status=404,
        )

    company.subscriptions.filter(status='active').exclude(pk=sub.pk).update(status='expired')
    sub.status = 'active'
    sub.save(update_fields=['status'])

    company.plan = sub.plan
    company.subscription_start = sub.start_date
    company.subscription_end = sub.end_date
    company.status = 'active'
    company.is_active = True
    company.save(update_fields=[
        'plan', 'subscription_start', 'subscription_end', 'status', 'is_active',
    ])

    return JsonResponse({'success': True, 'message': 'Marked as paid.'})



# ============================================
# COMPANY EMPLOYEES (Super Admin list)
# ============================================

@login_required
@staff_member_required
def company_employee_list(request, company_id):
    """Super admin view: list employees for a specific company."""
    company = get_object_or_404(
        Company.objects.select_related('business_type', 'plan'),
        pk=company_id,
    )

    employees = (
        User.objects
        .filter(company=company)
        .exclude(role='super_admin')
        .select_related('branch')
        .order_by('-created_at')
    )

    search_query = request.GET.get('search', '').strip()
    if search_query:
        employees = employees.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(staff_id__icontains=search_query)
        )

    role_filter = request.GET.get('role', '').strip()
    if role_filter:
        employees = employees.filter(role=role_filter)

    context = {
        'company': company,
        'employees': employees,
        'search_query': search_query,
        'role_filter': role_filter,
        'page_title': f'{company.name} · Employees',
        'page_subtitle': 'Company employees',
    }
    return render(request, 'companies/employees.html', context)