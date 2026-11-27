# ============================================================
# views.py (main Chama views)
# ============================================================
import datetime
from calendar import month_name
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Sum, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse

from apps.companies.models import Company

from .forms import (
    SavingsForm, ContributionForm, FineForm,
    LoanTypeForm,
    LoanForm, SelfServiceLoanForm, LoanRepaymentForm, MeetingForm,
    AttendanceForm, AnnouncementForm, AccountForm,
    TransactionForm, ExpenseForm, ProjectForm, CommitteeForm,
    CommitteeMemberForm, GuestForm,
)

from .models import (
    Member, MembershipType, Registration,
    Savings, Contribution, Fine,
    Loan, LoanType, LoanRepayment,
    Account, Transaction, Expense,
    Meeting, Attendance,
    Committee, CommitteeMember,
    Announcement, Project, Guest,
)

# ── Import shared helpers AND member views from members_views ──
from .members_views import (
    # helpers reused in this file
    _generate_default_password,
    _cloudinary_configure,
    _upload_to_cloudinary,
    _get_company,
    _company_queryset,
    _next_member_number,
    _get_current_member,
    _get_reset_link,
    _send_invite_email,
    ADMIN_ROLES,
    # member views re-exported for url resolution
    membership_type_list,
    membership_type_create,
    membership_type_edit,
    membership_type_delete,
    registration_list,
    registration_approve,
    registration_reject,
    member_loan_history,
    member_loan_limit_adjust,
)

User = get_user_model()


# ============================================================
#  DECORATORS
# ============================================================

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
    """Chairperson, Vice, Treasurer, Loan Officer, Company Admin/Manager, Super Admin, Secretary."""
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
#  HELPERS
# ============================================================

def _send_chama_stk_push(company, phone, amount, account_reference, description):
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


def _post_contribution_to_pool(contribution):
    company = contribution.company
    existing = Transaction.objects.filter(
        company=company,
        reference=f"CONT-{contribution.pk}"
    ).exists()
    if existing:
        return False
    pool_account = Account.objects.filter(
        company=company, purpose='pool', is_active=True
    ).first()
    if pool_account:
        Transaction.objects.create(
            company=company,
            account=pool_account,
            transaction_type='in',
            amount=contribution.amount,
            date=contribution.date,
            description=f"Contribution for {contribution.period} — {contribution.member.full_name}",
            reference=f"CONT-{contribution.pk}",
            auto_generated=True
        )
        return True
    return False


def _post_to_cashbook(company, account_purpose, transaction_type, amount, date, description, reference, auto_generated=True):
    account = Account.objects.filter(company=company, purpose=account_purpose, is_active=True).first()
    if account:
        Transaction.objects.create(
            company=company,
            account=account,
            transaction_type=transaction_type,
            amount=amount,
            date=date,
            description=description,
            reference=reference,
            auto_generated=auto_generated,
        )
        return True
    return False


