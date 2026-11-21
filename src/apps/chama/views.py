from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Sum, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
import time
import cloudinary
import cloudinary.uploader
from apps.companies.models import Company
from functools import wraps
from django.http import HttpResponseForbidden
from django.utils import timezone
from datetime import datetime
import json
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from .forms import (
    MemberForm, MembershipTypeForm,
    SavingsForm, ContributionForm, FineForm,
    SelfServiceContributionForm, 
    LoanTypeForm, LoanForm, SelfServiceLoanForm, LoanRepaymentForm,
    MeetingForm, AttendanceForm, AnnouncementForm,
    AccountForm, TransactionForm, ExpenseForm, ProjectForm,
    CommitteeForm, CommitteeMemberForm, GuestForm,
)

from .models import (
    Member, MembershipType, Registration,
    Savings, Contribution, Fine,
    Loan, LoanType, LoanRepayment,
    Account, Transaction, Expense,
    Meeting, Attendance,
    Committee, Meeting, Attendance, Announcement,
    Account, Transaction, Expense, Project,
    Committee, CommitteeMember,
)



User = get_user_model()




# ============================================================
# GLOBAL CONSTANTS
# ============================================================
ADMIN_ROLES = [
    'super_admin', 'company_admin', 'company_manager',
    'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    'vice_secretary', 'loan_officer',
]



# ============================================================
#  HELPERS
# ============================================================

