# apps/accounts/staff_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse 
from apps.companies.support_utils import get_active_company
from apps.companies.models import Branch
from .models import User, Membership



@login_required
def staff_list(request):
    """
    READ: List all staff members for the active company.

    Customer sio staff - ana page yake ya Customers.
    Kwa hiyo Customer / Guest / Super Admin hawaonekani hapa,
    hata kama wana Membership kwenye hii company.
    """
    company, is_viewing_company = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect('/dashboard/')

    # Roles ambazo sio staff - ziko na page zao wenyewe
    NON_STAFF_ROLES = ['customer', 'guest', 'super_admin']

    # Get all active memberships for this company
    # 1. Ondoa Membership zenye role ya customer/guest
    # 2. Ondoa pia kama User mwenyewe ni customer (kwa usalama, kama
    #    Membership role ilikuwa company_staff lakini User.role ni customer)
    memberships = Membership.objects.filter(
        company=company, is_active=True
    ).exclude(
        role__in=NON_STAFF_ROLES
    ).exclude(
        user__role__in=NON_STAFF_ROLES
    ).select_related('user', 'branch').order_by('-created_at')

    # Search functionality
    query = request.GET.get('q', '').strip()
    if query:
        memberships = memberships.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(company_username__icontains=query)
        )

    context = {
        'company': company,
        'memberships': memberships,
        'query': query,
        'page_title': f'Staff - {company.name}',
    }
    return render(request, 'accounts/staff_list.html', context)


