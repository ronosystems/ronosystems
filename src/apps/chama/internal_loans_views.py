# ============================================================
# INTERNAL LOANS VIEWS
# Internal loans for Chama members (CRUD, approval, disbursement,
# repayment, limits, eligibility)
# ============================================================
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from .forms import (
    LoanTypeForm,
    LoanForm,
    SelfServiceLoanForm,
    LoanRepaymentForm,
)

from .models import (
    Member, Contribution, Loan, LoanType, LoanRepayment,
    Account, Transaction,
)

from .members_views import (
    _get_company,
    _company_queryset,
    _get_current_member,
    ADMIN_ROLES,
)


# ============================================================
# DECORATORS
# ============================================================

from functools import wraps

def _require_loan_policy_setter(view_func):
    """Only Chairperson, Treasurer, Company Admin, or Super Admin."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        allowed = {'super_admin', 'company_admin', 'chairperson', 'treasurer'}
        if not request.user.is_authenticated:
            return redirect('/auth/login/')
        if getattr(request.user, 'role', None) not in allowed:
            messages.error(request, 'Only the Chairperson or Treasurer can set loan policy.')
            return redirect('chama:loan_type_list')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _require_officer(view_func):
    """Standard officer check for internal loan actions."""
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
            return redirect('chama:loan_type_list')
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


def check_internal_loan_eligibility(member):
    """Return (is_eligible, reason) for internal loan applications."""
    if not member:
        return False, "You are not registered as a Chama member."

    if member.status != 'active':
        return False, "Your membership is not active."

    current_month = timezone.localdate().strftime('%Y-%m')
    current_month_paid = Contribution.objects.filter(
        member=member, period=current_month, paid=True
    ).exists()
    if not current_month_paid:
        return False, f"You must pay your {current_month} contribution before applying for a loan."

    late_contributions = Contribution.objects.filter(
        member=member, paid=True, paid_on_time=False
    ).count()
    if late_contributions > 0:
        return False, "You have late contributions on record. Please clear all late payments first."

    outstanding_loans = Loan.objects.filter(
        member=member, status__in=['approved', 'disbursed']
    )
    if outstanding_loans.exists():
        return False, "You have an outstanding loan. Please repay it before applying for a new one."

    if member.available_borrowing_power <= 0:
        return False, "Your borrowing limit is zero. Increase your contributions to unlock more borrowing power."

    return True, "Eligible"


# ============================================================
# LOAN TYPES
# ============================================================

@login_required
def loan_type_list(request):
    _get_company(request)
    qs = _company_queryset(request, LoanType).order_by('name')
    return render(request, 'chama/internal_loans/type_list.html', {
        'loan_types': qs,
        'is_officer': request.user.role in [
            'super_admin', 'company_admin', 'company_manager',
            'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer',
        ],
    })


@login_required
@_require_loan_policy_setter
def loan_type_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:loan_type_list')

    if request.method == 'POST':
        form = LoanTypeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ Loan Type "{obj.name}" created.')
            return redirect('chama:loan_type_list')
    else:
        form = LoanTypeForm()

    return render(request, 'chama/internal_loans/type_form.html', {'form': form, 'mode': 'create'})


@login_required
@_require_loan_policy_setter
def loan_type_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(LoanType, pk=pk, company=company)

    if request.method == 'POST':
        form = LoanTypeForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Loan Type "{obj.name}" updated.')
            return redirect('chama:loan_type_list')
    else:
        form = LoanTypeForm(instance=obj)

    return render(request, 'chama/internal_loans/type_form.html', {'form': form, 'mode': 'edit', 'loan_type': obj})


@login_required
@_require_loan_policy_setter
def loan_type_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(LoanType, pk=pk, company=company)
    name = obj.name
    obj.delete()
    messages.info(request, f'🗑️ Loan Type "{name}" deleted.')
    return redirect('chama:loan_type_list')




# ============================================================
# INTERNAL BORROWERS — members who have loans / are eligible
# ============================================================

@login_required
def member_loan_list(request):
    """
    Officers-only page: all members with their loan summary.
    Shows active loans, total borrowed, repayment status,
    and quick access to create a loan / view limits.
    """
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    is_officer = request.user.role in ADMIN_ROLES
    if not is_officer:
        messages.error(request, 'Only Chama officers can view internal borrowers.')
        return redirect('chama:dashboard')

    qs = Member.objects.filter(
        company=company, status='active'
    ).select_related('membership_type').order_by('full_name')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(full_name__icontains=q) |
            models.Q(member_number__icontains=q) |
            models.Q(phone__icontains=q)
        )

    # Filter: only members with active loans?
    filter_loans = request.GET.get('filter', '').strip()

    # Aggregate active loan totals and count per member in bulk
    active_loans_by_member = {}
    active_loan_count_by_member = {}
    for loan in Loan.objects.filter(
        company=company,
        status__in=['approved', 'disbursed'],
        member__isnull=False,
    ).select_related('member'):
        mid = loan.member_id
        active_loans_by_member[mid] = (
            active_loans_by_member.get(mid, 0) + loan.balance_remaining
        )
        active_loan_count_by_member[mid] = (
            active_loan_count_by_member.get(mid, 0) + 1
        )

    # Total lifetime borrowed per member
    lifetime_borrowed_by_member = {}
    for loan in Loan.objects.filter(
        company=company,
        member__isnull=False,
    ).select_related('member'):
        mid = loan.member_id
        lifetime_borrowed_by_member[mid] = (
            lifetime_borrowed_by_member.get(mid, 0) + loan.principal
        )

    rows = []
    for m in qs:
        active_count = active_loan_count_by_member.get(m.id, 0)
        if filter_loans == 'active' and active_count == 0:
            continue
        rows.append({
            'member': m,
            'active_loan_count': active_count,
            'active_loans_total': active_loans_by_member.get(m.id, 0),
            'lifetime_borrowed': lifetime_borrowed_by_member.get(m.id, 0),
            'available_borrowing_power': m.available_borrowing_power,
            'eligible_limit': m.eligible_loan_limit,
            'has_good_history': m.has_good_repayment_history,
        })

    return render(request, 'chama/internal_loans/member_loan_list.html', {
        'rows': rows,
        'total_count': len(rows),
        'filter': filter_loans,
        'is_officer': True,
    })




# ============================================================
# INTERNAL LOANS — CRUD
# ============================================================

@login_required
def loan_list(request):
    """List loans. Officers see all; members see only their own."""
    company = _get_company(request)
    qs = _company_queryset(request, Loan).select_related(
        'member', 'loan_type', 'approved_by', 'rejected_by', 'disbursed_by', 'guest'
    )

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer',
    ]
    can_view_audit = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'treasurer',
    ]
    current_member = None
    needs_committee_review = False

    if not is_officer:
        current_member = _get_current_member(request, company)
        if current_member:
            qs = qs.filter(member=current_member)
            if current_member.custom_loan_limit == 0 and not current_member.has_good_repayment_history:
                needs_committee_review = True
        else:
            qs = qs.none()

    if is_officer:
        q_search = request.GET.get('q', '').strip()
        if q_search:
            qs = qs.filter(
                models.Q(member__full_name__icontains=q_search) |
                models.Q(guest__full_name__icontains=q_search)
            )
        status_filter = request.GET.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        category_filter = request.GET.get('category', '').strip()
        if category_filter:
            qs = qs.filter(loan_category=category_filter)

    qs = qs.order_by('-requested_on', '-created_at')

    total_pending = qs.filter(status='pending').aggregate(t=Sum('principal'))['t'] or 0
    total_approved = qs.filter(status='approved').aggregate(t=Sum('principal'))['t'] or 0
    total_disbursed = qs.filter(status='disbursed').aggregate(t=Sum('principal'))['t'] or 0
    total_repaid = (
        qs.filter(status__in=['disbursed', 'closed'])
        .aggregate(t=Sum('repayments__amount'))['t'] or 0
    )

    return render(request, 'chama/internal_loans/list.html', {
        'loans': qs,
        'total_pending': total_pending,
        'total_approved': total_approved,
        'total_disbursed': total_disbursed,
        'total_repaid': total_repaid,
        'total_count': qs.count(),
        'is_officer': is_officer,
        'can_view_audit': can_view_audit,
        'current_member': current_member,
        'needs_committee_review': needs_committee_review,
    })


@login_required
def loan_detail(request, pk):
    """Detail page — works for BOTH internal (member) and external (guest) loans."""
    from apps.customers.models import Customer

    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('member', 'guest', 'loan_type'),
        pk=pk, company=company
    )

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer',
    ]
    current_member = _get_current_member(request, company)

    if not is_officer and (not current_member or loan.member != current_member):
        messages.error(request, 'You do not have permission to view this loan.')
        return redirect('chama:loan_list')

    repayments = loan.repayments.order_by('-date', '-created_at')

    true_available_power = Decimal('0.00')
    display_limit = Decimal('0.00')
    display_taken = Decimal('0.00')
    display_active_debt = Decimal('0.00')

    if loan.member:
        display_limit = loan.member.eligible_loan_limit or Decimal('0.00')
        display_taken = loan.member.total_principal_taken or Decimal('0.00')
        display_active_debt = loan.member.active_loans_total or Decimal('0.00')
        other_active_loans_sum = loan.member.loans.filter(
            status__in=['approved', 'disbursed']
        ).exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
        true_available_power = display_limit - other_active_loans_sum

    elif loan.guest:
        identifier = loan.guest.national_id or loan.guest.phone
        customer = Customer.objects.filter(
            company=company,
            national_id=identifier
        ).first()

        if customer:
            display_limit = customer.custom_loan_limit or Decimal('0.00')
            customer_loans = Loan.objects.filter(
                company=company,
                loan_category='external',
                status__in=['approved', 'disbursed'],
                guest__national_id=identifier
            )
            display_taken = customer_loans.aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
            display_active_debt = sum(l.total_repayable for l in customer_loans)
            other_loans = customer_loans.exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
            true_available_power = display_limit - other_loans

    return render(request, 'chama/internal_loans/detail.html', {
        'loan': loan,
        'repayments': repayments,
        'is_officer': is_officer,
        'current_member': current_member,
        'true_available_power': true_available_power,
        'display_limit': display_limit,
        'display_taken': display_taken,
        'display_active_debt': display_active_debt,
    })


@login_required
def loan_create(request):
    """Member self-service application OR officer manual entry (internal only)."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:loan_list')

    is_officer = request.user.role in ADMIN_ROLES
    current_member = _get_current_member(request, company)

    # ============================================================
    # MEMBER SELF-SERVICE FLOW
    # ============================================================
    if not is_officer:
        if not current_member:
            messages.error(request, 'You are not linked to a Chama member record.')
            return redirect('chama:loan_list')

        is_eligible, reason = check_internal_loan_eligibility(current_member)
        if not is_eligible:
            messages.error(request, reason)
            return redirect('chama:loan_list')

        if request.method == 'POST':
            form = SelfServiceLoanForm(
                request.POST,
                company=company,
                member=current_member,
            )
            if form.is_valid():
                lt = form.cleaned_data['loan_type']
                principal = form.cleaned_data['principal']
                term = form.cleaned_data['term_months']
                purpose = form.cleaned_data['purpose']

                if term > (lt.max_term_months or 999):
                    messages.error(request, f'Term exceeds max for {lt.name} ({lt.max_term_months} months).')
                elif principal > current_member.available_borrowing_power:
                    messages.error(request, f'Amount exceeds your borrowing limit of KES {current_member.available_borrowing_power:,.2f}.')
                else:
                    Loan.objects.create(
                        company=company,
                        member=current_member,
                        loan_type=lt,
                        principal=principal,
                        interest_rate=lt.interest_rate,
                        term_months=term,
                        purpose=purpose,
                        status='pending',
                        requested_on=timezone.localdate(),
                    )
                    messages.success(request, f'✅ Loan application of KES {principal:,.2f} submitted for review.')
                    return redirect('chama:loan_list')
        else:
            form = SelfServiceLoanForm(company=company, member=current_member)

        my_loans = Loan.objects.filter(
            company=company, member=current_member
        ).prefetch_related('repayments').order_by('-requested_on')

        return render(request, 'chama/internal_loans/form.html', {
            'form': form,
            'mode': 'request',
            'current_member': current_member,
            'eligible_limit': current_member.available_borrowing_power,
            'total_contributions': current_member.total_contributions_paid,
            'active_loans': current_member.active_loans_total,
            'my_loans': my_loans,
        })

    # ============================================================
    # OFFICER MANUAL ENTRY
    # ============================================================
    if request.method == 'POST':
        form = LoanForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ Loan #{obj.id} recorded for {obj.member.full_name}.')
            return redirect('chama:loan_list')
    else:
        form = LoanForm(company=company, initial={'requested_on': timezone.localdate()})

    return render(request, 'chama/internal_loans/form.html', {
        'form': form,
        'mode': 'create',
        'is_officer': True,
    })


