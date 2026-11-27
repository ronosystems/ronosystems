# ============================================================
# EXTERNAL LOANS VIEWS
# Full CRUD for external loans (customers / guests — non-members)
# Mirrors internal_loans_views structure but scoped to guests
# ============================================================
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse

from .forms import GuestForm

from .models import (
    Loan, LoanType, LoanRepayment, Guest,
    Account, Transaction,
)

from .members_views import (
    _get_company,
    _company_queryset,
    ADMIN_ROLES,
)


# ============================================================
# DECORATORS
# ============================================================

def _require_officer(view_func):
    """Standard officer check for external loan actions."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        allowed = {
            'super_admin', 'company_admin', 'company_manager',
            'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer',
            'secretary',
        }
        if not request.user.is_authenticated:
            return redirect('/auth/login/')
        if getattr(request.user, 'role', None) not in allowed:
            messages.error(request, 'Only Chama officers can perform this action.')
            return redirect('chama:external_loan_limits')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ============================================================
# LOCAL HELPERS
# ============================================================

def _send_chama_stk_push(company, phone, amount, account_reference, description):
    """Wrapper around apps.mpesa.services.send_stk_push."""
    from apps.mpesa.models import MpesaConfig
    from apps.mpesa.services import send_stk_push

    cfg = MpesaConfig.for_branch(company, None)
    if not cfg:
        raise RuntimeError(
            'No M-Pesa configuration found for this company. '
            'Ask your admin to set one up in Company Settings.'
        )
    return send_stk_push(
        cfg=cfg,
        phone=phone,
        amount=amount,
        account_reference=(account_reference or '')[:12],
        description=(description or 'Chama payment')[:13],
    )


def _get_customer_for_guest(company, guest):
    """Look up the linked Customer record for a Guest (by phone or national_id)."""
    if not guest:
        return None
    from apps.customers.models import Customer

    qs = Customer.objects.filter(company=company)
    if guest.national_id:
        match = qs.filter(national_id=guest.national_id).first()
        if match:
            return match
    if guest.phone:
        match = qs.filter(phone_number=guest.phone).first()
        if match:
            return match
    return None


def _guest_active_loan_total(company, guest):
    """Sum of active external loan principals for a guest."""
    if not guest:
        return Decimal('0.00')
    total = Loan.objects.filter(
        company=company,
        loan_category='external',
        status__in=['approved', 'disbursed'],
        guest=guest,
    ).aggregate(t=Sum('principal'))['t']
    return total or Decimal('0.00')


def _guest_eligible_limit(company, guest):
    """Return (limit, active_loans, available) for a guest's customer profile."""
    customer = _get_customer_for_guest(company, guest)
    if not customer:
        return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')

    limit = customer.custom_loan_limit or Decimal('0.00')
    active = _guest_active_loan_total(company, guest)
    available = max(Decimal('0.00'), limit - active)
    return limit, active, available


# ============================================================
# GUESTS — CRUD
# ============================================================