# ============================================================
# DASHBOARD
# ============================================================
@login_required
def dashboard(request):
    company = _get_company(request)
    ctx = {'company': company}

    ADMIN_ROLES_DASH = [
        'company_admin', 'super_admin', 'chairperson', 'vice_chairperson',
        'secretary', 'vice_secretary', 'treasurer', 'loan_officer'
    ]

    if company:
        if request.user.role in ADMIN_ROLES_DASH:
            accounts = Account.objects.filter(company=company, is_active=True)
            pool_balance = sum(a.current_balance for a in accounts if a.purpose == 'pool')
            welfare_funds = sum(a.current_balance for a in accounts if a.purpose == 'welfare')
            project_funds = sum(a.current_balance for a in accounts if a.purpose == 'projects')
            loan_funds = sum(a.current_balance for a in accounts if a.purpose == 'loans')
            total_cash = sum(a.current_balance for a in accounts)

            active_loans_qs = Loan.objects.filter(company=company, status__in=['approved', 'disbursed'])
            loans_outstanding = sum(loan.balance_remaining for loan in active_loans_qs)
            loans_disbursed = Loan.objects.filter(company=company, status__in=['disbursed', 'closed']).aggregate(t=Sum('principal'))['t'] or 0
            loans_repaid = LoanRepayment.objects.filter(loan__company=company).aggregate(t=Sum('amount'))['t'] or 0

            ninety_days_ago = timezone.now().date() - timezone.timedelta(days=90)
            non_performing_qs = Loan.objects.filter(
                company=company, status='disbursed', disbursed_on__lt=ninety_days_ago,
            )
            loans_non_performing = sum(loan.balance_remaining for loan in non_performing_qs if loan.balance_remaining > 0)

            projects_count = Project.objects.filter(company=company).count()
            current_year = timezone.now().year
            contributions_this_year = Contribution.objects.filter(
                company=company, paid=True, date__year=current_year
            ).aggregate(t=Sum('amount'))['t'] or 0

            ctx.update({
                'members_count': Member.objects.filter(company=company, status='active').count(),
                'announcements': Announcement.objects.filter(company=company, is_active=True).order_by('-created_at')[:3],
                'savings_total': Savings.objects.filter(company=company).aggregate(t=Sum('amount'))['t'] or 0,
                'total_cash': total_cash,
                'pool_balance': pool_balance,
                'welfare_funds': welfare_funds,
                'project_funds': project_funds,
                'loan_funds': loan_funds,
                'loans_active': active_loans_qs.count(),
                'loans_outstanding': loans_outstanding,
                'loans_disbursed': loans_disbursed,
                'loans_repaid': loans_repaid,
                'loans_non_performing': loans_non_performing,
                'projects_count': projects_count,
                'contributions_this_year': contributions_this_year,
                'current_year': current_year,
                'pending_registrations': Registration.objects.filter(company=company, status='pending').count(),
                'pending_loans': Loan.objects.filter(company=company, status='pending').count(),
                'contributions_total': Contribution.objects.filter(company=company, paid=True).aggregate(t=Sum('amount'))['t'] or 0,
                'fines_total': Fine.objects.filter(company=company, is_paid=False).aggregate(t=Sum('amount'))['t'] or 0,
            })

        current_member = _get_current_member(request, company)
        if current_member:
            current_month = timezone.localdate().strftime('%Y-%m')
            required = (
                current_member.membership_type.monthly_contribution
                if current_member.membership_type else 0
            )
            contributed_total = Contribution.objects.filter(
                member=current_member, paid=True
            ).aggregate(t=Sum('amount'))['t'] or 0
            contributed_this_month = Contribution.objects.filter(
                member=current_member, period=current_month, paid=True
            ).aggregate(t=Sum('amount'))['t'] or 0

            member_active_loans = Loan.objects.filter(
                member=current_member, status__in=['approved', 'disbursed']
            )
            loan_balance = sum(l.balance_remaining for l in member_active_loans)

            fines_unpaid = Fine.objects.filter(member=current_member, is_paid=False).aggregate(t=Sum('amount'))['t'] or 0
            recent_loans = Loan.objects.filter(member=current_member).order_by('-requested_on')[:3]

            ctx.update({
                'member_profile': current_member,
                'my_contributions': contributed_total,
                'contributed_this_month': contributed_this_month,
                'my_required_contribution': required,
                'my_loan_balance': loan_balance,
                'my_fines_unpaid': fines_unpaid,
                'my_recent_loans': recent_loans,
                'current_month': current_month,
            })

    return render(request, 'chama/dashboard.html', ctx)






# ============================================================
# COMMITTEES
# ============================================================
@login_required
def committee_list(request):
    _get_company(request)
    qs = _company_queryset(request, Committee).order_by('name')
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'chairperson', 'vice_chairperson', 'secretary', 'treasurer'
    ]
    return render(request, 'chama/committee_list.html', {
        'committees': qs,
        'is_officer': is_officer,
    })


@login_required
def committee_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:committee_list')

    if request.method == 'POST':
        form = CommitteeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ Committee "{obj.name}" created.')
            return redirect('chama:committee_list')
    else:
        form = CommitteeForm()
    return render(request, 'chama/committee_form.html', {'form': form, 'mode': 'create'})


@login_required
def committee_detail(request, pk):
    company = _get_company(request)
    committee = get_object_or_404(Committee, pk=pk, company=company)
    members = committee.members.select_related('member').order_by('role_in_committee', 'member__full_name')
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'chairperson', 'vice_chairperson', 'secretary'
    ]
    return render(request, 'chama/committee_detail.html', {
        'committee': committee,
        'members': members,
        'is_officer': is_officer,
    })


@login_required
def committee_member_add(request, pk):
    company = _get_company(request)
    committee = get_object_or_404(Committee, pk=pk, company=company)

    if request.method == 'POST':
        form = CommitteeMemberForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.committee = committee
            obj.save()
            messages.success(request, f'✅ {obj.member.full_name} added to {committee.name}.')
            return redirect('chama:committee_detail', pk=committee.pk)
    else:
        form = CommitteeMemberForm(company=company)

    return render(request, 'chama/committee_form.html', {'form': form, 'committee': committee})


@login_required
def committee_member_remove(request, pk, member_pk):
    committee = get_object_or_404(Committee, pk=pk)
    member = get_object_or_404(CommitteeMember, pk=member_pk, committee=committee)
    name = member.member.full_name
    member.delete()
    messages.info(request, f'🗑️ {name} removed from {committee.name}.')
    return redirect('chama:committee_detail', pk=committee.pk)


# ============================================================
# PROJECTS / MEETINGS / ATTENDANCE / ANNOUNCEMENTS
# ============================================================
@login_required
def project_list(request):
    _get_company(request)
    qs = _company_queryset(request, Project).order_by('-start_date')
    return render(request, 'chama/project_list.html', {
        'projects': qs,
        'is_officer': request.user.role in ['super_admin', 'company_admin', 'chairperson', 'treasurer'],
    })


@login_required
def project_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ Project "{obj.name}" created.')
            return redirect('chama:project_list')
    else:
        form = ProjectForm(initial={'start_date': timezone.localdate()})
    return render(request, 'chama/project_form.html', {'form': form, 'mode': 'create'})