@login_required
def loan_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Loan, pk=pk, company=company)

    if request.method == 'POST':
        form = LoanForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Loan updated.')
            return redirect('chama:loan_list')
    else:
        form = LoanForm(instance=obj, company=company)

    return render(request, 'chama/internal_loans/form.html', {'form': form, 'mode': 'edit', 'loan': obj, 'is_officer': True})


@login_required
def loan_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Loan, pk=pk, company=company)
    obj.delete()
    messages.info(request, '🗑️ Loan deleted.')
    return redirect('chama:loan_list')


# ============================================================
# INTERNAL LOANS — APPROVAL / DISBURSEMENT
# ============================================================

@login_required
@_require_officer
def loan_approve(request, pk):
    if request.method != 'POST':
        return redirect('chama:loan_list')

    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('member', 'guest', 'loan_type'),
        pk=pk,
        company=company,
    )

    if loan.status != 'pending':
        messages.warning(request, 'Loan is no longer pending.')
        return redirect('chama:loan_list')

    member = loan.member
    guest = loan.guest

    # ── Internal loan: check 3x contributions limit ──
    if member:
        available = member.available_borrowing_power
        if loan.principal > available:
            messages.error(
                request,
                f'Cannot approve: {member.full_name} can only borrow up to '
                f'KES {available:,.2f} '
                f'(3× contributions of KES {member.total_contributions_paid:,.2f}, '
                f'minus outstanding loans of KES {member.active_loans_total:,.2f}).'
            )
            return redirect('chama:loan_list')

    # ── External loan: check customer's custom limit ──
    elif guest:
        from apps.customers.models import Customer
        customer = Customer.objects.filter(
            company=company,
            phone_number=guest.phone
        ).first()

        if customer:
            available = customer.custom_loan_limit
            if loan.principal > available:
                messages.error(
                    request,
                    f'Cannot approve: {guest.full_name} can only borrow up to '
                    f'KES {available:,.2f} (their approved external limit).'
                )
                return redirect('chama:loan_list')
        else:
            messages.warning(request, "Could not find a customer profile to verify limit. Proceeding with approval.")

    else:
        messages.error(request, 'This loan has neither a member nor a guest attached to it.')
        return redirect('chama:loan_list')

    # ── Loan type max_amount check ──
    if loan.loan_type and loan.loan_type.max_amount and loan.principal > loan.loan_type.max_amount:
        messages.error(
            request,
            f'Cannot approve: this amount exceeds the maximum for '
            f'{loan.loan_type.name} (KES {loan.loan_type.max_amount:,.2f}).'
        )
        return redirect('chama:loan_list')

    loan.status = 'approved'
    loan.approved_on = timezone.localdate()
    loan.approved_by = request.user
    loan.save(update_fields=['status', 'approved_on', 'approved_by'])

    borrower_name = member.full_name if member else guest.full_name

    messages.success(
        request,
        f'✅ Loan #{loan.id} approved for {borrower_name} '
        f'(KES {loan.principal:,.2f}).'
    )
    return redirect('chama:loan_list')


