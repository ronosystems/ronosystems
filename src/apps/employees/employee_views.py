# apps/employees/employee_views.py
# Super Admin Employee Management

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.companies.models import Company, BusinessType
from apps.company.models import Branch

User = get_user_model()


# ============================================
# HELPERS
# ============================================

def get_role_choices():
    """Return the model's role choices for dropdowns."""
    return User._meta.get_field('role').choices


def get_active_companies():
    return Company.objects.filter(is_active=True).order_by('name')


def get_active_business_types():
    return BusinessType.objects.filter(is_active=True).order_by('name')


def get_active_branches():
    return Branch.objects.filter(is_active=True).order_by('name')


# ============================================
# LIST
# ============================================

@login_required
@staff_member_required
def employee_list(request):
    """List all users/employees with search and filters (Super Admin)."""

    users = User.objects.select_related('company', 'branch').order_by('-date_joined')

    # ---- Search ----
    search_query = request.GET.get('search', '').strip()
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(staff_id__icontains=search_query)
        )

    # ---- Filters ----
    role_filter = request.GET.get('role', '').strip()
    if role_filter:
        users = users.filter(role=role_filter)

    company_filter = request.GET.get('company', '').strip()
    if company_filter:
        users = users.filter(company_id=company_filter)

    business_type_filter = request.GET.get('business_type', '').strip()
    if business_type_filter:
        users = users.filter(company__business_type_id=business_type_filter)

    branch_filter = request.GET.get('branch', '').strip()
    if branch_filter:
        users = users.filter(branch_id=branch_filter)

    status_filter = request.GET.get('status', '').strip()
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    elif status_filter == 'verified':
        users = users.filter(is_verified=True)
    elif status_filter == 'unverified':
        users = users.filter(is_verified=False)

    # ---- Stats ----
    all_users = User.objects.all()
    stats = {
        'total_users': all_users.count(),
        'active_count': all_users.filter(is_active=True).count(),
        'inactive_count': all_users.filter(is_active=False).count(),
        'verified_count': all_users.filter(is_verified=True).count(),
    }

    context = {
        'users': users,
        'stats': stats,
        'search_query': search_query,
        'role_filter': role_filter,
        'company_filter': company_filter,
        'business_type_filter': business_type_filter,
        'branch_filter': branch_filter,
        'status_filter': status_filter,
        'companies': get_active_companies(),
        'business_types': get_active_business_types(),
        'branches': get_active_branches(),
        'roles': get_role_choices(),
        'page_title': 'Employees',
        'page_subtitle': 'Manage all employees across companies',
    }
    return render(request, 'superadmin/employees/list.html', context)


# ============================================
# DETAIL
# ============================================

@login_required
@staff_member_required
def employee_detail(request, pk):
    """View employee details (Super Admin)."""
    employee = get_object_or_404(
        User.objects.select_related('company', 'branch'),
        pk=pk
    )

    context = {
        'employee': employee,
        'page_title': employee.get_full_name() or employee.username,
        'page_subtitle': 'Employee details',
    }
    return render(request, 'superadmin/employees/detail.html', context)


# ============================================
# CREATE
# ============================================

@login_required
@staff_member_required
def employee_create(request):
    """Create a new employee from the Super Admin interface."""

    companies = get_active_companies()
    branches = get_active_branches()
    roles = get_role_choices()

    def _render_form():
        return render(request, 'superadmin/employees/create.html', {
            'companies': companies,
            'branches': branches,
            'roles': roles,
            'page_title': 'Add Employee',
            'page_subtitle': 'Create a new employee account',
        })

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        username = request.POST.get('username', '').strip()
        phone = request.POST.get('phone', '').strip()
        staff_id = request.POST.get('staff_id', '').strip()
        role = request.POST.get('role', '').strip()
        department = request.POST.get('department', '').strip()
        position = request.POST.get('position', '').strip()
        hire_date = request.POST.get('hire_date', '').strip()
        company_id = request.POST.get('company', '').strip()
        branch_id = request.POST.get('branch', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        # ---- Required fields ----
        if not first_name:
            messages.error(request, 'First name is required.')
            return _render_form()
        if not last_name:
            messages.error(request, 'Last name is required.')
            return _render_form()
        if not email:
            messages.error(request, 'Email is required.')
            return _render_form()
        if not username:
            messages.error(request, 'Username is required.')
            return _render_form()
        if not role:
            messages.error(request, 'Role is required.')
            return _render_form()

        # ---- Password checks ----
        if not password:
            messages.error(request, 'Password is required.')
            return _render_form()
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return _render_form()
        try:
            validate_password(password)
        except ValidationError as e:
            messages.error(request, f'Password error: {", ".join(e.messages)}')
            return _render_form()

        # ---- Uniqueness ----
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return _render_form()
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Email already exists.')
            return _render_form()

        # ---- Validate company / branch belong together ----
        company = None
        if company_id:
            company = Company.objects.filter(pk=company_id, is_active=True).first()
            if not company:
                messages.error(request, 'Selected company is invalid.')
                return _render_form()

        branch = None
        if branch_id:
            branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
            if not branch:
                messages.error(request, 'Selected branch is invalid.')
                return _render_form()
            if company and branch.company_id != company.id:
                messages.error(request, 'Selected branch does not belong to the selected company.')
                return _render_form()

        # ---- Create ----
        try:
            employee = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                staff_id=staff_id,
                role=role,
                company=company,
                branch=branch,
                department=department,
                position=position,
                hire_date=hire_date or None,
                is_active=True,
                is_verified=True,
            )
            messages.success(
                request,
                f'Employee {employee.get_full_name() or employee.username} created successfully!'
            )
            return redirect('employees:superadmin-employee-list')

        except Exception as e:
            messages.error(request, f'Error creating employee: {e}')
            return _render_form()

    # ---- GET ----
    return _render_form()