@login_required
def staff_create(request):
    """
    CREATE: Add a new member to the company.
    Sends an email invite with the generated username.
    """
    company, _ = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect('/dashboard/')

    allowed_roles = company.allowed_roles
    allowed_role_keys = [r[0] for r in allowed_roles]
    branches = Branch.objects.filter(company=company, is_active=True)

    def _render_form(form_data=None):
        return render(request, 'accounts/staff_form.html', {
            'company': company,
            'branches': branches,
            'role_choices': allowed_roles,
            'is_edit': False,
            'form_data': form_data,
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', 'company_staff')
        branch_id = request.POST.get('branch')

        # --- Validation ---
        if role not in allowed_role_keys:
            messages.error(request, f"The role '{role}' is not valid for {company.business_type.name}.")
            return _render_form(request.POST)

        if not email or not first_name or not last_name:
            messages.error(request, "First Name, Last Name, and Email are required.")
            return _render_form(request.POST)

        branch = None
        if branch_id:
            branch = Branch.objects.filter(id=branch_id, company=company).first()

        try:
            with transaction.atomic():
                # 1. Resolve the User (create if new)
                user = User.objects.filter(email=email).first()
                is_new_user = False

                if not user:
                    user = User.objects.create_user(
                        email=email,
                        username=email,
                        password=get_random_string(32),   # unusable; they must reset
                        first_name=first_name,
                        last_name=last_name,
                        phone=phone,
                        is_active=True,
                    )
                    is_new_user = True
                elif Membership.objects.filter(user=user, company=company).exists():
                    messages.warning(request, f"{first_name} is already a member of {company.name}.")
                    return redirect('accounts:staff-list')

                # 2. Create the Membership (auto-generates company_username)
                membership = Membership.objects.create(
                    user=user,
                    company=company,
                    branch=branch,
                    role=role,
                    is_active=True,
                )
                if not user.memberships.exclude(pk=membership.pk).exists():
                    membership.is_primary = True
                    membership.save(update_fields=['is_primary'])

            # 3. Send the Invite Email (outside the DB transaction so a slow
            #    SMTP call doesn't hold locks / delay rollback on failure)
            try:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)

                protocol = 'https' if request.is_secure() else 'http'
                system_domain = getattr(settings, 'SYSTEM_DOMAIN', 'localhost:8000')

                if company.custom_domain and company.domain_verified and not settings.DEBUG:
                    # Production: company has a verified custom domain (e.g. fieldmax.shop)
                    mother_host = company.custom_domain
                elif company.subdomain:
                    # Tenant subdomain: fieldmax.localhost:8000 or fieldmax.ronosystems.com
                    mother_host = f"{company.subdomain}.{system_domain}"
                else:
                    # Fallback: mother domain only (shouldn't happen for a real company)
                    mother_host = system_domain

                reset_path = reverse(
                    'accounts:password_reset_confirm',
                    kwargs={'uidb64': uid, 'token': token},
                )
                reset_link = f"{protocol}://{mother_host}{reset_path}"

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
                messages.success(
                    request,
                    f"✅ {first_name} added to {company.name}. "
                    f"An invitation email has been sent to {email}."
                )
            except Exception as e:
                messages.warning(
                    request,
                    f"✅ {first_name} added to {company.name}. "
                    f"However, the email failed to send ({str(e)}). "
                    f"Please give them their username: {membership.company_username}"
                )

            return redirect('accounts:staff-list')

        except Exception as e:
            messages.error(request, f"Error adding staff: {str(e)}")
            return _render_form(request.POST)

    return _render_form()

@login_required
def staff_resend_invite(request, membership_id):
    """
    Resend the invitation / password-reset email for an existing membership.
    Generates a fresh token so the recipient can set a new password.
    """
    company, _ = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect('/dashboard/')

    membership = get_object_or_404(
        Membership, id=membership_id, company=company, is_active=True
    )
    user = membership.user

    # POST-only for safety, even though it's idempotent
    if request.method != 'POST':
        return redirect('accounts:staff-list')

    try:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        protocol = 'https' if request.is_secure() else 'http'
        system_domain = getattr(settings, 'SYSTEM_DOMAIN', 'localhost:8000')

        if company.custom_domain and company.domain_verified and not settings.DEBUG:
            mother_host = company.custom_domain
        elif company.subdomain:
            mother_host = f"{company.subdomain}.{system_domain}"
        else:
            mother_host = system_domain

        reset_path = reverse(
            'accounts:password_reset_confirm',
            kwargs={'uidb64': uid, 'token': token},
        )
        reset_link = f"{protocol}://{mother_host}{reset_path}"

        context = {
            'first_name': user.first_name or user.username,
            'company_name': company.name,
            'role': membership.get_role_display(),
            'username': membership.company_username,
            'email': user.email,
            'reset_link': reset_link,
            'is_new_user': False,   # existing user, "reset optional" wording
        }
        html_message = render_to_string('emails/staff_invite.html', context)
        plain_message = strip_tags(html_message)

        send_mail(
            f"You have been added to {company.name}",
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        messages.success(
            request,
            f"✅ Invitation re-sent to {user.email}. "
            f"A fresh reset link has been emailed."
        )
    except Exception as e:
        messages.error(
            request,
            f"Failed to resend invite to {user.email}: {e}"
        )

    return redirect('accounts:staff-list')



@login_required
def staff_edit(request, membership_id):
    """
    UPDATE: Edit an existing staff member's details.
    """
    company, _ = get_active_company(request)
    membership = get_object_or_404(Membership, id=membership_id, company=company)
    user = membership.user
    
    allowed_roles = company.allowed_roles 
    allowed_role_keys = [r[0] for r in allowed_roles]

    if request.method == 'POST':
        role = request.POST.get('role', membership.role)
        
        if role not in allowed_role_keys:
            messages.error(request, f"The role '{role}' is not valid for {company.business_type.name}.")
            return render(request, 'accounts/staff_form.html', {
                'company': company,
                'membership': membership,
                'staff_user': user,
                'branches': Branch.objects.filter(company=company, is_active=True),
                'role_choices': allowed_roles,
                'is_edit': True
            })

        try:
            with transaction.atomic():
                # Update User details
                user.first_name = request.POST.get('first_name', user.first_name).strip()
                user.last_name = request.POST.get('last_name', user.last_name).strip()
                user.phone = request.POST.get('phone', user.phone).strip()
                user.save()

                # Update Membership details
                membership.role = role
                branch_id = request.POST.get('branch')
                if branch_id:
                    membership.branch = Branch.objects.filter(id=branch_id, company=company).first()
                else:
                    membership.branch = None
                
                membership.save()

                messages.success(request, f"Successfully updated {user.full_name}.")
                return redirect('accounts:staff-list')
        except Exception as e:
            messages.error(request, f"Error updating staff: {str(e)}")

    branches = Branch.objects.filter(company=company, is_active=True)
    return render(request, 'accounts/staff_form.html', {
        'company': company,
        'membership': membership,
        'staff_user': user,
        'branches': branches,
        'role_choices': allowed_roles,
        'is_edit': True
    })


@login_required
def staff_detail(request, membership_id):
    """
    READ: View details of a single staff member.
    """
    company, _ = get_active_company(request)
    membership = get_object_or_404(Membership, id=membership_id, company=company)
    
    return render(request, 'accounts/staff_detail.html', {
        'company': company,
        'membership': membership,
        'staff_user': membership.user,
    })


@login_required
def staff_delete(request, membership_id):
    """
    DELETE: Remove a staff member from THIS company.
    Does not delete the global User account (so they can still log into other companies).
    """
    company, _ = get_active_company(request)
    membership = get_object_or_404(Membership, id=membership_id, company=company)
    
    # Prevent the company admin from deleting themselves
    if membership.user == request.user:
        messages.error(request, "You cannot remove yourself from the company.")
        return redirect('accounts:staff-list')

    if request.method == 'POST':
        user_name = membership.user.full_name
        # Deactivate membership instead of hard deleting (preserves transaction history)
        membership.is_active = False
        membership.save()

        messages.success(request, f"{user_name} has been removed from {company.name}.")
        return redirect('accounts:staff-list')

    return render(request, 'accounts/staff_confirm_delete.html', {
        'company': company,
        'membership': membership,
    })


@login_required
def staff_toggle_status(request, membership_id):
    """
    UPDATE: Toggle staff active/inactive status (Soft ban).
    """
    company, _ = get_active_company(request)
    membership = get_object_or_404(Membership, id=membership_id, company=company)
    
    if membership.user == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('accounts:staff-list')

    if request.method == 'POST':
        membership.is_active = not membership.is_active
        membership.save()
        
        status_text = "activated" if membership.is_active else "deactivated"
        messages.success(request, f"{membership.user.full_name} has been {status_text}.")
        
    return redirect('accounts:staff-list')