@login_required
@_require_officer
def loan_reject(request, pk):
    if request.method != 'POST':
        return redirect('chama:loan_list')
    company = _get_company(request)
    loan = get_object_or_404(Loan, pk=pk, company=company)

    if loan.status != 'pending':
        messages.warning(request, 'Loan is no longer pending.')
        return redirect('chama:loan_list')

    loan.status = 'rejected'
    loan.rejected_by = request.user
    loan.save(update_fields=['status', 'rejected_by'])
    return redirect('chama:loan_list')


@login_required
@_require_officer
@transaction.atomic
def loan_disburse(request, pk):
    if request.method != 'POST':
        return redirect('chama:loan_list')

    company = _get_company(request)
    loan = get_object_or_404(
        Loan.objects.select_related('member', 'guest', 'loan_type'),
        pk=pk,
        company=company,
    )

    if loan.status != 'approved':
        messages.warning(request, 'Only approved loans can be disbursed.')
        return redirect('chama:loan_list')

    member = loan.member
    if member:
        current_limit = member.eligible_loan_limit
        other_loans = member.loans.filter(
            status__in=['approved', 'disbursed']
        ).exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or 0
        actual_available = current_limit - other_loans

        if loan.principal > actual_available:
            messages.error(
                request,
                f'Cannot disburse: {member.full_name} can only borrow up to '
                f'KES {actual_available:,.2f} at this time.'
            )
            return redirect('chama:loan_list')

    loan.status = 'disbursed'
    loan.disbursed_on = timezone.localdate()
    loan.disbursed_by = request.user
    loan.save(update_fields=['status', 'disbursed_on', 'disbursed_by'])

    loan_account = Account.objects.filter(
        company=company, purpose='loans', is_active=True
    ).first()

    if loan_account:
        borrower = (
            loan.member.full_name if loan.member
            else (loan.guest.full_name if loan.guest else 'Guest')
        )
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
            description=f'Loan disbursed #{loan.pk} — {borrower}',
            reference=f'LOAN-{loan.pk}',
            auto_generated=True,
        )
    else:
        messages.warning(
            request,
            'Loan disbursed, but no Loan Fund account exists. '
            'Please create an account with purpose="loans" to track cash flow.'
        )

    borrower_name = (
        member.full_name if member
        else (loan.guest.full_name if loan.guest else 'Guest')
    )
    messages.success(
        request,
        f'✅ Loan #{loan.id} disbursed to {borrower_name} '
        f'(KES {loan.principal:,.2f}).'
    )
    return redirect('chama:loan_list')