@login_required
def meeting_list(request):
    _get_company(request)
    qs = _company_queryset(request, Meeting).order_by('-scheduled_for')
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'secretary', 'treasurer',
    ]
    return render(request, 'chama/meeting_list.html', {
        'meetings': qs,
        'is_officer': is_officer,
    })


@login_required
def meeting_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:meeting_list')

    if request.method == 'POST':
        form = MeetingForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ Meeting "{obj.title}" scheduled.')
            return redirect('chama:meeting_list')
    else:
        form = MeetingForm()

    return render(request, 'chama/meeting_form.html', {'form': form, 'mode': 'create'})


@login_required
def meeting_detail(request, pk):
    company = _get_company(request)
    meeting = get_object_or_404(Meeting, pk=pk, company=company)
    attendance = meeting.attendance.all().select_related('member')
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'secretary', 'treasurer',
    ]
    return render(request, 'chama/meeting_detail.html', {
        'meeting': meeting,
        'attendance': attendance,
        'is_officer': is_officer,
    })


@login_required
def meeting_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Meeting, pk=pk, company=company)

    if request.method == 'POST':
        form = MeetingForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Meeting updated.')
            return redirect('chama:meeting_list')
    else:
        form = MeetingForm(instance=obj)

    return render(request, 'chama/meeting_form.html', {'form': form, 'mode': 'edit', 'meeting': obj})


@login_required
def attendance_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Attendance).select_related('meeting', 'member').order_by('-meeting__scheduled_for')
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'secretary', 'treasurer',
    ]
    current_member = None
    if not is_officer:
        current_member = _get_current_member(request, company)
        if current_member:
            qs = qs.filter(member=current_member)
        else:
            qs = qs.none()
    return render(request, 'chama/attendance_list.html', {
        'attendance': qs,
        'is_officer': is_officer,
    })


@login_required
def attendance_create(request, meeting_pk):
    company = _get_company(request)
    meeting = get_object_or_404(Meeting, pk=meeting_pk, company=company)

    if request.method == 'POST':
        form = AttendanceForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.meeting = meeting
            obj.save()
            messages.success(request, f'✅ Attendance recorded for {obj.member.full_name}.')
            return redirect('chama:meeting_detail', pk=meeting.pk)
    else:
        form = AttendanceForm(company=company)

    return render(request, 'chama/attendance_form.html', {'form': form, 'meeting': meeting})


@login_required
def announcement_list(request):
    _get_company(request)
    qs = _company_queryset(request, Announcement).order_by('-created_at')
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'secretary', 'treasurer',
    ]
    return render(request, 'chama/announcement_list.html', {
        'announcements': qs,
        'is_officer': is_officer,
    })


@login_required
def announcement_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:announcement_list')

    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.created_by = request.user
            obj.save()
            messages.success(request, f'✅ Announcement "{obj.title}" posted.')
            return redirect('chama:announcement_list')
    else:
        form = AnnouncementForm()

    return render(request, 'chama/announcement_form.html', {'form': form, 'mode': 'create'})