@login_required
@_require_officer
def guest_list(request):
    """List all guests (external borrowers) for the company."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    qs = Guest.objects.filter(company=company).select_related('created_by')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(full_name__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(national_id__icontains=q)
        )

    qs = qs.order_by('-created_at')

    return render(request, 'chama/external_loans/guest_list.html', {
        'guests': qs,
        'total_count': qs.count(),
        'is_officer': True,
    })


@login_required
@_require_officer
def guest_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:guest_list')

    if request.method == 'POST':
        form = GuestForm(request.POST, request.FILES)
        if form.is_valid():
            guest = form.save(commit=False)
            guest.company = company
            guest.created_by = request.user
            guest.save()
            messages.success(request, f'✅ Guest "{guest.full_name}" registered successfully.')
            return redirect('chama:guest_detail', pk=guest.pk)
    else:
        form = GuestForm()

    return render(request, 'chama/external_loans/guest_form.html', {
        'form': form,
        'mode': 'create',
    })


@login_required
@_require_officer
def guest_detail(request, pk):
    company = _get_company(request)
    guest = get_object_or_404(Guest, pk=pk, company=company)

    # Stats for the detail page
    external_loans = Loan.objects.filter(
        company=company, guest=guest
    ).select_related('loan_type').order_by('-requested_on')

    limit, active, available = _guest_eligible_limit(company, guest)

    return render(request, 'chama/external_loans/guest_detail.html', {
        'guest': guest,
        'external_loans': external_loans,
        'limit': limit,
        'active_loans': active,
        'available': available,
    })


@login_required
@_require_officer
def guest_edit(request, pk):
    company = _get_company(request)
    guest = get_object_or_404(Guest, pk=pk, company=company)

    if request.method == 'POST':
        form = GuestForm(request.POST, request.FILES, instance=guest)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Guest "{guest.full_name}" updated.')
            return redirect('chama:guest_detail', pk=guest.pk)
    else:
        form = GuestForm(instance=guest)

    return render(request, 'chama/external_loans/guest_form.html', {
        'form': form,
        'mode': 'edit',
        'guest': guest,
    })


@login_required
@_require_officer
def guest_delete(request, pk):
    company = _get_company(request)
    guest = get_object_or_404(Guest, pk=pk, company=company)

    if request.method == 'POST':
        # Safety: block if guest has active loans
        active_count = Loan.objects.filter(
            company=company, guest=guest,
            status__in=['approved', 'disbursed']
        ).count()
        if active_count > 0:
            messages.error(
                request,
                f'Cannot delete {guest.full_name}: {active_count} active loan(s) exist. '
                'Close or reject them first.'
            )
            return redirect('chama:guest_detail', pk=guest.pk)

        name = guest.full_name
        guest.delete()
        messages.info(request, f'🗑️ Guest "{name}" deleted.')
        return redirect('chama:guest_list')

    return render(request, 'chama/external_loans/guest_confirm_delete.html', {'guest': guest})


# ============================================================
# EXTERNAL LOANS — LIST / DETAIL
# ============================================================

@login_required
@_require_officer
def external_loan_list(request):
    """List only external loans."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    qs = Loan.objects.filter(
        company=company,
        loan_category='external',
    ).select_related(
        'guest', 'loan_type', 'approved_by', 'rejected_by', 'disbursed_by'
    )

    # Filters
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(guest__full_name__icontains=q) |
            models.Q(guest__phone__icontains=q) |
            models.Q(guest__national_id__icontains=q)
        )

    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)

    qs = qs.order_by('-requested_on', '-created_at')

    # Stats
    total_pending = qs.filter(status='pending').aggregate(t=Sum('principal'))['t'] or 0
    total_approved = qs.filter(status='approved').aggregate(t=Sum('principal'))['t'] or 0
    total_disbursed = qs.filter(status='disbursed').aggregate(t=Sum('principal'))['t'] or 0
    total_repaid = (
        qs.filter(status__in=['disbursed', 'closed'])
        .aggregate(t=Sum('repayments__amount'))['t'] or 0
    )

    return render(request, 'chama/external_loans/list.html', {
        'loans': qs,
        'total_pending': total_pending,
        'total_approved': total_approved,
        'total_disbursed': total_disbursed,
        'total_repaid': total_repaid,
        'total_count': qs.count(),
    })


@login_required
@_require_officer
def external_loan_detail(request, pk):
    """Detail page for a single external loan."""
    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('guest', 'loan_type'),
        pk=pk, company=company, loan_category='external'
    )

    repayments = loan.repayments.order_by('-date', '-created_at')
    limit, active, available = _guest_eligible_limit(company, loan.guest)

    return render(request, 'chama/external_loans/detail.html', {
        'loan': loan,
        'repayments': repayments,
        'limit': limit,
        'active_loans': active,
        'available': available,
    })


# ============================================================
# EXTERNAL LOANS — CREATE
# ============================================================