# ============================================================
# INTERNAL LOANS — REPAYMENTS
# ============================================================

@login_required
def loan_repayment_pay(request, loan_pk):
    """Member self-service: pay a loan via M-Pesa STK Push."""
    company = _get_company(request)
    loan = get_object_or_404(Loan, pk=loan_pk, company=company)

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer',
    ]
    current_member = _get_current_member(request, company)
    if not is_officer and (not current_member or loan.member != current_member):
        messages.error(request, 'You do not have permission to repay this loan.')
        return redirect('chama:loan_list')

    if loan.status not in ('disbursed', 'approved'):
        messages.warning(request, 'This loan is not active for repayment.')
        return redirect('chama:loan_detail', pk=loan.pk)

    if loan.balance_remaining <= 0:
        messages.info(request, 'This loan is already fully repaid.')
        return redirect('chama:loan_detail', pk=loan.pk)

    if request.method == 'POST':
        amount = request.POST.get('amount', '').strip()
        phone = request.POST.get('phone', '').strip()

        if not amount or not phone:
            messages.error(request, 'Amount and phone number are required.')
        else:
            try:
                amount_dec = Decimal(amount)
                if amount_dec <= 0 or amount_dec > loan.balance_remaining:
                    messages.error(request, f'Amount must be between 1 and KES {loan.balance_remaining}.')
                else:
                    ref = f"L-{loan.member.member_number}" if loan.member else f"L-{loan.pk}"
                    response = _send_chama_stk_push(
                        company=company,
                        phone=phone,
                        amount=int(amount_dec),
                        account_reference=ref,
                        description="Loan Repay",
                    )
                    if str(response.get('ResponseCode')) == '0':
                        messages.success(
                            request,
                            f'✅ STK Push sent to {phone}. Enter your PIN to complete the repayment.'
                        )
                        return redirect('chama:loan_detail', pk=loan.pk)
                    else:
                        messages.error(
                            request,
                            response.get('ResponseDescription') or 'STK Push failed.'
                        )
            except Exception as e:
                messages.error(request, f'Payment error: {e}')

    return render(request, 'chama/internal_loans/repayment_pay.html', {
        'loan': loan,
        'suggested_amount': loan.balance_remaining,
    })


