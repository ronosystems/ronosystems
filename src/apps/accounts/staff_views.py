# apps/accounts/staff_views.py
"""
COMPANY ADMIN - STAFF CRUD
Anafanya kazi ndani ya company yake TU.
HACHAGUI company - company inatoka kwenye request.tenant (middleware).

Membership model REAL fields:
  branch, company, created_at, id, invited_by, is_active,
  is_primary, role, updated_at, user
HAKUNA tenant, HAKUNA status - usitumie hizo!

URL base: /staff/
Domain: fieldmax.localhost/staff/ -> staff wa FIELDMAX tu

Templates:
  List   -> account/staff_list.html
  Form   -> account/staff_form.html  (Create + Edit - TEMPLATE MOJA)
  Detail -> account/staff_detail.html
  Delete -> account/staff_delete_confirm.html
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q

User = get_user_model()

# ============================================
# HELPER - Pata company ya admin aliyelogin
# ============================================
def _get_company(request):
    return getattr(request, 'tenant', None) or getattr(request, 'company', None)

def _check_company_admin(request):
    """Hakikisha ni company admin au superuser"""
    if request.user.is_superuser:
        return True
    company = _get_company(request)
    if not company:
        return False
    try:
        # FIX: company=, is_active= - sio tenant=, status=
        membership = request.user.memberships.filter(
            company=company, is_active=True
        ).first()
        if membership and membership.role in ['company_admin', 'company_manager', 'admin', 'manager']:
            return True
        # Fallback kwa user.role ya zamani
        if getattr(request.user, 'role', '') in ['company_admin', 'company_manager', 'admin', 'manager']:
            return True
    except Exception:
        pass
    return False

# Roles Company Admin anaweza kumpa staff wake
# HAWEZI kumpa super_admin
# ROLES ZINABADILIKA KWA BUSINESS TYPE - sio static
BASE_ROLES = [
    ('company_admin', 'Company Admin'),
    ('company_manager', 'Company Manager'),
    ('company_staff', 'Company Staff'),
]

ROLES_BY_BUSINESS_TYPE = {
    'epa-shop': [('cashier', 'Cashier'), ('sales', 'Sales'), ('mpesa_agent', 'Mpesa Agent')],
    'supermarket': [('cashier', 'Cashier'), ('sales', 'Sales'), ('mpesa_agent', 'Mpesa Agent')],
    'retail': [('cashier', 'Cashier'), ('sales', 'Sales'), ('mpesa_agent', 'Mpesa Agent')],
    'kuku-biz': [('sales', 'Sales'), ('cashier', 'Cashier')],
    'chama': [('cashier', 'Cashier')],
    'healthcare': [('cashier', 'Cashier')],
    'education': [('cashier', 'Cashier')],
    'restaurant': [('cashier', 'Cashier'), ('sales', 'Sales')],
    'mpesa': [('mpesa_agent', 'Mpesa Agent'), ('cashier', 'Cashier')],
    'mpesa-agent': [('mpesa_agent', 'Mpesa Agent'), ('cashier', 'Cashier')],
    'mobile-money': [('mpesa_agent', 'Mpesa Agent'), ('cashier', 'Cashier')],
    'workshop': [('technician', 'Technician'), ('cashier', 'Cashier')],
    'garage': [('technician', 'Technician'), ('cashier', 'Cashier')],
}

def get_roles_for_company(company):
    if not company:
        return BASE_ROLES
    bt = getattr(company, 'business_type', None)
    slug = ''
    if bt:
        slug = (getattr(bt, 'slug', '') or getattr(bt, 'name', '') or str(bt)).lower()
    for key, extra in ROLES_BY_BUSINESS_TYPE.items():
        if key in slug:
            return BASE_ROLES + extra
    return BASE_ROLES + [
        ('cashier', 'Cashier'),
        ('technician', 'Technician'),
        ('sales', 'Sales'),
        ('mpesa_agent', 'Mpesa Agent'),
    ]

# Backward compat
COMPANY_STAFF_ROLES = BASE_ROLES + [
    ('cashier', 'Cashier'),
    ('technician', 'Technician'),
    ('sales', 'Sales'),
    ('mpesa_agent', 'Mpesa Agent'),
]

# ============================================
# LIST - Orodha ya staff wa company hii
# ============================================
@login_required
def staff_list(request):
    company = _get_company(request)
    if not company:
        messages.error(request, "No company found for this domain.")
        return redirect('/auth/login/')

    if not _check_company_admin(request):
        messages.error(request, "You don't have permission to manage staff.")
        return redirect('/')

    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')

    # FIX: memberships__company - sio memberships__tenant
    users = User.objects.filter(
        Q(company=company) | Q(memberships__company=company)
    ).distinct().order_by('-date_joined')

    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    context = {
        'company': company,
        'users': users,
        'roles': get_roles_for_company(company),
        'search': search,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'stats': {
            'total': users.count(),
            'active': users.filter(is_active=True).count(),
            'inactive': users.filter(is_active=False).count(),
        }
    }
    return render(request, 'account/staff_list.html', context)

# ============================================
# CREATE - Company Admin anatengeneza staff wake
# Render: account/staff_form.html
# ============================================
@login_required
def staff_create(request):
    company = _get_company(request)
    if not company:
        messages.error(request, "No company found for this domain.")
        return redirect('/auth/login/')

    if not _check_company_admin(request):
        messages.error(request, "You don't have permission to create staff.")
        return redirect('accounts:staff-list')

    def form_context(extra=None):
        ctx = {
            'company': company,
            'roles': get_roles_for_company(company),
            'staff_user': None,
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
        staff_id = request.POST.get('staff_id', '').strip()

        preserved = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'role': role,
            'staff_id': staff_id,
        }

        if not username or not email or not password:
            messages.error(request, "Username, Email and Password are required.")
            return render(request, 'account/staff_form.html', form_context({'preserved': preserved}))

        if password != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'account/staff_form.html', form_context({'preserved': preserved}))

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return render(request, 'account/staff_form.html', form_context({'preserved': preserved}))

        if User.objects.filter(email=email).exists():
            messages.error(request, f"Email '{email}' already exists.")
            return render(request, 'account/staff_form.html', form_context({'preserved': preserved}))

        if role == 'super_admin':
            messages.error(request, "You cannot create a Super Admin.")
            return render(request, 'account/staff_form.html', form_context({'preserved': preserved}))

        # Create user - company ni hii ya admin mwenyewe, HACHAGUI
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

        # FIX: Membership kwa company=, sio tenant=
        # FIX: defaults HAINA status, ina is_active tu
        from apps.accounts.models import Membership
        Membership.objects.get_or_create(
            user=user,
            company=company,
            defaults={
                'role': role,
                'is_primary': True,
                'is_active': True,
            }
        )

        messages.success(request, f"Staff '{username}' created for {company.name} as {role}.")
        return redirect('accounts:staff-list')

    return render(request, 'account/staff_form.html', form_context())

# ============================================
# DETAIL - Angalia staff mmoja
# ============================================
@login_required
def staff_detail(request, user_id):
    company = _get_company(request)
    if not _check_company_admin(request):
        messages.error(request, "No permission.")
        return redirect('accounts:staff-list')

    user = get_object_or_404(User, id=user_id, company=company)

    context = {
        'company': company,
        'staff_user': user,
        # FIX: company=, sio tenant=
        'memberships': user.memberships.filter(company=company),
    }
    return render(request, 'account/staff_detail.html', context)

# ============================================
# EDIT - Badilisha staff + role
# Render: account/staff_form.html - TEMPLATE MOJA NA CREATE
# ============================================
@login_required
def staff_edit(request, user_id):
    company = _get_company(request)
    if not _check_company_admin(request):
        messages.error(request, "No permission.")
        return redirect('accounts:staff-list')

    user = get_object_or_404(User, id=user_id, company=company)

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name = request.POST.get('last_name', user.last_name).strip()
        user.email = request.POST.get('email', user.email).strip()
        user.phone = request.POST.get('phone', user.phone).strip()
        new_role = request.POST.get('role', user.role)
        if hasattr(user, 'staff_id'):
            user.staff_id = request.POST.get('staff_id', getattr(user, 'staff_id', '')).strip()

        # Badilisha role - lakini sio super_admin
        if new_role != 'super_admin':
            user.role = new_role
        else:
            messages.error(request, "You cannot assign Super Admin role.")
            return render(request, 'account/staff_form.html', {
                'company': company,
                'roles': get_roles_for_company(company),
                'staff_user': user,
                'is_edit': True,
                'form_mode': 'edit',
            })
        user.save()

        # FIX: Membership filter kwa company=
        try:
            from apps.accounts.models import Membership
            Membership.objects.filter(user=user, company=company).update(role=new_role)
        except Exception:
            pass

        # Badilisha password kama ameweka mpya
        new_password = request.POST.get('password', '')
        if new_password:
            user.set_password(new_password)
            user.save()

        messages.success(request, f"Staff '{user.username}' updated.")
        return redirect('accounts:staff-list')

    # GET - Fungua form ikiwa na data ya staff huyu
    context = {
        'company': company,
        'roles': get_roles_for_company(company),
        'staff_user': user,
        'is_edit': True,
        'form_mode': 'edit',
    }
    return render(request, 'account/staff_form.html', context)

# ============================================
# TOGGLE - Activate / Deactivate
# ============================================
@login_required
def staff_toggle_status(request, user_id):
    company = _get_company(request)
    if not _check_company_admin(request):
        messages.error(request, "No permission.")
        return redirect('accounts:staff-list')

    user = get_object_or_404(User, id=user_id, company=company)

    if user.id == request.user.id:
        messages.error(request, "You cannot deactivate yourself.")
        return redirect('accounts:staff-list')

    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save()
        try:
            from apps.accounts.models import Membership
            # FIX: company=, is_active= - HAKUNA status
            Membership.objects.filter(user=user, company=company).update(
                is_active=user.is_active,
            )
        except Exception:
            pass
        status = "activated" if user.is_active else "deactivated"
        messages.success(request, f"Staff '{user.username}' {status}.")
    return redirect('accounts:staff-list')

# ============================================
# DELETE - Futa staff
# ============================================
@login_required
def staff_delete(request, user_id):
    company = _get_company(request)
    if not _check_company_admin(request):
        messages.error(request, "No permission.")
        return redirect('accounts:staff-list')

    user = get_object_or_404(User, id=user_id, company=company)

    if user.id == request.user.id:
        messages.error(request, "You cannot delete yourself.")
        return redirect('accounts:staff-list')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"Staff '{username}' deleted.")
        return redirect('accounts:staff-list')

    context = {'company': company, 'staff_user': user}
    return render(request, 'account/staff_delete_confirm.html', context)