@login_required
@_require_officer
def loan_create_external(request, guest_pk):
    """Create a new external loan for a registered guest."""
    company = _get_company(request)
    guest = get_object_or_404(Guest, pk=guest_pk, company=company)

    if request.method == 'POST':
        loan_type_id = request.POST.get('loan_type')
        principal_raw = request.POST.get('principal')
        term_raw = request.POST.get('term_months')
        purpose = request.POST.get('purpose', '')

        try:
            lt = LoanType.objects.get(pk=loan_type_id, company=company)
            principal = Decimal(principal_raw)
            term = int(term_raw)

            if principal <= 0:
                raise ValueError("Amount must be greater than zero.")
            if term <= 0:
                raise ValueError("Term must be at least 1 month.")

            # Enforce customer limit
            limit, active, available = _guest_eligible_limit(company, guest)
            if principal > available:
                messages.error(
                    request,
                    f'Amount exceeds available limit of KES {available:,.2f} '
                    f'(limit: {limit:,.2f} − active loans: {active:,.2f}).'
                )
                loan_types = LoanType.objects.filter(company=company, is_active=True)
                return render(request, 'chama/external_loans/form.html', {
                    'guest': guest,
                    'loan_types': loan_types,
                    'limit': limit,
                    'active_loans': active,
                    'available': available,
                })

            if lt.max_amount and principal > lt.max_amount:
                messages.error(
                    request,
                    f'Amount exceeds the maximum for {lt.name} '
                    f'(KES {lt.max_amount:,.2f}).'
                )
                loan_types = LoanType.objects.filter(company=company, is_active=True)
                return render(request, 'chama/external_loans/form.html', {
                    'guest': guest,
                    'loan_types': loan_types,
                    'limit': limit,
                    'active_loans': active,
                    'available': available,
                })

            if lt.max_term_months and term > lt.max_term_months:
                messages.error(
                    request,
                    f'Term exceeds the maximum for {lt.name} ({lt.max_term_months} months).'
                )
                loan_types = LoanType.objects.filter(company=company, is_active=True)
                return render(request, 'chama/external_loans/form.html', {
                    'guest': guest,
                    'loan_types': loan_types,
                    'limit': limit,
                    'active_loans': active,
                    'available': available,
                })

            Loan.objects.create(
                company=company,
                loan_category='external',
                guest=guest,
                loan_type=lt,
                principal=principal,
                interest_rate=lt.interest_rate,
                term_months=term,
                purpose=purpose,
                status='pending',
                requested_on=timezone.localdate(),
            )
            messages.success(
                request,
                f'✅ External loan of KES {principal:,.2f} created for {guest.full_name}.'
            )
            return redirect('chama:external_loan_list')

        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f'Invalid input: {e}')
        except LoanType.DoesNotExist:
            messages.error(request, 'Selected loan type not found.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    loan_types = LoanType.objects.filter(company=company, is_active=True)
    limit, active, available = _guest_eligible_limit(company, guest)

    return render(request, 'chama/external_loans/form.html', {
        'guest': guest,
        'loan_types': loan_types,
        'limit': limit,
        'active_loans': active,
        'available': available,
    })


# ============================================================
# EXTERNAL LOANS — UPDATE
# ============================================================

@login_required
@_require_officer
def loan_edit_external(request, pk):
    """Edit an external loan (only pending or approved, not disbursed/closed)."""
    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('guest', 'loan_type'),
        pk=pk, company=company, loan_category='external'
    )

    if loan.status not in ('pending', 'approved'):
        messages.warning(
            request,
            f'Cannot edit loan in "{loan.get_status_display()}" status. '
            'Only pending or approved loans can be edited.'
        )
        return redirect('chama:external_loan_detail', pk=loan.pk)

    if request.method == 'POST':
        loan_type_id = request.POST.get('loan_type')
        principal_raw = request.POST.get('principal')
        term_raw = request.POST.get('term_months')
        purpose = request.POST.get('purpose', '')

        try:
            lt = LoanType.objects.get(pk=loan_type_id, company=company)
            principal = Decimal(principal_raw)
            term = int(term_raw)

            if principal <= 0:
                raise ValueError("Amount must be greater than zero.")
            if term <= 0:
                raise ValueError("Term must be at least 1 month.")

            # If pending, allow limit check. If already approved, only allow
            # reducing principal (never increasing above what was approved).
            if loan.status == 'pending':
                limit, active, available = _guest_eligible_limit(company, loan.guest)
                if principal > available:
                    messages.error(
                        request,
                        f'Amount exceeds available limit of KES {available:,.2f}.'
                    )
                    return redirect('chama:loan_edit_external', pk=loan.pk)

            if lt.max_amount and principal > lt.max_amount:
                messages.error(
                    request,
                    f'Amount exceeds the maximum for {lt.name} (KES {lt.max_amount:,.2f}).'
                )
                return redirect('chama:loan_edit_external', pk=loan.pk)

            loan.loan_type = lt
            loan.principal = principal
            loan.interest_rate = lt.interest_rate
            loan.term_months = term
            loan.purpose = purpose
            loan.save()
            messages.success(request, f'✅ External loan #{loan.pk} updated.')
            return redirect('chama:external_loan_detail', pk=loan.pk)

        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f'Invalid input: {e}')
        except LoanType.DoesNotExist:
            messages.error(request, 'Selected loan type not found.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    loan_types = LoanType.objects.filter(company=company, is_active=True)

    return render(request, 'chama/external_loans/form.html', {
        'guest': loan.guest,
        'loan_types': loan_types,
        'loan': loan,
        'mode': 'edit',
    })


# ============================================================
# EXTERNAL LOANS — DELETE
# ============================================================

@login_required
@_require_officer
def loan_delete_external(request, pk):
    """Delete an external loan (only pending or rejected)."""
    company = _get_company(request)
    loan = get_object_or_404(
        Loan, pk=pk, company=company, loan_category='external'
    )

    if loan.status not in ('pending', 'rejected'):
        messages.error(
            request,
            f'Cannot delete loan in "{loan.get_status_display()}" status. '
            'Only pending or rejected loans can be deleted.'
        )
        return redirect('chama:external_loan_detail', pk=loan.pk)

    if request.method == 'POST':
        loan_id = loan.pk
        loan.delete()
        messages.info(request, f'🗑️ External loan #{loan_id} deleted.')
        return redirect('chama:external_loan_list')

    return render(request, 'chama/external_loans/loan_confirm_delete.html', {'loan': loan})


# ============================================================
# EXTERNAL LOANS — APPROVE / REJECT / DISBURSE
# ============================================================

@login_required
@_require_officer
def loan_approve_external(request, pk):
    if request.method != 'POST':
        return redirect('chama:external_loan_list')

    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('guest', 'loan_type'),
        pk=pk, company=company, loan_category='external'
    )

    if loan.status != 'pending':
        messages.warning(request, 'Loan is no longer pending.')
        return redirect('chama:external_loan_list')

    guest = loan.guest
    if not guest:
        messages.error(request, 'This loan has no guest attached.')
        return redirect('chama:external_loan_list')

    # Enforce customer limit at approval time
    limit, active, available = _guest_eligible_limit(company, guest)
    if loan.principal > available:
        messages.error(
            request,
            f'Cannot approve: {guest.full_name} can only borrow up to '
            f'KES {available:,.2f} (limit: {limit:,.2f} − active: {active:,.2f}).'
        )
        return redirect('chama:external_loan_list')

    if loan.loan_type and loan.loan_type.max_amount and loan.principal > loan.loan_type.max_amount:
        messages.error(
            request,
            f'Cannot approve: exceeds max for {loan.loan_type.name} '
            f'(KES {loan.loan_type.max_amount:,.2f}).'
        )
        return redirect('chama:external_loan_list')

    loan.status = 'approved'
    loan.approved_on = timezone.localdate()
    loan.approved_by = request.user
    loan.save(update_fields=['status', 'approved_on', 'approved_by'])

    messages.success(
        request,
        f'✅ External loan #{loan.pk} approved for {guest.full_name} '
        f'(KES {loan.principal:,.2f}).'
    )
    return redirect('chama:external_loan_list')


