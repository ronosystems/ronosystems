# ============================================================
# MEMBERS VIEWS
# Membership Types, Registration, Member Loan History/Limits
# ============================================================
import time
import cloudinary
import cloudinary.uploader

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.companies.models import Company

from .forms import MembershipTypeForm, MemberForm
from .models import (
    Member, MembershipType, Registration,
    Contribution, Loan,
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
# SHARED HELPERS
# ============================================================

def _generate_default_password(company):
    """Generate a default password from the company name."""
    if not company or not company.name:
        return 'Chama@12345'
    first_word = company.name.strip().split()[0].capitalize()
    return f"{first_word}@12345"


def _cloudinary_configure():
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def _upload_to_cloudinary(uploaded_file, folder='chama/members'):
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
        return result.get('public_id') or base
    except Exception as e:
        import traceback
        print(f"❌ Cloudinary upload FAILED: {e}")
        traceback.print_exc()
        return None


def _get_company(request):
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
    if not company or not request.user.is_authenticated:
        return None
    return Member.objects.filter(company=company, user=request.user).first()


def _get_reset_link(request, company, uid, token):
    custom = getattr(company, 'custom_domain', None)
    verified = getattr(company, 'domain_verified', False)
    if custom and verified:
        host = custom.strip().replace('http://', '').replace('https://', '').strip('/')
    else:
        host = request.get_host()
        if host.endswith('.onrender.com') and host.count('.') > 2:
            host = getattr(settings, 'SYSTEM_DOMAIN', 'ronosystems.onrender.com')
            host = host.replace('http://', '').replace('https://', '').strip('/')

    protocol = 'http' if ('localhost' in host or '127.0.0.1' in host) else 'https'
    reset_path = reverse(
        'accounts:password_reset_confirm',
        kwargs={'uidb64': uid, 'token': token},
    )
    return f"{protocol}://{host}{reset_path}"


def _send_invite_email(request, company, membership, user, first_name, email, is_new_user=True):
    try:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = _get_reset_link(request, company, uid, token)

        context = {
            'first_name': first_name,
            'company_name': company.name,
            'role': membership.get_role_display(),
            'username': membership.company_username,
            'email': email,
            'reset_link': reset_link,
            'is_new_user': is_new_user,
        }
        html_message = render_to_string('emails/staff_invite.html', context)
        plain_message = strip_tags(html_message)

        send_mail(
            f"You have been added to {company.name}",
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            html_message=html_message,
            fail_silently=False,
        )
        return True, None
    except Exception as e:
        return False, str(e)


# ============================================================
# MEMBERSHIP TYPES
# ============================================================

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


# ============================================================
# MEMBER LIST / DETAIL
# ============================================================

@login_required
def member_list(request):
    company = _get_company(request)
    qs = _company_queryset(request, Member).select_related('membership_type', 'user')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            models.Q(full_name__icontains=q) |
            models.Q(member_number__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(email__icontains=q) |
            models.Q(national_id__icontains=q)
        )

    # Status filter
    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    # Membership type filter
    membership_type_id = request.GET.get('membership_type', '').strip()
    if membership_type_id:
        qs = qs.filter(membership_type_id=membership_type_id)

    qs = qs.order_by('full_name')

    is_officer = request.user.role in ADMIN_ROLES

    return render(request, 'chama/member_list.html', {
        'members': qs,
        'total_count': qs.count(),
        'active_count': qs.filter(status='active').count(),
        'is_officer': is_officer,
        'membership_types': MembershipType.objects.filter(company=company) if company else [],
    })


@login_required
def member_detail(request, pk):
    company = _get_company(request)
    member = get_object_or_404(
        Member.objects.select_related('membership_type', 'user'),
        pk=pk, company=company
    )

    is_officer = request.user.role in ADMIN_ROLES
    current_member = _get_current_member(request, company)

    # Permission: officers see everyone, members see themselves only
    if not is_officer and (not current_member or current_member.pk != member.pk):
        messages.error(request, 'You do not have permission to view this member.')
        return redirect('chama:member_list')

    contributions = Contribution.objects.filter(member=member).order_by('-date', '-created_at')[:20]
    loans = Loan.objects.filter(member=member).order_by('-requested_on')[:10]

    return render(request, 'chama/member_detail.html', {
        'member': member,
        'contributions': contributions,
        'loans': loans,
        'is_officer': is_officer,
        'current_member': current_member,
    })


# ============================================================
# MEMBER CREATE / EDIT / DELETE / TOGGLE
# ============================================================
# ============================================================
# MEMBER CREATE / EDIT / DELETE / TOGGLE
# ============================================================

@login_required
def member_create(request):
    """Officer creates a member directly (bypassing registration approval)."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:member_list')

    is_officer = request.user.role in [
        'super_admin', 'company_admin', 'company_manager',
        'chairperson', 'vice_chairperson', 'secretary', 'vice_secretary',
        'treasurer',
    ]
    if not is_officer:
        messages.error(request, 'Only Chama officers can add members.')
        return redirect('chama:member_list')

    fallback_password = _generate_default_password(company)

    if request.method == 'POST':
        form = MemberForm(
            request.POST,
            request.FILES,
            company=company,
            fallback_password=fallback_password,
        )
        if form.is_valid():
            member = form.save(commit=False)
            member.company = company
            if not member.member_number:
                member.member_number = _next_member_number(company)

            password = form.cleaned_data.get('default_password') or fallback_password
            role = form.cleaned_data.get('role') or 'member'

            new_user_created = False
            if not member.user and (member.email or member.phone):
                username_base = member.phone or member.email or f"member_{timezone.now().timestamp()}"
                username = username_base
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{username_base}_{counter}"
                    counter += 1

                full_name_parts = (member.full_name or '').split()
                user = User.objects.create_user(
                    username=username,
                    email=member.email or '',
                    password=password,
                    first_name=(full_name_parts[0] if full_name_parts else ''),
                    last_name=(' '.join(full_name_parts[1:]) if len(full_name_parts) > 1 else ''),
                    company=company,
                    is_active=True,
                )
                member.user = user
                new_user_created = True

            member.save()

            # Link or update Membership role
            if member.user:
                from apps.accounts.models import Membership
                membership, created = Membership.objects.get_or_create(
                    user=member.user,
                    company=company,
                    defaults={
                        'role': role,
                        'is_active': True,
                        'is_primary': not member.user.memberships.exists(),
                    }
                )
                if not created and role and membership.role != role:
                    membership.role = role
                    membership.save(update_fields=['role'])

                # Send invite email only for freshly created users
                if new_user_created and member.email:
                    success, err = _send_invite_email(
                        request, company, membership, member.user,
                        (member.full_name or '').split()[0] if member.full_name else 'Member',
                        member.email,
                        is_new_user=True,
                    )
                    if not success:
                        messages.warning(
                            request,
                            f'Member created, but invite email failed ({err}). '
                            f'Username: {membership.company_username}'
                        )

            messages.success(
                request,
                f'✅ Member "{member.full_name}" created (No. {member.member_number}).'
            )
            return redirect('chama:member_list')
    else:
        form = MemberForm(
            company=company,
            fallback_password=fallback_password,
        )

    return render(request, 'chama/member_form.html', {
        'form': form,
        'mode': 'create',
    })


@login_required
def member_edit(request, pk):
    """Edit an existing member."""
    company = _get_company(request)
    member = get_object_or_404(Member, pk=pk, company=company)

    is_officer = request.user.role in ADMIN_ROLES
    current_member = _get_current_member(request, company)

    if not is_officer and (not current_member or current_member.pk != member.pk):
        messages.error(request, 'You do not have permission to edit this member.')
        return redirect('chama:member_list')

    fallback_password = _generate_default_password(company)

    if request.method == 'POST':
        form = MemberForm(
            request.POST,
            request.FILES,
            instance=member,
            company=company,
            fallback_password=fallback_password,
        )
        if form.is_valid():
            member = form.save(commit=False)

            # If the member doesn't have a User yet but now has email/phone,
            # create one now so they can log in.
            new_user_created = False
            if not member.user and (member.email or member.phone):
                password = form.cleaned_data.get('default_password') or fallback_password
                username_base = member.phone or member.email
                username = username_base
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{username_base}_{counter}"
                    counter += 1

                full_name_parts = (member.full_name or '').split()
                user = User.objects.create_user(
                    username=username,
                    email=member.email or '',
                    password=password,
                    first_name=(full_name_parts[0] if full_name_parts else ''),
                    last_name=(' '.join(full_name_parts[1:]) if len(full_name_parts) > 1 else ''),
                    company=company,
                    is_active=True,
                )
                member.user = user
                new_user_created = True

            member.save()

            # Update Membership role if provided
            role = form.cleaned_data.get('role')
            if member.user and role:
                from apps.accounts.models import Membership
                membership, created = Membership.objects.get_or_create(
                    user=member.user,
                    company=company,
                    defaults={
                        'role': role,
                        'is_active': True,
                        'is_primary': not member.user.memberships.exists(),
                    }
                )
                if not created and membership.role != role:
                    membership.role = role
                    membership.save(update_fields=['role'])

                if new_user_created and member.email:
                    _send_invite_email(
                        request, company, membership, member.user,
                        (member.full_name or '').split()[0] if member.full_name else 'Member',
                        member.email,
                        is_new_user=True,
                    )

            messages.success(request, f'✅ Member "{member.full_name}" updated.')
            return redirect('chama:member_detail', pk=member.pk)
    else:
        form = MemberForm(
            instance=member,
            company=company,
            fallback_password=fallback_password,
        )

    return render(request, 'chama/member_form.html', {
        'form': form,
        'mode': 'edit',
        'member': member,
    })


@login_required
def member_delete(request, pk):
    """Delete a member (officers only)."""
    company = _get_company(request)
    member = get_object_or_404(Member, pk=pk, company=company)

    if request.user.role not in ['super_admin', 'company_admin', 'chairperson']:
        messages.error(request, 'Only Chairperson or Company Admin can delete members.')
        return redirect('chama:member_list')

    if request.method == 'POST':
        name = member.full_name
        member.delete()
        messages.info(request, f'🗑️ Member "{name}" deleted.')
        return redirect('chama:member_list')

    return render(request, 'chama/member_confirm_delete.html', {'member': member})


@login_required
def member_toggle_status(request, pk):
    """Toggle member between active / inactive."""
    company = _get_company(request)
    member = get_object_or_404(Member, pk=pk, company=company)

    if request.user.role not in ADMIN_ROLES:
        messages.error(request, 'Permission denied.')
        return redirect('chama:member_list')

    if request.method == 'POST':
        old_status = member.status
        member.status = 'inactive' if member.status == 'active' else 'active'
        member.save(update_fields=['status'])
        messages.success(
            request,
            f'✅ {member.full_name} status changed: {old_status} → {member.status}.'
        )

    return redirect('chama:member_list')





# ============================================================
# REGISTRATION
# ============================================================

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

    default_password = _generate_default_password(company)

    user = None
    is_new_user = False
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
        user = User.objects.create_user(
            username=username,
            email=reg.email or '',
            password=default_password,
            first_name=(reg.full_name.split()[0] if reg.full_name else ''),
            last_name=(' '.join(reg.full_name.split()[1:]) if reg.full_name else ''),
            company=company,
            is_active=True,
        )
        is_new_user = True

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

    from apps.accounts.models import Membership
    membership, created = Membership.objects.get_or_create(
        user=user,
        company=company,
        defaults={
            'role': 'member',
            'is_active': True,
            'is_primary': not user.memberships.exists()
        }
    )

    if is_new_user and user.email:
        success, err = _send_invite_email(
            request, company, membership, user,
            reg.full_name.split()[0],
            user.email,
            is_new_user=True,
        )
        if success:
            messages.success(request, f'✅ {reg.full_name} approved and invite email sent.')
        else:
            messages.warning(request, f'✅ {reg.full_name} approved, but email failed ({err}). Username: {membership.company_username}')
    else:
        messages.success(request, f'✅ {reg.full_name} approved. Linked to existing user account.')

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


# ============================================================
# MEMBER LOAN HISTORY / LIMIT ADJUST (AJAX)
# ============================================================

@login_required
def member_loan_history(request, member_pk):
    company = _get_company(request)
    if not company:
        return JsonResponse({'error': 'No company assigned.'}, status=400)

    if request.user.role not in ADMIN_ROLES:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    member = get_object_or_404(Member, pk=member_pk, company=company)

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