def _require_loan_policy_setter(view_func):
    """
    Only Chairperson, Treasurer, Company Admin, or Super Admin
    may create/edit/delete Loan Types.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        allowed = {
            'super_admin', 'company_admin',
            'chairperson', 'treasurer',
        }
        if not request.user.is_authenticated:
            return redirect('/auth/login/')
        if getattr(request.user, 'role', None) not in allowed:
            messages.error(request, 'Only the Chairperson or Treasurer can set loan policy.')
            return redirect('chama:loan_type_list')
        return view_func(request, *args, **kwargs)
    return _wrapped

def _require_officer(view_func):
    """
    Only Chairperson, Vice Chairperson, Treasurer, Loan Officer,
    Company Admin, Company Manager, or Super Admin.
    """
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

def _generate_default_password(company):
    """
    Generate a default password from the company name.
    
    Takes the first word of the company name, capitalizes it, and appends '@12345'.
    
    Examples:
        'TAMBUL HUTSLE YOUTH' → 'Tambul@12345'
        'KALWAL FARM'         → 'Kalwal@12345'
        'FIELDMAX SHOP'       → 'Fieldmax@12345'
    """
    if not company or not company.name:
        return 'Chama@12345'

    # Get the first word of the company name
    first_word = company.name.strip().split()[0]

    # Capitalize properly (first letter upper, rest lower)
    first_word = first_word.capitalize()

    return f"{first_word}@12345"

def _cloudinary_configure():
    """Match the pattern used in epa_shop views."""
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )

def _upload_to_cloudinary(uploaded_file, folder='chama/members'):
    """
    Upload a file to Cloudinary and return the public_id.
    Returns None on failure or if no file is provided.
    """
    if not uploaded_file:
        return None

    try:
        _cloudinary_configure()

        base = f"{folder}/p_{int(time.time() * 1000)}"

        is_pdf = uploaded_file.name.lower().endswith('.pdf')
        resource_type = 'raw' if is_pdf else 'image'

        result = cloudinary.uploader.upload(
            uploaded_file,
            public_id=base,
            overwrite=False,
            resource_type=resource_type,
        )
        public_id = result.get('public_id') or base
        print(f"✅ Cloudinary upload OK: {public_id}")
        return public_id
    except Exception as e:
        import traceback
        print(f"❌ Cloudinary upload FAILED: {e}")
        traceback.print_exc()
        return None

def _get_company(request):
    """Resolve the active company for the current request."""
    company = getattr(request, 'company', None) or getattr(request, 'current_company', None)
    if company:
        return company
    if request.user.is_authenticated and getattr(request.user, 'company_id', None):
        return request.user.company
    company_id = request.session.get('viewing_company_id') or request.session.get('company_id')
    if company_id:
        return Company.objects.filter(pk=company_id).first()
    return None

def _company_queryset(request, model, **filters):
    company = _get_company(request)
    qs = model.objects.all()
    if company:
        qs = qs.filter(company=company, **filters)
    else:
        qs = qs.filter(**filters)
    return qs

def _next_member_number(company):
    """Generate the next sequential member number for a company."""
    last_member = (
        Member.objects
        .filter(company=company)
        .exclude(member_number__isnull=True)
        .exclude(member_number='')
        .order_by('-id')
        .first()
    )
    if not last_member or not last_member.member_number:
        return "M-00001"
    try:
        current = int(last_member.member_number.split('-')[-1])
        return f"M-{current + 1:05d}"
    except (ValueError, IndexError):
        return "M-00001"

def _get_current_member(request, company):
    """
    Get the Member record linked to the current logged-in user.
    Returns None if the user is not linked to any member in this company.
    """
    if not company or not request.user.is_authenticated:
        return None
    return Member.objects.filter(company=company, user=request.user).first()

def _send_chama_stk_push(company, phone, amount, account_reference, description):
    """
    Wrapper around apps.mpesa.services.send_stk_push.

    - Resolves the company's default M-Pesa config
    - Normalises the phone (Safaricom expects 2547xxxxxxxx)
    - Sends the STK push via Daraja
    - Returns the raw Daraja response dict (with ResponseCode == '0' on success)

    Raises RuntimeError on failure.
    """
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
        account_reference=(account_reference or '')[:12],   # Safaricom limit
        description=(description or 'Chama payment')[:13],
    )
    
def _post_contribution_to_pool(contribution):
    """
    Helper function: Automatically creates a Money-In transaction 
    in the General Pool Account when a contribution is marked as paid.
    """
    company = contribution.company
    
    # Check if this contribution has already been posted
    existing = Transaction.objects.filter(
        company=company,
        reference=f"CONT-{contribution.pk}"
    ).exists()
    if existing:
        return False  # Already posted, skip
        
    pool_account = Account.objects.filter(
        company=company, 
        purpose='pool', 
        is_active=True
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
    """
    Reusable helper to post a transaction to the appropriate account.
    """
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
    
    # 1. Define who gets to see the global financials
    ADMIN_ROLES = [
        'company_admin', 'super_admin', 'chairperson', 'vice_chairperson',
        'secretary', 'vice_secretary', 'treasurer', 'loan_officer'
    ]
    
    if company:
        # ============================================================
        # GLOBAL VIEW (Admins & Committee Members Only)
        # ============================================================
        if request.user.role in ADMIN_ROLES:
            
            # --- Accounts Logic ---
            accounts = Account.objects.filter(company=company, is_active=True)
            
            pool_balance = sum(a.current_balance for a in accounts if a.purpose == 'pool')
            welfare_funds = sum(a.current_balance for a in accounts if a.purpose == 'welfare')
            project_funds = sum(a.current_balance for a in accounts if a.purpose == 'projects')
            loan_funds = sum(a.current_balance for a in accounts if a.purpose == 'loans')
            total_cash = sum(a.current_balance for a in accounts)

            # --- Loans Logic ---
            active_loans_qs = Loan.objects.filter(company=company, status__in=['approved', 'disbursed'])
            loans_outstanding = sum(loan.balance_remaining for loan in active_loans_qs)
            
            loans_disbursed = Loan.objects.filter(company=company, status__in=['disbursed', 'closed']).aggregate(t=Sum('principal'))['t'] or 0
            loans_repaid = LoanRepayment.objects.filter(loan__company=company).aggregate(t=Sum('amount'))['t'] or 0
            
            ninety_days_ago = timezone.now().date() - timezone.timedelta(days=90)
            non_performing_qs = Loan.objects.filter(
                company=company, 
                status='disbursed',
                disbursed_on__lt=ninety_days_ago,
            )
            loans_non_performing = sum(loan.balance_remaining for loan in non_performing_qs if loan.balance_remaining > 0)

            # --- Projects & Contributions Logic ---
            projects_count = Project.objects.filter(company=company).count()
            
            current_year = timezone.now().year
            contributions_this_year = Contribution.objects.filter(
                company=company, 
                paid=True, 
                date__year=current_year
            ).aggregate(t=Sum('amount'))['t'] or 0

            # --- Update Context ---
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

        # ============================================================
        # INDIVIDUAL VIEW
        # ============================================================
        current_member = _get_current_member(request, company)
        if current_member:
            current_month = timezone.localdate().strftime('%Y-%m')
            required = (
                current_member.membership_type.monthly_contribution
                if current_member.membership_type else 0
            )
            
            # 👇 NEW: Calculate TOTAL contributions (lifetime) for the big number
            contributed_total = Contribution.objects.filter(
                member=current_member, paid=True
            ).aggregate(t=Sum('amount'))['t'] or 0
            
            # 👇 NEW: Calculate just for this month to see if they are up to date
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
                'my_contributions': contributed_total, # 👈 Shows lifetime total
                'contributed_this_month': contributed_this_month, # 👈 Shows if current month is paid
                'my_required_contribution': required,
                'my_loan_balance': loan_balance,
                'my_fines_unpaid': fines_unpaid,
                'my_recent_loans': recent_loans,
                'current_month': current_month,
            })

    return render(request, 'chama/dashboard.html', ctx)



# ============================================================
# MEMBERS MEMBERSHIP TYPES, REGISTRATION, & COMMITTEES
# ============================================================
@login_required
def member_list(request):
    qs = _company_queryset(request, Member).select_related('membership_type', 'user')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(full_name__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(member_number__icontains=q) |
            models.Q(email__icontains=q)
        )

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by('full_name')
    return render(request, 'chama/member_list.html', {'members': qs})

@login_required
def member_detail(request, pk):
    """Show a full profile for a member."""
    company = _get_company(request)
    member = get_object_or_404(
        Member.objects.select_related('membership_type', 'user'),
        pk=pk,
        company=company
    )

    total_savings = (
        Savings.objects.filter(member=member)
        .aggregate(total=Sum('amount'))['total'] or 0
    )

    total_contributions = (
        Contribution.objects.filter(member=member, paid=True)
        .aggregate(total=Sum('amount'))['total'] or 0
    )

    total_fines = (
        Fine.objects.filter(member=member, is_paid=False)
        .aggregate(total=Sum('amount'))['total'] or 0
    )

    active_loans_qs = Loan.objects.filter(
        member=member, status__in=['approved', 'disbursed']
    )
    active_loans_count = active_loans_qs.count()
    active_loans_outstanding = (
        active_loans_qs.aggregate(total=Sum('principal'))['total'] or 0
    )

    recent_savings = (
        Savings.objects.filter(member=member)
        .order_by('-date', '-created_at')[:5]
    )
    recent_contributions = (
        Contribution.objects.filter(member=member)
        .order_by('-date', '-created_at')[:5]
    )
    recent_loans = (
        Loan.objects.filter(member=member)
        .order_by('-requested_on', '-created_at')[:5]
    )

    return render(request, 'chama/member_detail.html', {
        'member': member,
        'total_savings': total_savings,
        'total_contributions': total_contributions,
        'total_fines': total_fines,
        'active_loans_count': active_loans_count,
        'active_loans_outstanding': active_loans_outstanding,
        'recent_savings': recent_savings,
        'recent_contributions': recent_contributions,
        'recent_loans': recent_loans,
    })

@login_required
@transaction.atomic
def member_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:member_list')

    # Fallback password if left blank
    fallback_password = _generate_default_password(company)

    if request.method == 'POST':
        form = MemberForm(
            request.POST,
            request.FILES,
            company=company,
            fallback_password=fallback_password,   # 👈 pass dynamic default
        )
        if form.is_valid():
            member = form.save(commit=False)
            member.company = company

            # 1. Get the custom password (or fall back)
            custom_password = form.cleaned_data.get('default_password', '').strip()
            final_password = custom_password if custom_password else fallback_password

            # Auto-generate member number
            if not getattr(member, 'member_number', None):
                member.member_number = _next_member_number(company)

            # Cloudinary uploads
            if request.FILES.get('passport_photo'):
                member.passport_photo = _upload_to_cloudinary(request.FILES.get('passport_photo'))
            if request.FILES.get('id_front'):
                member.id_front = _upload_to_cloudinary(request.FILES.get('id_front'))
            if request.FILES.get('id_back'):
                member.id_back = _upload_to_cloudinary(request.FILES.get('id_back'))
            if request.FILES.get('kra_certificate'):
                member.kra_certificate = _upload_to_cloudinary(request.FILES.get('kra_certificate'))
            if request.FILES.get('good_conduct'):
                member.good_conduct = _upload_to_cloudinary(request.FILES.get('good_conduct'))

            # 2. Link or create a User account
            if not member.user:
                existing_user = None
                if member.email:
                    existing_user = User.objects.filter(email__iexact=member.email).first()
                elif member.phone:
                    existing_user = User.objects.filter(username=member.phone).first()

                if not existing_user:
                    username_base = member.phone or member.email or f"member_{member.member_number.lower()}"
                    username = username_base
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{username_base}_{counter}"
                        counter += 1

                    existing_user = User.objects.create(
                        username=username,
                        email=member.email or '',
                        first_name=(member.full_name.split()[0] if member.full_name else ''),
                        last_name=(' '.join(member.full_name.split()[1:]) if member.full_name else ''),
                        company=company,
                        role='member',
                        is_active=True,
                    )
                    # ✅ SET THE FINAL PASSWORD
                    existing_user.set_password(final_password)
                    existing_user.save()

                member.user = existing_user

            member.save()

            # 3. Save the role to the User
            role = form.cleaned_data.get('role')
            if role and member.user:
                member.user.role = role
                member.user.company = company
                member.user.save(update_fields=['role', 'company'])

            messages.success(
                request,
                f'✅ Member "{member.full_name}" created (No. {member.member_number}). '
                f'Login Email: {member.user.email or member.user.username} | '
                f'Password: {final_password}'
            )
            return redirect('chama:member_list')
    else:
        form = MemberForm(
            company=company,
            initial={'joined_on': timezone.localdate()},
            fallback_password=fallback_password,   # 👈 pass dynamic default
        )

    return render(request, 'chama/member_form.html', {
        'form': form,
        'mode': 'create',
        'default_password': fallback_password,
    })

@login_required
@transaction.atomic
def member_edit(request, pk):
    company = _get_company(request)
    member = get_object_or_404(Member.objects.select_related('user'), pk=pk, company=company)

    # Fallback password (used only when creating a new linked user with no typed password)
    fallback_password = _generate_default_password(company)

    if request.method == 'POST':
        form = MemberForm(
            request.POST,
            request.FILES,
            instance=member,
            company=company,
            fallback_password=fallback_password,   # 👈 pass (form ignores it when user has usable password)
        )
        if form.is_valid():
            m = form.save(commit=False)

            # 1. Get the custom password (if provided)
            custom_password = form.cleaned_data.get('default_password', '').strip()

            # ── Cloudinary uploads ──
            if request.FILES.get('passport_photo'):
                m.passport_photo = _upload_to_cloudinary(request.FILES.get('passport_photo'))
            if request.FILES.get('id_front'):
                m.id_front = _upload_to_cloudinary(request.FILES.get('id_front'))
            if request.FILES.get('id_back'):
                m.id_back = _upload_to_cloudinary(request.FILES.get('id_back'))
            if request.FILES.get('kra_certificate'):
                m.kra_certificate = _upload_to_cloudinary(request.FILES.get('kra_certificate'))
            if request.FILES.get('good_conduct'):
                m.good_conduct = _upload_to_cloudinary(request.FILES.get('good_conduct'))

            # 2. Ensure the member has a linked User account
            if not m.user:
                existing_user = None
                if m.email:
                    existing_user = User.objects.filter(email__iexact=m.email).first()
                elif m.phone:
                    existing_user = User.objects.filter(username=m.phone).first()

                if not existing_user:
                    username_base = m.phone or m.email or f"member_{m.member_number.lower()}"
                    username = username_base
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{username_base}_{counter}"
                        counter += 1

                    existing_user = User.objects.create(
                        username=username,
                        email=m.email or '',
                        first_name=(m.full_name.split()[0] if m.full_name else ''),
                        last_name=(' '.join(m.full_name.split()[1:]) if m.full_name else ''),
                        company=company,
                        role='member',
                        is_active=True,
                    )

                    # ✅ If a custom password was provided, use it. Otherwise, unusable.
                    if custom_password:
                        existing_user.set_password(custom_password)
                    else:
                        existing_user.set_unusable_password()
                    existing_user.save()

                m.user = existing_user

            m.save()

            # 3. Update User Role & Password (if provided)
            if m.user:
                update_fields = []
                role = form.cleaned_data.get('role')

                if role and m.user.role != role:
                    m.user.role = role
                    update_fields.append('role')

                if m.user.company != company:
                    m.user.company = company
                    update_fields.append('company')

                # ✅ Override password if a new one was typed
                if custom_password:
                    m.user.set_password(custom_password)
                    update_fields.append('password')

                if update_fields:
                    m.user.save(update_fields=update_fields)

            messages.success(request, f'✅ Member "{m.full_name}" updated.')
            return redirect('chama:member_list')
    else:
        form = MemberForm(
            instance=member,
            company=company,
            fallback_password=fallback_password,   # 👈 pass (placeholder logic self-selects on edit)
        )

    return render(request, 'chama/member_form.html', {
        'form': form,
        'mode': 'edit',
        'member': member,
    })

@login_required
def role_list(request):
    return render(request, 'chama/role_list.html')

@login_required
def membership_type_list(request):
    qs = _company_queryset(request, MembershipType)
    return render(request, 'chama/membership_type_list.html', {'types': qs})

@login_required
def membership_type_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:membership_type_list')

    if request.method == 'POST':
        form = MembershipTypeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, f'✅ "{obj.name}" created successfully.')
            return redirect('chama:membership_type_list')
    else:
        form = MembershipTypeForm()

    return render(request, 'chama/membership_type_form.html', {
        'form': form,
        'mode': 'create',
    })

@login_required
def membership_type_edit(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(MembershipType, pk=pk, company=company)

    if request.method == 'POST':
        form = MembershipTypeForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ "{obj.name}" updated.')
            return redirect('chama:membership_type_list')
    else:
        form = MembershipTypeForm(instance=obj)

    return render(request, 'chama/membership_type_form.html', {
        'form': form,
        'mode': 'edit',
        'membership_type': obj,
    })

@login_required
def membership_type_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(MembershipType, pk=pk, company=company)
    name = obj.name
    obj.delete()
    messages.info(request, f'🗑️ "{name}" deleted.')
    return redirect('chama:membership_type_list')

@login_required
def registration_list(request):
    qs = _company_queryset(request, Registration).select_related('membership_type')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(full_name__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(email__icontains=q) |
            models.Q(national_id__icontains=q)
        )

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by('-created_at')
    pending_count = qs.filter(status='pending').count()

    return render(request, 'chama/registration_list.html', {
        'registrations': qs,
        'pending_count': pending_count,
    })

@login_required
@transaction.atomic
def registration_approve(request, pk):
    if request.method != 'POST':
        return redirect('chama:registration_list')

    company = _get_company(request)
    reg = get_object_or_404(Registration, pk=pk, company=company)

    if reg.status != 'pending':
        messages.warning(request, 'This application is no longer pending.')
        return redirect('chama:registration_list')

    reg.status = 'approved'
    reg.save(update_fields=['status'])

    # Generate default password
    default_password = _generate_default_password(company)

    # Link or create a User
    user = None
    if reg.email:
        user = User.objects.filter(email__iexact=reg.email).first()
    if not user and reg.phone:
        user = User.objects.filter(username=reg.phone).first()
    if not user:
        username_base = reg.phone or reg.email or f"member_{reg.id}"
        username = username_base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{username_base}_{counter}"
            counter += 1
        user = User.objects.create(
            username=username,
            email=reg.email or '',
            first_name=(reg.full_name.split()[0] if reg.full_name else ''),
            last_name=(' '.join(reg.full_name.split()[1:]) if reg.full_name else ''),
            company=company,
            role='member',
            is_active=True,
        )
        # ✅ SET COMPANY-BASED DEFAULT PASSWORD
        user.set_password(default_password)
        user.save()

    Member.objects.create(
        company=company,
        membership_type=reg.membership_type,
        member_number=_next_member_number(company),
        full_name=reg.full_name,
        phone=reg.phone,
        email=reg.email,
        national_id=reg.national_id,
        status='active',
        user=user,
    )

    messages.success(
        request,
        f'✅ {reg.full_name} approved. '
        f'Login Email: {user.email or user.username} | '
        f'Password: {default_password}'
    )
    return redirect('chama:registration_list')

@login_required
def registration_reject(request, pk):
    if request.method != 'POST':
        return redirect('chama:registration_list')

    reg = get_object_or_404(Registration, pk=pk, company=_get_company(request))

    if reg.status != 'pending':
        messages.warning(request, 'This application is no longer pending.')
        return redirect('chama:registration_list')

    reg.status = 'rejected'
    reg.save(update_fields=['status'])

    messages.info(request, f'{reg.full_name}\'s application was rejected.')
    return redirect('chama:registration_list')

@login_required
def committee_list(request):
    company = _get_company(request)
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

    return render(request, 'chama/committee_member_form.html', {'form': form, 'committee': committee})

@login_required
def committee_member_remove(request, pk, member_pk):
    committee = get_object_or_404(Committee, pk=pk)
    member = get_object_or_404(CommitteeMember, pk=member_pk, committee=committee)
    name = member.member.full_name
    member.delete()
    messages.info(request, f'🗑️ {name} removed from {committee.name}.')
    return redirect('chama:committee_detail', pk=committee.pk)

    


# ============================================================
# PROJECTS, MEETINGS,  ANOUNCEMENT,  ATTENDANCE
# ============================================================
@login_required
def project_list(request):
    company = _get_company(request)
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
    company = _get_company(request)
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
    
    # Get attendance records for this meeting
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
    company = _get_company(request)
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
# CONTRIBUTIONS   FINES  AND SAVINGS
# ============================================================
import datetime
from calendar import month_name


@login_required
def contribution_list(request):
    company = _get_company(request)
    
    if not company:
        return redirect('home')

    # 1. Define authorized roles
    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    ]

    # 2. Get the selected month (default to current month)
    today = timezone.localdate()
    current_month = today.strftime('%Y-%m')
    selected_month = request.GET.get('month', current_month)

    # 3. Generate Month Choices Dynamically (Last 12 months + Next 3 months)
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

    # 4. Handle ONE-CLICK "Mark as Paid" (Treasurer/Officer action only)
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

    # 5. Fetch data based on role
    if is_officer:
        # --- OFFICER VIEW ---
        # See all active members to manage them
        members = Member.objects.filter(company=company, status='active').order_by('full_name')
        
        contributions_qs = Contribution.objects.filter(
            company=company, period=selected_month
        )
        
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
        # --- MEMBER VIEW ---
        # See only their own contribution history
        current_member = _get_current_member(request, company)
        if current_member:
            contributions_qs = Contribution.objects.filter(
                member=current_member
            ).order_by('-date', '-created_at')
        else:
            contributions_qs = Contribution.objects.none()
            
        context = {
            'is_officer': False,
            'contributions': contributions_qs, # The template will loop through this
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
            
            # 👇 NEW: Automatically assign the membership type from the member
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
    
    # Store the original paid status
    was_paid = obj.paid

    if request.method == 'POST':
        form = ContributionForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            contribution = form.save()
            
            # If it was unpaid and is now paid, post to pool
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
    
    # If this contribution had been posted to Pool, reverse it
    posted_txn = Transaction.objects.filter(
        company=company,
        reference=f"CONT-{obj.pk}"
    ).first()
    
    if posted_txn:
        # Create a reversal transaction (Money Out) so the pool balance corrects
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

    # 1. Calculate required amount for current month
    current_month = timezone.localdate().strftime('%Y-%m')
    required_amount = (
        current_member.membership_type.monthly_contribution 
        if current_member.membership_type else 0
    )
    
    # 2. Calculate already paid and remaining
    contributed_this_month = Contribution.objects.filter(
        member=current_member,
        period=current_month,
        paid=True
    ).aggregate(t=Sum('amount'))['t'] or 0
    
    remaining_amount = max(0, required_amount - contributed_this_month)

    # 3. Handle POST Request (Trigger M-Pesa STK Push)
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        
        if not phone:
            messages.error(request, "Phone number is required.")
        elif remaining_amount <= 0:
            messages.info(request, "You have already paid for this month.")
            return redirect('chama:contribution_list')
        else:
            try:
                # Trigger the STK Push using your helper function
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
                    
                    # NOTE: The actual marking as "Paid" happens when Safaricom 
                    # confirms the transaction via the M-Pesa Callback URL.
                    # If you are testing without callbacks, you can uncomment the lines below:
                    
                    # contribution, created = Contribution.objects.get_or_create(
                    #     company=company, member=current_member, period=current_month,
                    #     defaults={'amount': remaining_amount, 'paid': True, 'date': timezone.localdate(), 'membership_type': current_member.membership_type}
                    # )
                    # if not created:
                    #     contribution.paid = True
                    #     contribution.save()
                    # _post_contribution_to_pool(contribution)
                    
                    return redirect('chama:contribution_list')
                else:
                    messages.error(
                        request,
                        response.get('ResponseDescription') or 'STK Push failed. Please try again.'
                    )
            except Exception as e:
                messages.error(request, f"Payment error: {e}")

    # 4. Render the Template
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

    # 1. Calculate required amount for current month
    current_month = timezone.localdate().strftime('%Y-%m')
    required_amount = (
        current_member.membership_type.monthly_contribution 
        if current_member.membership_type else 0
    )
    
    # 2. Calculate already paid and remaining
    contributed_this_month = Contribution.objects.filter(
        member=current_member,
        period=current_month,
        paid=True
    ).aggregate(t=Sum('amount'))['t'] or 0
    
    remaining_amount = max(0, required_amount - contributed_this_month)

    # 3. Handle POST Request (Trigger M-Pesa STK Push)
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        
        if not phone:
            messages.error(request, "Phone number is required.")
        elif remaining_amount <= 0:
            messages.info(request, "You have already paid for this month.")
            return redirect('chama:contribution_list')
        else:
            try:
                # Trigger the STK Push using your helper function
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

    # 4. Render the Template
    context = {
        'member': current_member,
        'current_month': current_month,
        'required_amount': required_amount,
        'contributed_this_month': contributed_this_month,
        'remaining_amount': remaining_amount,
    }
    return render(request, 'chama/contribution_pay.html', context)

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

            # Post to cashbook (General/Pool Account)
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
    
    # Reverse from cashbook if it exists
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

@login_required
def fine_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Fine).select_related('member')

    # ── Role-based filtering ──
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

    # Search & filter
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
    """
    Pay a pending fine via M-Pesa STK Push.
    """
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

            # If the fine was created as paid, post to cashbook
            if obj.is_paid:
                posted = _post_to_cashbook(
                    company=company,
                    account_purpose='welfare',  # Or 'pool' depending on your policy
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
            
            # If it was unpaid and is now paid, post to cashbook
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

    return render(request, 'chama:fine_form.html', {
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
    
    # Reverse from cashbook if it was paid
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
# LOAN TYPES  LOANS
# ============================================================

def check_internal_loan_eligibility(member):
    """
    Returns (is_eligible: bool, reason: str)
    Checks if a member can apply for an internal loan.
    """
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

@login_required
def loan_type_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, LoanType).order_by('name')
    return render(request, 'chama/loan_type_list.html', {
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

    return render(request, 'chama/loan_type_form.html', {'form': form, 'mode': 'create'})

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

    return render(request, 'chama/loan_type_form.html', {'form': form, 'mode': 'edit', 'loan_type': obj})

@login_required
@_require_loan_policy_setter
def loan_type_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(LoanType, pk=pk, company=company)
    name = obj.name
    obj.delete()
    messages.info(request, f'🗑️ Loan Type "{name}" deleted.')
    return redirect('chama:loan_type_list')

@login_required
@_require_officer
def guest_create(request):
    """Officer registers a guest for an external loan."""
    company = _get_company(request)
    if request.method == 'POST':
        form = GuestForm(request.POST, request.FILES)
        if form.is_valid():
            guest = form.save(commit=False)
            guest.company = company
            guest.created_by = request.user
            guest.save()
            messages.success(request, f'✅ Guest "{guest.full_name}" registered successfully.')
            return redirect('chama:loan_create_external', guest_pk=guest.pk)
    else:
        form = GuestForm()
    return render(request, 'chama/guest_form.html', {'form': form})

@login_required
@_require_officer
def loan_create_external(request, guest_pk):
    """Create an external loan for a registered guest."""
    company = _get_company(request)
    guest = get_object_or_404(Guest, pk=guest_pk, company=company)

    if request.method == 'POST':
        # Custom form for external loans
        loan_type_id = request.POST.get('loan_type')
        principal = request.POST.get('principal')
        term = request.POST.get('term_months')
        purpose = request.POST.get('purpose', '')

        try:
            lt = LoanType.objects.get(pk=loan_type_id, company=company)
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
            messages.success(request, f'✅ External loan application created for {guest.full_name}.')
            return redirect('chama:loan_list')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    loan_types = LoanType.objects.filter(company=company, is_active=True)
    return render(request, 'chama/loan_external_form.html', {
        'guest': guest,
        'loan_types': loan_types,
    })

@login_required
def loan_list(request):
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
            
            # Check if they are locked out of the 3x rule
            if current_member.custom_loan_limit == 0 and not current_member.has_good_repayment_history:
                needs_committee_review = True
        else:
            qs = qs.none()

    # --- Apply Officer Filters ---
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

    # --- Strict Funnel Stats (Fixes the NameError) ---
    total_pending = qs.filter(status='pending').aggregate(t=Sum('principal'))['t'] or 0
    total_approved = qs.filter(status='approved').aggregate(t=Sum('principal'))['t'] or 0
    total_disbursed = qs.filter(status='disbursed').aggregate(t=Sum('principal'))['t'] or 0
    total_repaid = (
        qs.filter(status__in=['disbursed', 'closed'])
        .aggregate(t=Sum('repayments__amount'))['t'] or 0
    )

    return render(request, 'chama/loan_list.html', {
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

from decimal import Decimal
from django.db.models import Sum
from apps.customers.models import Customer # Ensure this is imported

@login_required
def loan_detail(request, pk):
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
    
    # Permission check
    if not is_officer and (not current_member or loan.member != current_member):
        messages.error(request, 'You do not have permission to view this loan.')
        return redirect('chama:loan_list')

    repayments = loan.repayments.order_by('-date', '-created_at')

    # Calculate limits based on loan type (Internal vs External)
    true_available_power = Decimal('0.00')
    display_limit = Decimal('0.00')
    display_taken = Decimal('0.00')
    display_active_debt = Decimal('0.00')

    if loan.member:
        # --- INTERNAL LOAN LOGIC ---
        display_limit = loan.member.eligible_loan_limit or Decimal('0.00')
        display_taken = loan.member.total_principal_taken or Decimal('0.00')
        display_active_debt = loan.member.active_loans_total or Decimal('0.00')
        
        # Get other active loans for power calc
        other_active_loans_sum = loan.member.loans.filter(
            status__in=['approved', 'disbursed']
        ).exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
        
        true_available_power = display_limit - other_active_loans_sum

    elif loan.guest:
        # --- EXTERNAL LOAN LOGIC ---
        identifier = loan.guest.national_id or loan.guest.phone
        customer = Customer.objects.filter(
            company=company,
            national_id=identifier
        ).first()

        if customer:
            display_limit = customer.custom_loan_limit or Decimal('0.00')
            
            # Sum all active external loans for this customer (excluding this one)
            customer_loans = Loan.objects.filter(
                company=company,
                loan_category='external',
                status__in=['approved', 'disbursed'],
                guest__national_id=identifier
            )
            
            display_taken = customer_loans.aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
            
            # Calculate active debt (Principal + Interest)
            display_active_debt = sum(l.total_repayable for l in customer_loans)
            
            # Calculate power
            other_loans = customer_loans.exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or Decimal('0.00')
            true_available_power = display_limit - other_loans

    return render(request, 'chama/loan_detail.html', {
        'loan': loan,
        'repayments': repayments,
        'is_officer': is_officer,
        'current_member': current_member,
        'true_available_power': true_available_power,
        # Pass these new variables to the template
        'display_limit': display_limit,
        'display_taken': display_taken,
        'display_active_debt': display_active_debt,
    })



@login_required
def loan_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:loan_list')

    is_officer = request.user.role in ADMIN_ROLES
    current_member = _get_current_member(request, company)

    # ============================================================
    # MEMBER SELF-SERVICE FLOW (from Modal)
    # ============================================================
    if not is_officer:
        if not current_member:
            messages.error(request, 'You are not linked to a Chama member record.')
            return redirect('chama:loan_list')

        # Eligibility Check
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

        # Fetch loan history for the member
        my_loans = Loan.objects.filter(
            company=company, member=current_member
        ).prefetch_related('repayments').order_by('-requested_on')

        return render(request, 'chama/loan_form.html', {
            'form': form,
            'mode': 'request',
            'current_member': current_member,
            'eligible_limit': current_member.available_borrowing_power,
            'total_contributions': current_member.total_contributions_paid,
            'active_loans': current_member.active_loans_total,
            'my_loans': my_loans,
        })

    # ============================================================
    # OFFICER MANUAL ENTRY FLOW (unchanged)
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

    return render(request, 'chama/loan_form.html', {
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

    return render(request, 'chama/loan_form.html', {'form': form, 'mode': 'edit', 'loan': obj, 'is_officer': True})

@login_required
def loan_delete(request, pk):
    company = _get_company(request)
    obj = get_object_or_404(Loan, pk=pk, company=company)
    obj.delete()
    messages.info(request, '🗑️ Loan deleted.')
    return redirect('chama:loan_list')

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

    # ── SAFETY CHECK: Handle Internal vs External loans ──
    member = loan.member
    guest = loan.guest

    if member:
        # 👇 INTERNAL LOAN: Check 3x contributions limit
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
            
    elif guest:
        # 👇 EXTERNAL LOAN: Check Customer's custom limit
        from apps.customers.models import Customer
        
        # Find the customer linked to this guest (by phone or national ID)
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
            # If no customer profile found, you can choose to block or allow
            messages.warning(request, "Could not find a customer profile to verify limit. Proceeding with approval.")
    
    else:
        messages.error(request, 'This loan has neither a member nor a guest attached to it.')
        return redirect('chama:loan_list')

    # ── Also verify against the loan type's max_amount ──
    if loan.loan_type and loan.loan_type.max_amount and loan.principal > loan.loan_type.max_amount:
        messages.error(
            request,
            f'Cannot approve: this amount exceeds the maximum for '
            f'{loan.loan_type.name} (KES {loan.loan_type.max_amount:,.2f}).'
        )
        return redirect('chama:loan_list')

    # ── All checks pass — approve ──
    loan.status = 'approved'
    loan.approved_on = timezone.localdate()
    loan.approved_by = request.user 
    loan.save(update_fields=['status', 'approved_on', 'approved_by'])

    # Get name for success message
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
    loan.save(update_fields=['status'])
    loan.rejected_by = request.user 
    loan.save(update_fields=['status', 'rejected_by']) # 👈 Added 'rejected_by'
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

    # ── Re-check borrowing power at disbursement time ──
    member = loan.member
    if member:
        # Calculate her limit
        current_limit = member.eligible_loan_limit
        
        # Calculate her total active loans, EXCLUDING this loan we are trying to disburse
        other_loans = member.loans.filter(
            status__in=['approved', 'disbursed']
        ).exclude(pk=loan.pk).aggregate(t=Sum('principal'))['t'] or 0
        
        # Her real available limit BEFORE this loan
        actual_available = current_limit - other_loans

        if loan.principal > actual_available:
            messages.error(
                request,
                f'Cannot disburse: {member.full_name} can only borrow up to '
                f'KES {actual_available:,.2f} at this time.'
            )
            return redirect('chama:loan_list')

    # ── Mark loan disbursed ──
    loan.status = 'disbursed'
    loan.disbursed_on = timezone.localdate()
    loan.disbursed_by = request.user
    loan.save(update_fields=['status', 'disbursed_on', 'disbursed_by'])

    # ── POST TO CASHBOOK (Loan Fund = money OUT) ──
    loan_account = Account.objects.filter(
        company=company, purpose='loans', is_active=True
    ).first()

    if loan_account:
        borrower = (
            loan.member.full_name if loan.member
            else (loan.guest.full_name if loan.guest else 'Guest')
        )

        # Optional safety: warn if the Loan Fund is short
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



@login_required
def loan_repayment_pay(request, loan_pk):
    """
    Member self-service: pay a loan via M-Pesa STK Push.
    """
    company = _get_company(request)
    loan = get_object_or_404(Loan, pk=loan_pk, company=company)

    # Permission check
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
                    response = _send_chama_stk_push(
                        company=company,
                        phone=phone,
                        amount=int(amount_dec),
                        account_reference=f"L-{loan.member.member_number}",
                        description=f"Loan Repay",
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

    return render(request, 'chama/loan_repayment_pay.html', {
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

    # 👇 NEW: Calculate totals
    total_repaid = qs.aggregate(t=Sum('amount'))['t'] or 0
    
    # Calculate total principal of all loans (that have repayments, or all loans for this user)
    loan_qs = Loan.objects.filter(company=company)
    if not is_officer and current_member:
        loan_qs = loan_qs.filter(member=current_member)
    
    total_borrowed = loan_qs.aggregate(t=Sum('principal'))['t'] or 0

    return render(request, 'chama/loan_repayment_list.html', {
        'repayments': qs,
        'total_count': qs.count(),
        'total_repaid': total_repaid,     # 👈 Pass the total
        'total_borrowed': total_borrowed, # 👈 Pass the new total
        'is_officer': is_officer,
        'current_member': current_member,
    })
 
@login_required
@transaction.atomic
def loan_repayment_create(request, loan_pk):
    company = _get_company(request)
    loan = get_object_or_404(Loan, pk=loan_pk, company=company)

    # 👇 STRICT ROLE CHECK: Only Treasurer, Company Admin, or Super Admin
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

            # ── POST TO CASHBOOK (Loan Fund = money IN) ──
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
                    auto_generated=True,   # 👈 hides from unified cashbook list
                )
            else:
                messages.warning(
                    request,
                    'Repayment saved, but no Loan Fund account exists. '
                    'Please create an account with purpose="loans" to track cash flow.'
                )

            # Auto-close loan if fully repaid
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

    return render(request, 'chama/loan_repayment_form.html', {
        'form': form,
        'loan': loan,
    })

@login_required
def internal_loan_limits(request):
    """
    Officer-only page listing all active members with:
      - Total contributions paid (lifetime)
      - Contribution status for current month
      - Current eligible loan limit
      - Action buttons: Review History / Adjust Limit
    """
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

    # Preload contribution totals & current-month status in bulk (avoids N+1)
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

    # Preload active loan outstanding per member
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

    return render(request, 'chama/internal_loan_limits.html', {
        'rows': rows,
        'current_month': current_month,
        'total_expected': total_expected,
        'total_collected': total_collected,
        'is_officer': True,
    })

@login_required
def member_loan_history(request, member_pk):
    """
    AJAX endpoint — returns JSON with a member's contribution history,
    loan history, and repayment history for the Review History modal.
    """
    company = _get_company(request)
    if not company:
        return JsonResponse({'error': 'No company assigned.'}, status=400)

    if request.user.role not in ADMIN_ROLES:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    member = get_object_or_404(Member, pk=member_pk, company=company)

    # Contributions (last 12, paid only for the "paid" timeline)
    contributions = Contribution.objects.filter(
        member=member
    ).order_by('-date', '-created_at')[:12]
    contrib_data = [
        {
            'period': c.period or '—',
            'amount': float(c.amount),
            'paid': c.paid,
            'paid_on_time': c.paid_on_time,
            'date': c.date.strftime('%Y-%m-%d') if c.date else None,
        }
        for c in contributions
    ]

    # Loans
    loans = Loan.objects.filter(member=member).order_by('-requested_on')[:10]
    loan_data = []
    for l in loans:
        loan_data.append({
            'id': l.pk,
            'type': l.loan_type.get_name_display() if l.loan_type else '—',
            'principal': float(l.principal),
            'status': l.get_status_display(),
            'status_code': l.status,
            'requested_on': l.requested_on.strftime('%Y-%m-%d') if l.requested_on else None,
            'disbursed_on': l.disbursed_on.strftime('%Y-%m-%d') if l.disbursed_on else None,
            'total_repaid': float(l.total_repaid),
            'balance_remaining': float(l.balance_remaining),
            'total_repayable': float(l.total_repayable),
            'progress_pct': round(l.repayment_progress_pct, 1),
        })

    return JsonResponse({
        'member': {
            'id': member.pk,
            'full_name': member.full_name,
            'member_number': member.member_number,
            'membership_type': member.membership_type.get_name_display() if member.membership_type else '—',
            'joined_on': member.joined_on.strftime('%Y-%m-%d') if member.joined_on else None,
            'total_contributions_paid': float(member.total_contributions_paid),
            'has_good_repayment_history': member.has_good_repayment_history,
            'custom_loan_limit': float(member.custom_loan_limit),
            'eligible_loan_limit': float(member.eligible_loan_limit),
            'active_loans_total': float(member.active_loans_total),
            'available_borrowing_power': float(member.available_borrowing_power),
        },
        'contributions': contrib_data,
        'loans': loan_data,
    })

@login_required
def member_loan_limit_adjust(request, member_pk):
    """
    AJAX POST endpoint — updates a member's custom_loan_limit.
    Expects JSON: {"custom_limit": "50000.00"}
    Returns JSON with new computed values.
    """
    company = _get_company(request)
    if not company:
        return JsonResponse({'error': 'No company assigned.'}, status=400)

    if request.user.role not in ADMIN_ROLES:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    member = get_object_or_404(Member, pk=member_pk, company=company)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    raw = payload.get('custom_limit', '')
    try:
        new_limit = Decimal(str(raw).strip() or '0')
    except (InvalidOperation, ValueError):
        return JsonResponse({'error': 'Invalid amount.'}, status=400)

    if new_limit < 0:
        return JsonResponse({'error': 'Limit cannot be negative.'}, status=400)

    member.custom_loan_limit = new_limit
    member.save(update_fields=['custom_loan_limit', 'updated_at'])

    return JsonResponse({
        'ok': True,
        'custom_loan_limit': float(member.custom_loan_limit),
        'eligible_loan_limit': float(member.eligible_loan_limit),
        'available_borrowing_power': float(member.available_borrowing_power),
        'message': f'Loan limit updated to KES {member.custom_loan_limit:,.2f}',
    })





# ============================================================
# ACCOUNTS, TRANSACTIONS, EXPENCES AND REOPORTS
# ============================================================
@login_required
def account_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Account).order_by('name')
    
    # Calculate totals for the summary cards
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

        # --- VALIDATION ---
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

        # Check if the source account has enough funds
        if from_account.current_balance < amount:
            messages.error(
                request, 
                f"Insufficient funds in {from_account.name}. "
                f"Available: KES {from_account.current_balance:,.2f}, "
                f"Requested: KES {amount:,.2f}"
            )
            return render(request, 'chama/account_transfer.html', {'accounts': accounts})

        # --- PROCESS TRANSFER ---
        # 1. Money Out from source
        Transaction.objects.create(
            company=company,
            account=from_account,
            transaction_type='out',
            amount=amount,
            description=f"Transfer to {to_account.name} — {description}",
            date=timezone.localdate()
        )

        # 2. Money In to destination
        Transaction.objects.create(
            company=company,
            account=to_account,
            transaction_type='in',
            amount=amount,
            description=f"Transfer from {from_account.name} — {description}",
            date=timezone.localdate()
        )

        messages.success(
            request, 
            f"✅ Successfully transferred KES {amount:,.2f} from {from_account.name} to {to_account.name}."
        )
        return redirect('chama:account_list')

    return render(request, 'chama/account_transfer.html', {'accounts': accounts})

@login_required
def account_transfer_confirm(request):
    company = _get_company(request)
    if not company:
        return redirect('home')

    pending = request.session.get('pending_transfer')
    if not pending:
        messages.error(request, "No pending transfer found. Please start again.")
        return redirect('chama:account_transfer')

    from_account = get_object_or_404(Account, pk=pending['from_id'], company=company)
    to_account = get_object_or_404(Account, pk=pending['to_id'], company=company)
    amount = Decimal(pending['amount'])
    description = pending['description']

    if request.method == 'POST':
        # Re-check the balance (in case another user withdrew money in the meantime)
        if from_account.current_balance < amount:
            messages.error(request, "Insufficient funds. Transfer cancelled.")
            del request.session['pending_transfer']
            return redirect('chama:account_transfer')

        # 1. Money Out from source
        Transaction.objects.create(
            company=company,
            account=from_account,
            transaction_type='out',
            amount=amount,
            description=f"Transfer to {to_account.name} — {description}",
            date=timezone.localdate()
        )

        # 2. Money In to destination
        Transaction.objects.create(
            company=company,
            account=to_account,
            transaction_type='in',
            amount=amount,
            description=f"Transfer from {from_account.name} — {description}",
            date=timezone.localdate()
        )

        # Clear session
        del request.session['pending_transfer']

        messages.success(
            request, 
            f"✅ Successfully transferred KES {amount:,.2f} from {from_account.name} to {to_account.name}."
        )
        return redirect('chama:account_list')

    # If GET, show the confirmation page
    context = {
        'from_account': from_account,
        'to_account': to_account,
        'amount': amount,
        'description': description,
    }
    return render(request, 'chama/account_transfer_confirm.html', context)

@login_required
def transaction_list(request):
    company = _get_company(request)

    source_filter = request.GET.get('source', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    
    # 👇 NEW: Get the account ID from the URL parameter
    account_filter_id = request.GET.get('account', '').strip()
    
    # Get the account name for the UI title if filtering
    selected_account = None
    if account_filter_id:
        selected_account = Account.objects.filter(pk=account_filter_id, company=company).first()

    txs = []

    # 1. Cashbook (ONLY manual entries — exclude auto-generated mirrors)
    cashbook_txs = Transaction.objects.filter(
        company=company, 
        auto_generated=False
    ).select_related('account', 'project')
    
    # 👇 NEW: Filter cashbook transactions by account
    if account_filter_id:
        cashbook_txs = cashbook_txs.filter(account_id=account_filter_id)
        
    for t in cashbook_txs:
        txs.append({
            'date': t.date,
            'description': t.description,
            'amount': t.amount,
            'transaction_type': t.transaction_type,
            'account_name': t.account.name if t.account else 'N/A',
            'reference': t.reference,
            'source': 'cashbook',
        })

    # --- SAVINGS ---
    # (Savings, Contributions, Fines usually go to the Pool account in your logic)
    if not account_filter_id or (selected_account and selected_account.purpose == 'pool'):
        savings = Savings.objects.filter(company=company).select_related('member')
        for s in savings:
            txs.append({
                'date': s.date,
                'description': f'Savings deposit — {s.member.full_name}',
                'amount': s.amount,
                'transaction_type': 'in',
                'account_name': 'Savings',
                'reference': s.reference or f'SAV-{s.pk}',
                'source': 'saving',
            })

        # --- CONTRIBUTIONS ---
        contributions = Contribution.objects.filter(company=company, paid=True).select_related('member')
        for c in contributions:
            txs.append({
                'date': c.date,
                'description': f'Contribution {c.period} — {c.member.full_name}',
                'amount': c.amount,
                'transaction_type': 'in',
                'account_name': 'Contributions',
                'reference': f'CONT-{c.pk}',
                'source': 'contribution',
            })

        # --- FINES ---
        fines = Fine.objects.filter(company=company, is_paid=True).select_related('member')
        for f in fines:
            txs.append({
                'date': f.date,
                'description': f'Fine — {f.member.full_name}: {f.reason}',
                'amount': f.amount,
                'transaction_type': 'in',
                'account_name': 'Fines',
                'reference': f'FINE-{f.pk}',
                'source': 'fine',
            })

    # --- LOANS ---
    # (Loans and Repayments usually go to the Loan Fund account)
    if not account_filter_id or (selected_account and selected_account.purpose == 'loans'):
        # 5. Loan Disbursements
        disbursed = Loan.objects.filter(
            company=company, status__in=['disbursed', 'closed']
        ).select_related('member', 'guest')
        for loan in disbursed:
            borrower = loan.member.full_name if loan.member else (loan.guest.full_name if loan.guest else 'Guest')
            txs.append({
                'date': loan.disbursed_on or loan.requested_on,
                'description': f'Loan disbursed #{loan.pk} — {borrower}',
                'amount': loan.principal,
                'transaction_type': 'out',
                'account_name': 'Loan Fund',
                'reference': f'LOAN-{loan.pk}',
                'source': 'loan',
            })

        # 6. Loan Repayments
        repayments = LoanRepayment.objects.filter(company=company).select_related('loan__member', 'loan__guest')
        for r in repayments:
            loan = r.loan
            borrower = loan.member.full_name if loan.member else (loan.guest.full_name if loan.guest else 'Guest')
            txs.append({
                'date': r.date,
                'description': f'Loan repayment #{loan.pk} — {borrower}',
                'amount': r.amount,
                'transaction_type': 'in',
                'account_name': 'Loan Fund',
                'reference': r.reference or f'REPAY-{r.pk}',
                'source': 'loan_repayment',
            })

    # --- EXPENSES ---
    expenses = Expense.objects.filter(company=company).select_related('account')
    
    # 👇 NEW: Filter expenses by account
    if account_filter_id:
        expenses = expenses.filter(account_id=account_filter_id)

    for e in expenses:
        txs.append({
            'date': e.date,
            'description': f'Expense — {e.title}',
            'amount': e.amount,
            'transaction_type': 'out',
            'account_name': e.account.name if e.account else 'Expenses',
            'reference': f'EXP-{e.pk}',
            'source': 'expense',
        })

    # --- Filtering ---
    if source_filter:
        txs = [t for t in txs if t['source'] == source_filter]

    if date_from:
        txs = [t for t in txs if str(t['date']) >= date_from]
    if date_to:
        txs = [t for t in txs if str(t['date']) <= date_to]

    # --- Sort ---
    txs.sort(key=lambda x: str(x['date']), reverse=True)

    # --- Totals ---
    total_in = sum(t['amount'] for t in txs if t['transaction_type'] == 'in')
    total_out = sum(t['amount'] for t in txs if t['transaction_type'] == 'out')

    # --- Source Summary ---
    source_summary = {}
    for t in txs:
        s = t['source']
        if s not in source_summary:
            source_summary[s] = {'in': 0, 'out': 0, 'count': 0}
        source_summary[s][t['transaction_type']] += float(t['amount'])
        source_summary[s]['count'] += 1

    return render(request, 'chama/transaction_list.html', {
        'transactions': txs,
        'total_in': total_in,
        'total_out': total_out,
        'net_balance': total_in - total_out,
        'source_summary': source_summary,
        'source_filter': source_filter,
        'date_from': date_from,
        'date_to': date_to,
        # 👇 Pass the account info to the template so we can show a filter badge
        'selected_account': selected_account,
        'is_officer': request.user.role in [
            'super_admin', 'company_admin', 'chairperson', 'treasurer',
        ],
    })

@login_required
def transaction_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        form = TransactionForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, '✅ Transaction recorded.')
            return redirect('chama:transaction_list')
    else:
        form = TransactionForm(company=company, initial={'date': timezone.localdate()})
    return render(request, 'chama/transaction_form.html', {'form': form, 'mode': 'create'})

@login_required
def expense_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Expense).select_related('account').order_by('-date')
    total_expenses = qs.aggregate(t=Sum('amount'))['t'] or 0
    
    return render(request, 'chama/expense_list.html', {
        'expenses': qs,
        'total_expenses': total_expenses,
        'is_officer': request.user.role in ['super_admin', 'company_admin', 'chairperson', 'treasurer'],
    })

@login_required
@transaction.atomic
def expense_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()

            # Post to cashbook (Money OUT from the chosen account)
            if obj.account:
                Transaction.objects.create(
                    company=company,
                    account=obj.account,
                    transaction_type='out',
                    amount=obj.amount,
                    date=obj.date,
                    description=f'Expense — {obj.title}',
                    reference=f'EXP-{obj.pk}',
                    auto_generated=True,
                )
                messages.success(request, '✅ Expense recorded and posted to Cashbook.')
            else:
                messages.warning(request, 'Expense recorded, but no account was selected. Balance not updated.')
                
            return redirect('chama:expense_list')
    else:
        form = ExpenseForm(company=company, initial={'date': timezone.localdate()})
    return render(request, 'chama/expense_form.html', {'form': form, 'mode': 'create'})

@login_required
def reports(request):
    company = _get_company(request)
    ctx = {'company': company}
    
    if company:
        # ── 1. Total Savings ──
        savings_agg = Savings.objects.filter(company=company).aggregate(t=Sum('amount'))
        ctx['total_savings'] = savings_agg['t'] if savings_agg['t'] is not None else 0
        
        # ── 2. Total Contributions ──
        contrib_agg = Contribution.objects.filter(company=company, paid=True).aggregate(t=Sum('amount'))
        ctx['total_contributions'] = contrib_agg['t'] if contrib_agg['t'] is not None else 0
        
        # ── 3. Loans Disbursed ──
        disbursed_agg = Loan.objects.filter(company=company, status__in=['disbursed', 'closed']).aggregate(t=Sum('principal'))
        ctx['total_loans_disbursed'] = disbursed_agg['t'] if disbursed_agg['t'] is not None else 0
        
        # ── 4. Loans Outstanding ──
        active_loans = Loan.objects.filter(company=company, status__in=['approved', 'disbursed'])
        outstanding = 0
        for loan in active_loans:
            outstanding += loan.balance_remaining
        ctx['total_loans_outstanding'] = outstanding

        # ── 5. Fines Summary ──
        paid_fines = Fine.objects.filter(company=company, is_paid=True).aggregate(t=Sum('amount'))
        unpaid_fines = Fine.objects.filter(company=company, is_paid=False).aggregate(t=Sum('amount'))
        
        ctx['fines_summary'] = {
            'paid': paid_fines['t'] if paid_fines['t'] is not None else 0,
            'unpaid': unpaid_fines['t'] if unpaid_fines['t'] is not None else 0,
        }

        # ── 6. Top Savers ──
        ctx['savings_by_member'] = (
            Savings.objects.filter(company=company)
            .values('member__full_name')
            .annotate(total=Sum('amount'))
            .order_by('-total')[:10]
        )
        
        # ── 7. Top Borrowers ──
        ctx['top_borrowers'] = (
            Loan.objects.filter(company=company, status__in=['disbursed', 'closed'])
            .values('member__full_name')
            .annotate(total_borrowed=Sum('principal'))
            .order_by('-total_borrowed')[:5]
        )
        
        # ── 8. Loans by Status ──
        ctx['loans_by_status'] = (
            Loan.objects.filter(company=company)
            .values('status')
            .annotate(count=Count('id'), total=Sum('principal'))
            .order_by('-total')
        )

    return render(request, 'chama/reports.html', ctx)