# ============================================================
# CONTRIBUTIONS
# ============================================================
@login_required
def contribution_list(request):
    company = _get_company(request)
    if not company:
        return redirect('home')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    ]

    today = timezone.localdate()
    current_month = today.strftime('%Y-%m')
    selected_month = request.GET.get('month', current_month)

    month_choices = []
    start_date = today.replace(day=1) - datetime.timedelta(days=365)
    start_year, start_month = start_date.year, start_date.month

    for i in range(16):
        month_index = (start_month - 1) + i
        year = start_year + (month_index // 12)
        month = (month_index % 12) + 1
        value = f"{year}-{month:02d}"
        label = f"{month_name[month]} {year}"
        month_choices.append({
            'value': value,
            'label': label,
            'is_selected': value == selected_month
        })

    if request.method == 'POST' and 'mark_paid' in request.POST and is_officer:
        member_id = request.POST.get('member_id')
        amount = request.POST.get('amount')
        member = get_object_or_404(Member, pk=member_id, company=company)

        contrib, created = Contribution.objects.get_or_create(
            company=company,
            member=member,
            period=selected_month,
            defaults={
                'amount': amount,
                'paid': True,
                'date': timezone.localdate(),
                'membership_type': member.membership_type
            }
        )
        if not created and not contrib.paid:
            contrib.paid = True
            contrib.date = timezone.localdate()
            contrib.amount = amount
            contrib.save()

        posted = _post_contribution_to_pool(contrib)
        if posted:
            messages.success(request, f"Marked {member.full_name} as paid and updated Pool Account.")
        else:
            messages.warning(request, f"Marked {member.full_name} as paid, but no Pool Account exists.")
        return redirect(f"{request.path}?month={selected_month}")

    if is_officer:
        members = Member.objects.filter(company=company, status='active').order_by('full_name')
        contributions_qs = Contribution.objects.filter(company=company, period=selected_month)
        contrib_map = {c.member_id: c for c in contributions_qs}
        for m in members:
            m.current_contrib = contrib_map.get(m.id)
        total_collected = sum(c.amount for c in contrib_map.values() if c.paid)
        total_expected = sum(
            (m.membership_type.monthly_contribution if m.membership_type else 0)
            for m in members
        )
        context = {
            'is_officer': True,
            'members': members,
            'selected_month': selected_month,
            'month_choices': month_choices,
            'total_collected': total_collected,
            'total_expected': total_expected,
        }
    else:
        current_member = _get_current_member(request, company)
        if current_member:
            contributions_qs = Contribution.objects.filter(
                member=current_member
            ).order_by('-date', '-created_at')
        else:
            contributions_qs = Contribution.objects.none()
        context = {
            'is_officer': False,
            'contributions': contributions_qs,
            'current_member': current_member,
            'selected_month': selected_month,
        }

    return render(request, 'chama/contribution_list.html', context)


@login_required
def contribution_create(request):
    company = _get_company(request)

    if request.method == 'POST':
        form = ContributionForm(request.POST, company=company)
        if form.is_valid():
            contribution = form.save(commit=False)
            contribution.company = company
            if contribution.member and contribution.member.membership_type:
                contribution.membership_type = contribution.member.membership_type
            contribution.save()

            if contribution.paid:
                posted = _post_contribution_to_pool(contribution)
                if posted:
                    messages.success(request, 'Contribution saved and posted to Pool Account.')
                else:
                    messages.warning(
                        request,
                        'Contribution saved, but no General Pool Account exists. '
                        'Please create a Pool account to track cash flow.'
                    )
            else:
                messages.success(request, 'Contribution saved (not yet paid).')

            return redirect('chama:contribution_list')
    else:
        form = ContributionForm(company=company)

    return render(request, 'chama/contribution_form.html', {
        'form': form,
        'mode': 'create'
    })


@login_required
def contribution_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Contribution, pk=pk, company=company)
    was_paid = obj.paid

    if request.method == 'POST':
        form = ContributionForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            contribution = form.save()
            if not was_paid and contribution.paid:
                posted = _post_contribution_to_pool(contribution)
                if posted:
                    messages.success(request, 'Contribution updated and posted to Pool Account.')
                else:
                    messages.warning(request, 'Contribution updated, but no Pool Account exists.')
            else:
                messages.success(request, 'Contribution record updated.')
            return redirect('chama:contribution_list')
    else:
        form = ContributionForm(instance=obj, company=company)

    return render(request, 'chama/contribution_form.html', {
        'form': form,
        'mode': 'edit',
        'contribution': obj,
    })


@login_required
def contribution_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Contribution, pk=pk, company=company)
    name = obj.member.full_name
    amount = obj.amount

    posted_txn = Transaction.objects.filter(
        company=company,
        reference=f"CONT-{obj.pk}"
    ).first()

    if posted_txn:
        Transaction.objects.create(
            company=company,
            account=posted_txn.account,
            transaction_type='out',
            amount=posted_txn.amount,
            date=timezone.localdate(),
            description=f"REVERSAL: Deleted contribution for {obj.period} — {name}",
            reference=f"CONT-{obj.pk}-REVERSAL"
        )
        messages.info(request, 'Contribution was linked to Pool Account. Reversal transaction created.')

    obj.delete()
    messages.success(request, f'Deleted contribution of KES {amount} for {name}.')
    return redirect('chama:contribution_list')


@login_required
def contribution_pay(request):
    company = _get_company(request)
    current_member = _get_current_member(request, company)

    if not current_member:
        messages.error(request, "You are not registered as a Chama member.")
        return redirect('chama:contribution_list')

    current_month = timezone.localdate().strftime('%Y-%m')
    required_amount = (
        current_member.membership_type.monthly_contribution
        if current_member.membership_type else 0
    )
    contributed_this_month = Contribution.objects.filter(
        member=current_member, period=current_month, paid=True
    ).aggregate(t=Sum('amount'))['t'] or 0
    remaining_amount = max(0, required_amount - contributed_this_month)

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        if not phone:
            messages.error(request, "Phone number is required.")
        elif remaining_amount <= 0:
            messages.info(request, "You have already paid for this month.")
            return redirect('chama:contribution_list')
        else:
            try:
                response = _send_chama_stk_push(
                    company=company,
                    phone=phone,
                    amount=int(remaining_amount),
                    account_reference=f"C-{current_member.member_number}",
                    description=f"Chama Contribution {current_month}",
                )
                if str(response.get('ResponseCode')) == '0':
                    messages.success(
                        request,
                        f"✅ STK Push sent to {phone}. Please enter your M-Pesa PIN to complete the payment."
                    )
                    return redirect('chama:contribution_list')
                else:
                    messages.error(
                        request,
                        response.get('ResponseDescription') or 'STK Push failed. Please try again.'
                    )
            except Exception as e:
                messages.error(request, f"Payment error: {e}")

    context = {
        'member': current_member,
        'current_month': current_month,
        'required_amount': required_amount,
        'contributed_this_month': contributed_this_month,
        'remaining_amount': remaining_amount,
    }
    return render(request, 'chama/contribution_pay.html', context)


