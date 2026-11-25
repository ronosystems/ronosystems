# apps/accounts/users_views.py
"""
SUPER ADMIN - GLOBAL USERS CRUD
Membership model REAL fields:
  branch, company, created_at, id, invited_by, is_active,
  is_primary, role, updated_at, user
HAKUNA tenant, HAKUNA status - usitumie hizo!
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q

User = get_user_model()

def _is_super_admin(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') == 'super_admin')

SUPER_ADMIN_ROLES = [
    ('super_admin', 'Super Admin - Platform Boss'),
    ('company_admin', 'Company Admin - Boss wa Company'),
    ('company_manager', 'Company Manager'),
    ('company_staff', 'Company Staff'),
    ('cashier', 'Cashier'),
    ('technician', 'Technician'),
    ('sales', 'Sales'),
    ('mpesa_agent', 'Mpesa Agent'),
    ('customer', 'Customer'),
]

# ============================================
# LIST
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def user_list(request):
    from apps.companies.models import Company

    companies = Company.objects.filter(is_active=True).order_by('name')

    search = request.GET.get('search', '')
    company_filter = request.GET.get('company', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')

    users = User.objects.all().select_related('company').order_by('-date_joined')

    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    if company_filter:
        # FIX: memberships__company, sio memberships__tenant
        users = users.filter(
            Q(company_id=company_filter) | Q(memberships__company_id=company_filter)
        ).distinct()
    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    context = {
        'users': users,
        'companies': companies,
        'roles': SUPER_ADMIN_ROLES,
        'search': search,
        'company_filter': company_filter,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'stats': {
            'total': User.objects.count(),
            'active': User.objects.filter(is_active=True).count(),
            'inactive': User.objects.filter(is_active=False).count(),
            'super_admins': User.objects.filter(role='super_admin').count(),
            'company_admins': User.objects.filter(role='company_admin').count(),
        }
    }
    return render(request, 'account/users_list.html', context)

# ============================================
# CREATE - HAPA NDIPO ERROR ILIPOTOKA
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def user_create(request):
    from apps.companies.models import Company
    from apps.accounts.models import Membership

    companies = Company.objects.filter(is_active=True).order_by('name')

    def form_context(extra=None):
        ctx = {
            'companies': companies,
            'roles': SUPER_ADMIN_ROLES,
            'detail_user': None,
            'is_edit': False,
            'form_mode': 'create',
        }
        if extra:
            ctx.update(extra)
        return ctx

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', 'company_staff')
        company_id = request.POST.get('company', '')
        staff_id = request.POST.get('staff_id', '').strip()

        preserved = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'role': role,
            'company': company_id,
            'staff_id': staff_id,
        }

        if not username or not email or not password:
            messages.error(request, "Username, Email and Password are required.")
            return render(request, 'account/users_form.html', form_context({'preserved': preserved}))

        if password != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'account/users_form.html', form_context({'preserved': preserved}))

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return render(request, 'account/users_form.html', form_context({'preserved': preserved}))

        if User.objects.filter(email=email).exists():
            messages.error(request, f"Email '{email}' already exists.")
            return render(request, 'account/users_form.html', form_context({'preserved': preserved}))

        company = None
        if company_id:
            company = Company.objects.filter(id=company_id).first()
        if role != 'super_admin' and not company:
            messages.error(request, "Please select a Company for this user.")
            return render(request, 'account/users_form.html', form_context({'preserved': preserved}))

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            company=company,
        )
        if hasattr(user, 'staff_id'):
            user.staff_id = staff_id
            user.save()

        # FIX: get_or_create(user=user, company=company) - SIO tenant
        # FIX: defaults HAINA status
        if company:
            Membership.objects.get_or_create(
                user=user,
                company=company,
                defaults={
                    'role': role,
                    'is_primary': True,
                    'is_active': True,
                }
            )

        if role == 'company_admin':
            messages.success(request, f"'{username}' is now Company Admin of {company.name}.")
        else:
            messages.success(request, f"User '{username}' created.")
        return redirect('accounts:user-list')

    return render(request, 'account/users_form.html', form_context())

# ============================================
# DETAIL
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)
    context = {
        'detail_user': user,
        # FIX: select_related('company') tu, sio tenant
        'memberships': user.memberships.all().select_related('company'),
    }
    return render(request, 'account/users_detail.html', context)

# ============================================
# EDIT
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def user_edit(request, user_id):
    from apps.companies.models import Company
    from apps.accounts.models import Membership

    user = get_object_or_404(User, id=user_id)
    companies = Company.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        old_company = user.company
        new_company_id = request.POST.get('company', '')
        new_role = request.POST.get('role', user.role)

        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name = request.POST.get('last_name', user.last_name).strip()
        user.email = request.POST.get('email', user.email).strip()
        user.phone = request.POST.get('phone', user.phone).strip()
        user.role = new_role
        if hasattr(user, 'staff_id'):
            user.staff_id = request.POST.get('staff_id', getattr(user, 'staff_id', '')).strip()

        new_company = None
        if new_company_id:
            new_company = Company.objects.filter(id=new_company_id).first()
            user.company = new_company
        else:
            if new_role == 'super_admin':
                user.company = None
            else:
                messages.error(request, "Please select a Company - only Super Admin can have no company.")
                return render(request, 'account/users_form.html', {
                    'companies': companies,
                    'roles': SUPER_ADMIN_ROLES,
                    'detail_user': user,
                    'is_edit': True,
                    'form_mode': 'edit',
                })
        user.save()

        # FIX: Membership kwa company, sio tenant, na is_active sio status
        if new_company and new_company != old_company:
            Membership.objects.filter(user=user).update(is_active=False)
            Membership.objects.get_or_create(
                user=user,
                company=new_company,
                defaults={
                    'role': new_role,
                    'is_primary': True,
                    'is_active': True,
                }
            )
            messages.success(request, f"User moved from {old_company} to {new_company}.")
        else:
            if new_company:
                Membership.objects.filter(user=user, company=new_company).update(role=new_role)

        new_password = request.POST.get('password', '')
        if new_password:
            user.set_password(new_password)
            user.save()

        messages.success(request, f"User '{user.username}' updated.")
        return redirect('accounts:user-list')

    context = {
        'companies': companies,
        'roles': SUPER_ADMIN_ROLES,
        'detail_user': user,
        'is_edit': True,
        'form_mode': 'edit',
    }
    return render(request, 'account/users_form.html', context)

# ============================================
# ASSIGN COMPANY ADMIN
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def assign_company_admin(request, user_id):
    from apps.companies.models import Company
    from apps.accounts.models import Membership

    user = get_object_or_404(User, id=user_id)
    companies = Company.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        company_id = request.POST.get('company')
        company = Company.objects.filter(id=company_id).first()
        if not company:
            messages.error(request, "Select a company.")
            return render(request, 'account/assign_company_admin.html', {'detail_user': user, 'companies': companies})

        user.company = company
        user.role = 'company_admin'
        user.save()

        # FIX: company=, sio tenant=
        Membership.objects.get_or_create(
            user=user,
            company=company,
            defaults={
                'role': 'company_admin',
                'is_primary': True,
                'is_active': True,
            }
        )
        Membership.objects.filter(user=user, company=company).update(role='company_admin', is_active=True)

        messages.success(request, f"'{user.username}' is now Company Admin of {company.name}.")
        return redirect('accounts:user-list')

    context = {'detail_user': user, 'companies': companies}
    return render(request, 'account/assign_company_admin.html', context)

# ============================================
# TOGGLE
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def user_toggle_status(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.id == request.user.id:
        messages.error(request, "You cannot deactivate yourself.")
        return redirect('accounts:user-list')
    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save()
        try:
            from apps.accounts.models import Membership
            Membership.objects.filter(user=user).update(is_active=user.is_active)
        except Exception:
            pass
        messages.success(request, f"User '{user.username}' {'activated' if user.is_active else 'deactivated'}.")
    return redirect('accounts:user-list')

# ============================================
# DELETE
# ============================================
@login_required
@user_passes_test(_is_super_admin)
def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.id == request.user.id:
        messages.error(request, "You cannot delete yourself.")
        return redirect('accounts:user-list')
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"User '{username}' deleted.")
        return redirect('accounts:user-list')
    context = {'detail_user': user}
    return render(request, 'account/users_delete_confirm.html', context)