@login_required
@_require_officer
def loan_reject_external(request, pk):
    if request.method != 'POST':
        return redirect('chama:external_loan_list')

    company = _get_company(request)
    loan = get_object_or_404(
        Loan, pk=pk, company=company, loan_category='external'
    )

    if loan.status != 'pending':
        messages.warning(request, 'Loan is no longer pending.')
        return redirect('chama:external_loan_list')

    loan.status = 'rejected'
    loan.rejected_by = request.user
    loan.save(update_fields=['status', 'rejected_by'])

    messages.info(request, f'External loan #{loan.pk} rejected.')
    return redirect('chama:external_loan_list')


@login_required
@_require_officer
@transaction.atomic
def loan_disburse_external(request, pk):
    if request.method != 'POST':
        return redirect('chama:external_loan_list')

    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('guest', 'loan_type'),
        pk=pk, company=company, loan_category='external'
    )

    if loan.status != 'approved':
        messages.warning(request, 'Only approved loans can be disbursed.')
        return redirect('chama:external_loan_list')

    guest = loan.guest
    if guest:
        # Re-check limit at disbursement time
        limit, active, available = _guest_eligible_limit(company, guest)
        # `active` already excludes this loan if it's approved (we re-query)
        other_active = Loan.objects.filter(
            company=company,
            loan_category='external',
            status__in=['approved', 'disbursed'],
            guest=guest,
        ).exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or Decimal('0.00')

        actual_available = max(Decimal('0.00'), limit - other_active)
        if loan.principal > actual_available:
            messages.error(
                request,
                f'Cannot disburse: {guest.full_name} can only borrow up to '
                f'KES {actual_available:,.2f} at this time.'
            )
            return redirect('chama:external_loan_list')

    loan.status = 'disbursed'
    loan.disbursed_on = timezone.localdate()
    loan.disbursed_by = request.user
    loan.save(update_fields=['status', 'disbursed_on', 'disbursed_by'])

    # Post to cashbook (Loan Fund = money OUT)
    loan_account = Account.objects.filter(
        company=company, purpose='loans', is_active=True
    ).first()

    if loan_account:
        borrower = guest.full_name if guest else 'Guest'
        if loan_account.current_balance < loan.principal:
            messages.warning(
                request,
                f'⚠️ Note: {loan_account.name} balance (KES '
                f'{loan_account.current_balance:,.2f}) is less than the loan '
                f'principal (KES {loan.principal:,.2f}). The account will go negative.'
            )
        Transaction.objects.create(
            company=company,
            account=loan_account,
            transaction_type='out',
            amount=loan.principal,
            date=loan.disbursed_on,
            description=f'External loan disbursed #{loan.pk} — {borrower}',
            reference=f'EXLOAN-{loan.pk}',
            auto_generated=True,
        )
    else:
        messages.warning(
            request,
            'Loan disbursed, but no Loan Fund account exists. '
            'Please create an account with purpose="loans" to track cash flow.'
        )

    messages.success(
        request,
        f'✅ External loan #{loan.pk} disbursed to {guest.full_name} '
        f'(KES {loan.principal:,.2f}).'
    )
    return redirect('chama:external_loan_list')