@login_required
def contribution_pay_self_service(request):
    company = _get_company(request)
    current_member = _get_current_member(request, company)

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    ]

    if not current_member:
        if is_officer:
            messages.info(request, "As an officer, you manage contributions from the main Contributions page.")
            return redirect('chama:contribution_list')
        else:
            messages.error(request, "You are not registered as a Chama member.")
            return redirect('chama:contribution_list')

    current_month = timezone.localdate().strftime('%Y-%m')
    required_amount = (
        current_member.membership_type.monthly_contribution
        if current_member.membership_type else 0
    )
    contributed_this_month = Contribution.objects.filter(
        member=current_member, period=current_month, paid=True
    ).aggregate(t=Sum('amount'))['t'] or 0
    remaining_amount = max(0, required_amount - contributed_this_month)

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        if not phone:
            messages.error(request, "Phone number is required.")
        elif remaining_amount <= 0:
            messages.info(request, "You have already paid for this month.")
            return redirect('chama:contribution_list')
        else:
            try:
                response = _send_chama_stk_push(
                    company=company,
                    phone=phone,
                    amount=int(remaining_amount),
                    account_reference=f"C-{current_member.member_number}",
                    description=f"Chama Contribution {current_month}",
                )
                if str(response.get('ResponseCode')) == '0':
                    messages.success(
                        request,
                        f"✅ STK Push sent to {phone}. Please enter your M-Pesa PIN to complete the payment."
                    )
                    return redirect('chama:contribution_list')
                else:
                    messages.error(
                        request,
                        response.get('ResponseDescription') or 'STK Push failed. Please try again.'
                    )
            except Exception as e:
                messages.error(request, f"Payment error: {e}")

    context = {
        'member': current_member,
        'current_month': current_month,
        'required_amount': required_amount,
        'contributed_this_month': contributed_this_month,
        'remaining_amount': remaining_amount,
    }
    return render(request, 'chama/contribution_pay.html', context)


# ============================================================
# SAVINGS
# ============================================================
@login_required
def savings_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Savings).select_related('member')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    ]
    current_member = None
    if not is_officer:
        current_member = _get_current_member(request, company)
        if current_member:
            qs = qs.filter(member=current_member)
        else:
            qs = qs.none()

    q = request.GET.get('q', '').strip()
    if q and is_officer:
        qs = qs.filter(
            models.Q(member__full_name__icontains=q) |
            models.Q(member__member_number__icontains=q) |
            models.Q(reference__icontains=q)
        )

    qs = qs.order_by('-date', '-created_at')
    total = qs.aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'chama/savings_list.html', {
        'savings': qs,
        'total_savings': total,
        'total_count': qs.count(),
        'is_officer': is_officer,
        'current_member': current_member,
    })


@login_required
@transaction.atomic
def savings_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:savings_list')

    if request.method == 'POST':
        form = SavingsForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            posted = _post_to_cashbook(
                company=company,
                account_purpose='pool',
                transaction_type='in',
                amount=obj.amount,
                date=obj.date,
                description=f'Savings deposit — {obj.member.full_name}',
                reference=f'SAV-{obj.pk}'
            )
            if posted:
                messages.success(request, f'✅ Savings of KES {obj.amount} recorded for {obj.member.full_name}.')
            else:
                messages.warning(request, f'✅ Savings recorded, but no General Pool account exists to track cash flow.')
            return redirect('chama:savings_list')
    else:
        form = SavingsForm(company=company, initial={'date': timezone.localdate()})

    return render(request, 'chama/savings_form.html', {
        'form': form,
        'mode': 'create',
    })


@login_required
def savings_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Savings, pk=pk, company=company)

    if request.method == 'POST':
        form = SavingsForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Savings record updated.')
            return redirect('chama:savings_list')
    else:
        form = SavingsForm(instance=obj, company=company)

    return render(request, 'chama/savings_form.html', {
        'form': form,
        'mode': 'edit',
        'savings': obj,
    })


@login_required
@transaction.atomic
def savings_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Savings, pk=pk, company=company)
    member_name = obj.member.full_name
    amount = obj.amount

    posted_txn = Transaction.objects.filter(company=company, reference=f'SAV-{obj.pk}').first()
    if posted_txn:
        Transaction.objects.create(
            company=company,
            account=posted_txn.account,
            transaction_type='out',
            amount=posted_txn.amount,
            date=timezone.localdate(),
            description=f"REVERSAL: Deleted savings — {member_name}",
            reference=f"SAV-{obj.pk}-REVERSAL",
            auto_generated=True
        )

    obj.delete()
    messages.info(request, f'🗑️ Deleted savings of KES {amount} for {member_name}.')
    return redirect('chama:savings_list')