# ============================================
# EDIT
# ============================================

@login_required
@staff_member_required
def employee_edit(request, pk):
    """Edit employee details (Super Admin)."""
    employee = get_object_or_404(User, pk=pk)

    companies = get_active_companies()
    branches = get_active_branches()
    roles = get_role_choices()

    def _render_form():
        return render(request, 'superadmin/employees/edit.html', {
            'employee': employee,
            'companies': companies,
            'branches': branches,
            'roles': roles,
            'page_title': f'Edit {employee.get_full_name() or employee.username}',
            'page_subtitle': 'Edit employee details',
        })

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        staff_id = request.POST.get('staff_id', '').strip()
        role = request.POST.get('role', '').strip()
        department = request.POST.get('department', '').strip()
        position = request.POST.get('position', '').strip()
        hire_date = request.POST.get('hire_date', '').strip()
        company_id = request.POST.get('company', '').strip()
        branch_id = request.POST.get('branch', '').strip()

        is_active = request.POST.get('is_active') == 'on'
        is_verified = request.POST.get('is_verified') == 'on'
        two_factor_enabled = request.POST.get('two_factor_enabled') == 'on'

        # ---- Validation ----
        if not first_name:
            messages.error(request, 'First name is required.')
            return _render_form()
        if not last_name:
            messages.error(request, 'Last name is required.')
            return _render_form()
        if not email:
            messages.error(request, 'Email is required.')
            return _render_form()
        if not role:
            messages.error(request, 'Role is required.')
            return _render_form()

        # ---- Uniqueness (exclude self) ----
        if User.objects.filter(email__iexact=email).exclude(pk=employee.pk).exists():
            messages.error(request, 'Email already exists.')
            return _render_form()

        # ---- Validate company / branch belong together ----
        company = None
        if company_id:
            company = Company.objects.filter(pk=company_id, is_active=True).first()
            if not company:
                messages.error(request, 'Selected company is invalid.')
                return _render_form()

        branch = None
        if branch_id:
            branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
            if not branch:
                messages.error(request, 'Selected branch is invalid.')
                return _render_form()
            if company and branch.company_id != company.id:
                messages.error(request, 'Selected branch does not belong to the selected company.')
                return _render_form()

        # ---- Save ----
        try:
            employee.first_name = first_name
            employee.last_name = last_name
            employee.email = email
            employee.phone = phone
            employee.staff_id = staff_id
            employee.role = role
            employee.company = company
            employee.branch = branch
            employee.department = department
            employee.position = position
            employee.hire_date = hire_date or None
            employee.is_active = is_active
            employee.is_verified = is_verified
            employee.two_factor_enabled = two_factor_enabled
            employee.save()

            messages.success(
                request,
                f'Employee {employee.get_full_name() or employee.username} updated successfully!'
            )
            return redirect('employees:superadmin-employee-list')

        except Exception as e:
            messages.error(request, f'Error updating employee: {e}')
            return _render_form()

    # ---- GET ----
    return _render_form()


# ============================================
# TOGGLE STATUS
# ============================================

@login_required
@staff_member_required
def employee_toggle_status(request, pk):
    """Toggle employee active status (Super Admin)."""
    employee = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        # Prevent a super admin from deactivating themselves
        if employee.pk == request.user.pk:
            messages.error(request, 'You cannot change your own status.')
            return redirect('employees:superadmin-employee-list')

        employee.is_active = not employee.is_active
        employee.save(update_fields=['is_active'])
        status = 'activated' if employee.is_active else 'deactivated'
        messages.success(
            request,
            f'Employee {employee.get_full_name() or employee.username} has been {status}.'
        )

    return redirect('employees:superadmin-employee-list')


# ============================================
# DELETE
# ============================================

@login_required
@staff_member_required
def employee_delete(request, pk):
    """Delete an employee (Super Admin)."""
    employee = get_object_or_404(User, pk=pk)

    # Prevent self-deletion
    if employee.pk == request.user.pk:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('employees:superadmin-employee-list')

    if request.method == 'POST':
        try:
            name = employee.get_full_name() or employee.username
            employee.delete()
            messages.success(request, f'Employee {name} deleted successfully!')
            return redirect('employees:superadmin-employee-list')
        except Exception as e:
            messages.error(request, f'Error deleting employee: {e}')

    context = {
        'employee': employee,
        'page_title': 'Delete Employee',
        'page_subtitle': f'Confirm deletion of {employee.get_full_name() or employee.username}',
    }
    return render(request, 'superadmin/employees/delete.html', context)