# ============================================================
# EXTERNAL LOANS — REPAYMENTS
# ============================================================

@login_required
@_require_officer
def external_loan_repayment_create(request, loan_pk):
    """Officer records a manual repayment for an external loan."""
    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('guest'),
        pk=loan_pk, company=company, loan_category='external'
    )

    allowed_roles = ['super_admin', 'company_admin', 'treasurer']
    if request.user.role not in allowed_roles:
        messages.error(request, 'Only the Treasurer can record manual repayments.')
        return redirect('chama:external_loan_detail', pk=loan.pk)

    if loan.status not in ('disbursed', 'approved'):
        messages.warning(request, 'Only active loans can be repaid.')
        return redirect('chama:external_loan_detail', pk=loan.pk)

    if request.method == 'POST':
        amount_raw = request.POST.get('amount', '').strip()
        date_raw = request.POST.get('date', '').strip()
        reference = request.POST.get('reference', '').strip()
        notes = request.POST.get('notes', '').strip()

        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")
            if amount > loan.balance_remaining:
                raise ValueError(
                    f"Amount exceeds balance remaining (KES {loan.balance_remaining:,.2f})."
                )

            paid_date = (
                timezone.datetime.strptime(date_raw, '%Y-%m-%d').date()
                if date_raw else timezone.localdate()
            )

            with transaction.atomic():
                obj = LoanRepayment.objects.create(
                    company=company,
                    loan=loan,
                    amount=amount,
                    date=paid_date,
                    reference=reference or f'EXREPAY-{loan.pk}-{timezone.now().timestamp()}',
                    notes=notes,
                )

                loan_account = Account.objects.filter(
                    company=company, purpose='loans', is_active=True
                ).first()

                if loan_account:
                    Transaction.objects.create(
                        company=company,
                        account=loan_account,
                        transaction_type='in',
                        amount=amount,
                        date=paid_date,
                        description=(
                            f'External loan repayment #{loan.pk} — '
                            f'{loan.guest.full_name if loan.guest else "Guest"}'
                        ),
                        reference=f'EXREPAY-{obj.pk}',
                        auto_generated=True,
                    )
                else:
                    messages.warning(
                        request,
                        'Repayment saved, but no Loan Fund account exists.'
                    )

                loan.refresh_from_db()
                if loan.is_fully_repaid and loan.status == 'disbursed':
                    loan.status = 'closed'
                    loan.save(update_fields=['status'])
                    messages.success(
                        request,
                        f'✅ Repayment of KES {amount:,.2f} recorded. '
                        f'Loan #{loan.pk} is now FULLY REPAID and closed! 🎉'
                    )
                else:
                    messages.success(
                        request,
                        f'✅ Repayment of KES {amount:,.2f} recorded. '
                        f'Balance remaining: KES {loan.balance_remaining:,.2f}'
                    )

            return redirect('chama:external_loan_detail', pk=loan.pk)

        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f'Invalid input: {e}')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return render(request, 'chama/external_loans/repayment_form.html', {
        'loan': loan,
        'suggested_amount': loan.balance_remaining,
    })