# ============================================================
# FINES
# ============================================================
@login_required
def fine_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Fine).select_related('member')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    ]
    current_member = None
    if not is_officer:
        current_member = _get_current_member(request, company)
        if current_member:
            qs = qs.filter(member=current_member)
        else:
            qs = qs.none()

    q = request.GET.get('q', '').strip()
    if q and is_officer:
        qs = qs.filter(
            models.Q(member__full_name__icontains=q) |
            models.Q(member__member_number__icontains=q) |
            models.Q(reason__icontains=q)
        )

    paid_filter = request.GET.get('paid', '').strip()
    if paid_filter == 'yes':
        qs = qs.filter(is_paid=True)
    elif paid_filter == 'no':
        qs = qs.filter(is_paid=False)

    qs = qs.order_by('-date', '-created_at')

    total_paid = qs.filter(is_paid=True).aggregate(t=Sum('amount'))['t'] or 0
    total_unpaid = qs.filter(is_paid=False).aggregate(t=Sum('amount'))['t'] or 0

    return render(request, 'chama/fine_list.html', {
        'fines': qs,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_count': qs.count(),
        'is_officer': is_officer,
        'current_member': current_member,
    })


@login_required
def fine_pay(request, pk):
    company = _get_company(request)
    fine = get_object_or_404(Fine, pk=pk, company=company)

    current_member = _get_current_member(request, company)
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    ]
    if not is_officer and (not current_member or fine.member != current_member):
        messages.error(request, 'You do not have permission to pay this fine.')
        return redirect('chama:fine_list')

    if fine.is_paid:
        messages.info(request, 'This fine is already paid.')
        return redirect('chama:fine_list')

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        if not phone:
            messages.error(request, 'Phone number is required.')
            return render(request, 'chama/fine_pay.html', {
                'fine': fine,
                'default_phone': fine.member.phone,
            })
        try:
            response = _send_chama_stk_push(
                company=company,
                phone=phone,
                amount=int(fine.amount),
                account_reference=f"F-{fine.member.member_number}",
                description=f"Chama fine",
            )
            if str(response.get('ResponseCode')) == '0':
                messages.success(
                    request,
                    f'✅ STK Push sent to {phone}. Enter your PIN to complete payment.'
                )
                return redirect('chama:fine_list')
            else:
                messages.error(
                    request,
                    response.get('ResponseDescription') or 'STK Push failed.'
                )
        except Exception as e:
            messages.error(request, f'Payment error: {e}')

    return render(request, 'chama/fine_pay.html', {
        'fine': fine,
        'default_phone': fine.member.phone,
    })


@login_required
@transaction.atomic
def fine_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:fine_list')

    if request.method == 'POST':
        form = FineForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()

            if obj.is_paid:
                posted = _post_to_cashbook(
                    company=company,
                    account_purpose='welfare',
                    transaction_type='in',
                    amount=obj.amount,
                    date=obj.date,
                    description=f'Fine paid — {obj.member.full_name}: {obj.reason}',
                    reference=f'FINE-{obj.pk}'
                )
                if not posted:
                    messages.warning(request, 'Fine recorded, but no Welfare/Pool account exists to track cash flow.')

            messages.success(
                request,
                f'✅ Fine of KES {obj.amount} recorded for {obj.member.full_name}.'
            )
            return redirect('chama:fine_list')
    else:
        form = FineForm(company=company, initial={'date': timezone.localdate()})

    return render(request, 'chama/fine_form.html', {
        'form': form,
        'mode': 'create',
    })


@login_required
@transaction.atomic
def fine_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Fine, pk=pk, company=company)
    was_paid = obj.is_paid

    if request.method == 'POST':
        form = FineForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            fine = form.save()
            if not was_paid and fine.is_paid:
                posted = _post_to_cashbook(
                    company=company,
                    account_purpose='welfare',
                    transaction_type='in',
                    amount=fine.amount,
                    date=fine.date,
                    description=f'Fine paid — {fine.member.full_name}: {fine.reason}',
                    reference=f'FINE-{fine.pk}'
                )
                if posted:
                    messages.success(request, 'Fine record updated and posted to account.')
                else:
                    messages.warning(request, 'Fine updated, but no Welfare/Pool account exists.')
            else:
                messages.success(request, '✅ Fine record updated.')
            return redirect('chama:fine_list')
    else:
        form = FineForm(instance=obj, company=company)

    return render(request, 'chama/fine_form.html', {
        'form': form,
        'mode': 'edit',
        'fine': obj,
    })


@login_required
@transaction.atomic
def fine_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Fine, pk=pk, company=company)
    name = obj.member.full_name
    amount = obj.amount

    posted_txn = Transaction.objects.filter(company=company, reference=f'FINE-{obj.pk}').first()
    if posted_txn:
        Transaction.objects.create(
            company=company,
            account=posted_txn.account,
            transaction_type='out',
            amount=posted_txn.amount,
            date=timezone.localdate(),
            description=f"REVERSAL: Deleted fine — {name}",
            reference=f"FINE-{obj.pk}-REVERSAL",
            auto_generated=True
        )

    obj.delete()
    messages.info(request, f'🗑️ Deleted fine of KES {amount} for {name}.')
    return redirect('chama:fine_list')