@login_required
def loan_repayment_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, LoanRepayment).select_related('loan', 'loan__member')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer',
    ]
    current_member = None
    if not is_officer:
        current_member = _get_current_member(request, company)
        if current_member:
            qs = qs.filter(loan__member=current_member)
        else:
            qs = qs.none()

    qs = qs.order_by('-date', '-created_at')

    total_repaid = qs.aggregate(t=Sum('amount'))['t'] or 0

    loan_qs = Loan.objects.filter(company=company)
    if not is_officer and current_member:
        loan_qs = loan_qs.filter(member=current_member)

    total_borrowed = loan_qs.aggregate(t=Sum('principal'))['t'] or 0

    return render(request, 'chama/internal_loans/repayment_list.html', {
        'repayments': qs,
        'total_count': qs.count(),
        'total_repaid': total_repaid,
        'total_borrowed': total_borrowed,
        'is_officer': is_officer,
        'current_member': current_member,
    })


@login_required
@transaction.atomic
def loan_repayment_create(request, loan_pk):
    """Officer manual repayment entry (Treasurer / Company Admin / Super Admin)."""
    company = _get_company(request)
    loan = get_object_or_404(Loan, pk=loan_pk, company=company)

    allowed_roles = ['super_admin', 'company_admin', 'treasurer']
    if request.user.role not in allowed_roles:
        messages.error(request, 'Only the Treasurer can record manual repayments.')
        return redirect('chama:loan_detail', pk=loan.pk)

    if loan.status not in ('disbursed', 'approved'):
        messages.warning(request, 'Only active loans can be repaid.')
        return redirect('chama:loan_detail', pk=loan.pk)

    if request.method == 'POST':
        form = LoanRepaymentForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.loan = loan
            obj.save()

            loan_account = Account.objects.filter(
                company=company, purpose='loans', is_active=True
            ).first()

            if loan_account:
                Transaction.objects.create(
                    company=company,
                    account=loan_account,
                    transaction_type='in',
                    amount=obj.amount,
                    date=obj.date,
                    description=f'Loan repayment #{loan.pk} — {loan.member.full_name if loan.member else "Guest"}',
                    reference=f'REPAY-{obj.pk}',
                    auto_generated=True,
                )
            else:
                messages.warning(
                    request,
                    'Repayment saved, but no Loan Fund account exists. '
                    'Please create an account with purpose="loans" to track cash flow.'
                )

            loan.refresh_from_db()
            if loan.is_fully_repaid and loan.status == 'disbursed':
                loan.status = 'closed'
                loan.save(update_fields=['status'])
                messages.success(
                    request,
                    f'✅ Repayment of KES {obj.amount} recorded. '
                    f'Loan #{loan.id} is now FULLY REPAID and closed! 🎉'
                )
            else:
                messages.success(
                    request,
                    f'✅ Manual repayment of KES {obj.amount} recorded. '
                    f'Balance remaining: KES {loan.balance_remaining:,.2f}'
                )

            return redirect('chama:loan_detail', pk=loan.pk)
    else:
        form = LoanRepaymentForm(initial={
            'date': timezone.localdate(),
            'amount': loan.balance_remaining,
        })

    return render(request, 'chama/internal_loans/repayment_form.html', {
        'form': form,
        'loan': loan,
    })