@login_required
@_require_officer
def external_loan_repayment_pay(request, loan_pk):
    """Trigger M-Pesa STK Push for an external loan repayment."""
    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('guest'),
        pk=loan_pk, company=company, loan_category='external'
    )

    if loan.status not in ('disbursed', 'approved'):
        messages.warning(request, 'This loan is not active for repayment.')
        return redirect('chama:external_loan_detail', pk=loan.pk)

    if loan.balance_remaining <= 0:
        messages.info(request, 'This loan is already fully repaid.')
        return redirect('chama:external_loan_detail', pk=loan.pk)

    if request.method == 'POST':
        amount_raw = request.POST.get('amount', '').strip()
        phone = request.POST.get('phone', '').strip()

        if not amount_raw or not phone:
            messages.error(request, 'Amount and phone number are required.')
        else:
            try:
                amount_dec = Decimal(amount_raw)
                if amount_dec <= 0 or amount_dec > loan.balance_remaining:
                    messages.error(
                        request,
                        f'Amount must be between 1 and KES {loan.balance_remaining:,.2f}.'
                    )
                else:
                    response = _send_chama_stk_push(
                        company=company,
                        phone=phone,
                        amount=int(amount_dec),
                        account_reference=f'EXL-{loan.pk}',
                        description='Ext Loan Repay',
                    )
                    if str(response.get('ResponseCode')) == '0':
                        messages.success(
                            request,
                            f'✅ STK Push sent to {phone}. '
                            'Enter your PIN to complete the repayment.'
                        )
                        return redirect('chama:external_loan_detail', pk=loan.pk)
                    else:
                        messages.error(
                            request,
                            response.get('ResponseDescription') or 'STK Push failed.'
                        )
            except Exception as e:
                messages.error(request, f'Payment error: {e}')

    return render(request, 'chama/external_loans/repayment_pay.html', {
        'loan': loan,
        'suggested_amount': loan.balance_remaining,
    })


@login_required
@_require_officer
def external_loan_repayment_list(request):
    """List all external loan repayments."""
    company = _get_company(request)
    qs = LoanRepayment.objects.filter(
        company=company,
        loan__loan_category='external',
    ).select_related('loan', 'loan__guest').order_by('-date', '-created_at')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(loan__guest__full_name__icontains=q) |
            models.Q(reference__icontains=q)
        )

    total_repaid = qs.aggregate(t=Sum('amount'))['t'] or 0

    return render(request, 'chama/external_loans/repayment_list.html', {
        'repayments': qs,
        'total_repaid': total_repaid,
        'total_count': qs.count(),
    })


# ============================================================
# EXTERNAL LOANS — LIMITS PAGE
# ============================================================

@login_required
def external_loan_limits(request):
    """Officer-only page listing external borrowers with their loan limits."""
    from apps.customers.models import Customer

    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    if request.user.role not in ADMIN_ROLES:
        messages.error(request, 'Only Chama officers can access external loan limits.')
        return redirect('chama:dashboard')

    customers = Customer.objects.filter(company=company).order_by('full_name')

    # Aggregate active external loan principals per customer (by phone)
    active_external = {}
    for loan in Loan.objects.filter(
        company=company,
        loan_category='external',
        status__in=['approved', 'disbursed'],
    ).select_related('guest'):
        key = loan.guest.phone if loan.guest else None
        if key:
            active_external[key] = active_external.get(key, Decimal('0.00')) + loan.principal

    rows = []
    for c in customers:
        limit = c.custom_loan_limit or Decimal('0.00')
        active = active_external.get(c.phone_number, Decimal('0.00'))
        rows.append({
            'customer': c,
            'custom_limit': limit,
            'active_loans_total': active,
            'available_borrowing_power': max(Decimal('0.00'), limit - active),
        })

    return render(request, 'chama/external_loans/limits.html', {
        'rows': rows,
        'is_officer': True,
    })