# ============================================================
# TRANSACTIONS — CREATE / EDIT / DELETE
# ============================================================

@login_required
def transaction_create(request):
    """Create a manual cashbook transaction."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:transaction_list')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Treasury officers can add transactions.')
        return redirect('chama:transaction_list')

    if request.method == 'POST':
        form = TransactionForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.auto_generated = False
            obj.save()
            messages.success(
                request,
                f'✅ Transaction recorded: {obj.get_transaction_type_display()} '
                f'KES {obj.amount:,.2f} — {obj.account.name}.'
            )
            return redirect('chama:transaction_list')
    else:
        form = TransactionForm(company=company, initial={
            'date': timezone.localdate(),
        })

    return render(request, 'chama/transaction_form.html', {
        'form': form,
        'mode': 'create',
    })


@login_required
def transaction_edit(request, pk):
    """Edit an existing manual transaction."""
    company = _get_company(request)
    obj = get_object_or_404(Transaction, pk=pk, company=company)

    if obj.auto_generated:
        messages.warning(
            request,
            'Auto-generated transactions cannot be edited. '
            'Edit or delete the source record (contribution, loan, etc.) instead.'
        )
        return redirect('chama:transaction_list')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Treasury officers can edit transactions.')
        return redirect('chama:transaction_list')

    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Transaction #{obj.pk} updated.')
            return redirect('chama:transaction_list')
    else:
        form = TransactionForm(instance=obj, company=company)

    return render(request, 'chama/transaction_form.html', {
        'form': form,
        'mode': 'edit',
        'transaction': obj,
    })


@login_required
def transaction_delete(request, pk):
    """Delete a manual transaction."""
    company = _get_company(request)
    obj = get_object_or_404(Transaction, pk=pk, company=company)

    if obj.auto_generated:
        messages.warning(
            request,
            'Auto-generated transactions cannot be deleted directly. '
            'Delete the source record (contribution, loan, etc.) instead.'
        )
        return redirect('chama:transaction_list')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'chairperson', 'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Treasury officers can delete transactions.')
        return redirect('chama:transaction_list')

    if request.method == 'POST':
        txn_id = obj.pk
        obj.delete()
        messages.info(request, f'🗑️ Transaction #{txn_id} deleted.')
        return redirect('chama:transaction_list')

    return render(request, 'chama/transaction_confirm_delete.html', {
        'transaction': obj,
    })


@login_required
def transaction_list(request):
    """Cashbook — list all manual transactions (auto_generated=False)."""
    company = _get_company(request)
    if not company:
        return redirect('chama:dashboard')

    qs = Transaction.objects.filter(
        company=company,
        auto_generated=False,
    ).select_related('account').order_by('-date', '-created_at')

    # Optional filters
    account_id = request.GET.get('account', '').strip()
    if account_id:
        qs = qs.filter(account_id=account_id)

    tx_type = request.GET.get('type', '').strip()
    if tx_type in ('in', 'out'):
        qs = qs.filter(transaction_type=tx_type)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(description__icontains=q) |
            models.Q(reference__icontains=q)
        )

    total_in = qs.filter(transaction_type='in').aggregate(t=Sum('amount'))['t'] or 0
    total_out = qs.filter(transaction_type='out').aggregate(t=Sum('amount'))['t'] or 0

    accounts = Account.objects.filter(company=company, is_active=True)

    return render(request, 'chama/transaction_list.html', {
        'transactions': qs,
        'accounts': accounts,
        'total_in': total_in,
        'total_out': total_out,
        'net_flow': total_in - total_out,
        'total_count': qs.count(),
        'is_officer': request.user.role in ADMIN_ROLES,
    })






# ============================================================
# EXPENSES — CREATE / EDIT / DELETE
# ============================================================

@login_required
def expense_list(request):
    """List all expenses (money out of the pool)."""
    company = _get_company(request)
    if not company:
        return redirect('chama:dashboard')

    qs = Expense.objects.filter(company=company).order_by('-date', '-created_at')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(title__icontains=q) |
            models.Q(reference__icontains=q) |
            models.Q(description__icontains=q)
        )

    # Category filter
    category = request.GET.get('category', '').strip()
    if category:
        qs = qs.filter(category=category)

    total = qs.aggregate(t=Sum('amount'))['t'] or 0

    # Build distinct category list from model choices or existing records
    try:
        categories = [c[0] for c in Expense.CATEGORY_CHOICES]
    except AttributeError:
        # Fallback: pull distinct categories that actually exist in the DB
        categories = list(
            Expense.objects.filter(company=company)
            .exclude(category__isnull=True)
            .exclude(category='')
            .values_list('category', flat=True)
            .distinct()
        )

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'treasurer',
    ]

    return render(request, 'chama/expense_list.html', {
        'expenses': qs,
        'total_expenses': total,
        'total_count': qs.count(),
        'categories': categories,
        'is_officer': is_officer,
    })


@login_required
def expense_create(request):
    """Record a new expense (money out)."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:expense_list')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Treasury officers can record expenses.')
        return redirect('chama:expense_list')

    if request.method == 'POST':
        form = ExpenseForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(
                request,
                f'✅ Expense recorded: KES {obj.amount:,.2f} — {obj.title}.'
            )
            return redirect('chama:expense_list')
    else:
        form = ExpenseForm(company=company, initial={
            'date': timezone.localdate(),
        })

    return render(request, 'chama/expense_form.html', {
        'form': form,
        'mode': 'create',
    })