# ============================================================
# INTERNAL LOANS — LIMITS PAGE
# ============================================================

@login_required
def internal_loan_limits(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    is_officer = request.user.role in ADMIN_ROLES
    if not is_officer:
        messages.error(request, 'Only Chama officers can access loan limit management.')
        return redirect('chama:dashboard')

    current_month = timezone.localdate().strftime('%Y-%m')

    members = Member.objects.filter(
        company=company, status='active'
    ).select_related('membership_type').order_by('full_name')

    paid_totals = dict(
        Contribution.objects.filter(
            company=company, paid=True
        ).values_list('member_id').annotate(total=Sum('amount'))
    )

    current_month_paid_member_ids = set(
        Contribution.objects.filter(
            company=company, period=current_month, paid=True
        ).values_list('member_id', flat=True)
    )

    active_loan_totals = {}
    for loan in Loan.objects.filter(
        company=company, status__in=['approved', 'disbursed']
    ).select_related('member'):
        if loan.member_id:
            active_loan_totals[loan.member_id] = (
                active_loan_totals.get(loan.member_id, 0) + loan.principal
            )

    rows = []
    total_expected = 0
    total_collected = 0

    for m in members:
        required = (
            m.membership_type.monthly_contribution if m.membership_type else 0
        )
        total_expected += required
        if m.id in current_month_paid_member_ids:
            total_collected += required

        rows.append({
            'member': m,
            'total_contributions': paid_totals.get(m.id, 0),
            'current_month_paid': m.id in current_month_paid_member_ids,
            'current_month_required': required,
            'custom_limit': m.custom_loan_limit,
            'eligible_limit': m.eligible_loan_limit,
            'has_good_history': m.has_good_repayment_history,
            'active_loans_total': active_loan_totals.get(m.id, 0),
            'available_borrowing_power': m.available_borrowing_power,
            'multiplier_eligible': m.has_good_repayment_history,
        })

    return render(request, 'chama/internal_loans/limits.html', {
        'rows': rows,
        'current_month': current_month,
        'total_expected': total_expected,
        'total_collected': total_collected,
        'is_officer': True,
    })