@login_required
def expense_edit(request, pk):
    """Edit an existing expense."""
    company = _get_company(request)
    obj = get_object_or_404(Expense, pk=pk, company=company)

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Treasury officers can edit expenses.')
        return redirect('chama:expense_list')

    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Expense #{obj.pk} updated.')
            return redirect('chama:expense_list')
    else:
        form = ExpenseForm(instance=obj, company=company)

    return render(request, 'chama/expense_form.html', {
        'form': form,
        'mode': 'edit',
        'expense': obj,
    })


@login_required
def expense_delete(request, pk):
    """Delete an expense."""
    company = _get_company(request)
    obj = get_object_or_404(Expense, pk=pk, company=company)

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'chairperson', 'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Treasury officers can delete expenses.')
        return redirect('chama:expense_list')

    if request.method == 'POST':
        expense_id = obj.pk
        title = obj.title
        obj.delete()
        messages.info(request, f'🗑️ Expense #{expense_id} ({title}) deleted.')
        return redirect('chama:expense_list')

    return render(request, 'chama/expense_confirm_delete.html', {
        'expense': obj,
    })







# ============================================================
# ACCOUNTS / TRANSACTIONS
# ============================================================
@login_required
def account_list(request):
    _get_company(request)
    qs = _company_queryset(request, Account).order_by('name')

    total_cash = sum(a.current_balance for a in qs)
    pool_balance = sum(a.current_balance for a in qs if a.purpose == 'pool')
    allocated_total = sum(a.current_balance for a in qs if a.purpose != 'pool')

    return render(request, 'chama/account_list.html', {
        'accounts': qs,
        'total_cash': total_cash,
        'pool_balance': pool_balance,
        'allocated_total': allocated_total,
        'is_officer': request.user.role in ['super_admin', 'company_admin', 'chairperson', 'treasurer'],
    })


@login_required
def account_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ Account "{obj.name}" created.')
            return redirect('chama:account_list')
    else:
        form = AccountForm()
    return render(request, 'chama/account_form.html', {'form': form, 'mode': 'create'})


@login_required
def account_edit(request, pk):
    company = _get_company(request)
    account = get_object_or_404(Account, pk=pk, company=company)

    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account updated successfully.')
            return redirect('chama:account_list')
    else:
        form = AccountForm(instance=account)

    return render(request, 'chama/account_form.html', {'form': form, 'account': account})


@login_required
def account_delete(request, pk):
    company = _get_company(request)
    account = get_object_or_404(Account, pk=pk, company=company)

    if request.method == 'POST':
        account.delete()
        messages.success(request, 'Account deleted.')
        return redirect('chama:account_list')

    return render(request, 'chama/account_confirm_delete.html', {'account': account})


@login_required
def account_transfer(request):
    company = _get_company(request)
    if not company:
        return redirect('home')

    accounts = Account.objects.filter(company=company, is_active=True)

    if request.method == 'POST':
        from_id = request.POST.get('from_account')
        to_id = request.POST.get('to_account')
        amount_raw = request.POST.get('amount')
        description = request.POST.get('description', 'Internal Transfer')

        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")
        except (ValueError, TypeError):
            messages.error(request, "Please enter a valid amount.")
            return render(request, 'chama/account_transfer.html', {'accounts': accounts})

        if from_id == to_id:
            messages.error(request, "Source and destination accounts must be different.")
            return render(request, 'chama/account_transfer.html', {'accounts': accounts})

        from_account = get_object_or_404(Account, pk=from_id, company=company)
        to_account = get_object_or_404(Account, pk=to_id, company=company)

        if from_account.current_balance < amount:
            messages.error(
                request,
                f"Insufficient funds in {from_account.name}. "
                f"Available: KES {from_account.current_balance:,.2f}"
            )
            return render(request, 'chama/account_transfer.html', {'accounts': accounts})

        Transaction.objects.create(
            company=company,
            account=from_account,
            transaction_type='out',
            amount=amount,
            date=timezone.localdate(),
            description=f"Transfer to {to_account.name} — {description}",
            reference=f"TRF-OUT-{timezone.now().timestamp()}",
        )
        Transaction.objects.create(
            company=company,
            account=to_account,
            transaction_type='in',
            amount=amount,
            date=timezone.localdate(),
            description=f"Transfer from {from_account.name} — {description}",
            reference=f"TRF-IN-{timezone.now().timestamp()}",
        )

        messages.success(
            request,
            f"✅ Transferred KES {amount:,.2f} from {from_account.name} to {to_account.name}."
        )
        return redirect('chama:account_list')

    return render(request, 'chama/account_transfer.html', {'accounts': accounts})