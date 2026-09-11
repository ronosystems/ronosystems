# apps/company/employee_views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from apps.epa_shop.models import Branch
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)

User = get_user_model()


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_roles():
    """Get role choices for dropdown"""
    return [
        ('company_admin', 'Company Admin'),
        ('company_manager', 'Company Manager'),
        ('company_cashier', 'Company Cashier'),
        ('company_agent', 'Company Agent'),
        ('company_staff', 'Company Staff'),
        ('stock_controller', 'Stock Controller'),
        ('mpesa_agent', 'M-Pesa Agent'),
    ]


def get_branches(company):
    """Get branches for the company"""
    return Branch.objects.filter(company=company, is_active=True)


@login_required
def employee_list(request):
    """List employees for the logged-in user's company"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized (support mode = always authorized)
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to view employees.')
        return redirect('/dashboard/')
    
    # Get employees for this company
    employees = User.objects.filter(
        company=company
    ).exclude(
        role='super_admin'
    ).order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        employees = employees.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(staff_id__icontains=search_query)
        )
    
    # Filter by role
    role_filter = request.GET.get('role', '')
    if role_filter:
        employees = employees.filter(role=role_filter)
    
    # Filter by branch
    branch_filter = request.GET.get('branch', '')
    if branch_filter:
        employees = employees.filter(branch_id=branch_filter)
    
    # Stats
    stats = {
        'total_employees': User.objects.filter(company=company).count(),
        'managers': User.objects.filter(company=company, role='company_manager').count(),
        'staff': User.objects.filter(company=company, role='company_staff').count(),
        'cashiers': User.objects.filter(company=company, role='company_cashier').count(),
        'agents': User.objects.filter(company=company, role='company_agent').count(),
        'stock_controllers': User.objects.filter(company=company, role='stock_controller').count(),
        'mpesa_agents': User.objects.filter(company=company, role='mpesa_agent').count(),
    }
    
    # Get branches for filter
    branches = Branch.objects.filter(company=company, is_active=True)
    
    context = {
        'company': company,
        'employees': employees,
        'stats': stats,
        'branches': branches,
        'roles': get_roles(),
        'search_query': search_query,
        'role_filter': role_filter,
        'branch_filter': branch_filter,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Employees',
        'page_subtitle': 'Manage your company employees',
    }
    return render(request, 'company/employees/list.html', context)


@login_required
def employee_detail(request, pk):
    """View employee details (Company Admin/Manager)"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized (support mode = always authorized)
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to view employee details.')
        return redirect('employee-list')
    
    employee = get_object_or_404(User, pk=pk, company=company)
    
    context = {
        'company': company,
        'employee': employee,
        'is_viewing_company': is_viewing_company,
        'page_title': employee.get_full_name() or employee.username,
        'page_subtitle': 'Employee details',
    }
    return render(request, 'company/employee_detail.html', context)


@login_required
def employee_create(request):
    """Add a new employee to the company"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized (support mode = always authorized)
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to add employees.')
        return redirect('employee-list')
    
    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            username = request.POST.get('username', '').strip()
            phone = request.POST.get('phone', '').strip()
            role = request.POST.get('role', 'company_staff')
            department = request.POST.get('department', '').strip()
            position = request.POST.get('position', '').strip()
            staff_id = request.POST.get('staff_id', '').strip()
            branch_id = request.POST.get('branch_id', '')
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            # Validation
            if not all([first_name, last_name, email, username, password, confirm_password]):
                messages.error(request, 'Please fill in all required fields.')
                return render(request, 'company/employees/form.html', {
                    'company': company,
                    'roles': get_roles(),
                    'branches': get_branches(company),
                    'is_viewing_company': is_viewing_company,
                    'page_title': 'Add Employee',
                    'page_subtitle': 'Add a new employee to your company',
                })
            
            if password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return render(request, 'company/employees/form.html', {
                    'company': company,
                    'roles': get_roles(),
                    'branches': get_branches(company),
                    'is_viewing_company': is_viewing_company,
                    'page_title': 'Add Employee',
                    'page_subtitle': 'Add a new employee to your company',
                })
            
            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email already exists.')
                return render(request, 'company/employees/form.html', {
                    'company': company,
                    'roles': get_roles(),
                    'branches': get_branches(company),
                    'is_viewing_company': is_viewing_company,
                    'page_title': 'Add Employee',
                    'page_subtitle': 'Add a new employee to your company',
                })
            
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return render(request, 'company/employees/form.html', {
                    'company': company,
                    'roles': get_roles(),
                    'branches': get_branches(company),
                    'is_viewing_company': is_viewing_company,
                    'page_title': 'Add Employee',
                    'page_subtitle': 'Add a new employee to your company',
                })
            
            # Validate password
            try:
                validate_password(password)
            except ValidationError as e:
                messages.error(request, f'Password error: {", ".join(e.messages)}')
                return render(request, 'company/employees/form.html', {
                    'company': company,
                    'roles': get_roles(),
                    'branches': get_branches(company),
                    'is_viewing_company': is_viewing_company,
                    'page_title': 'Add Employee',
                    'page_subtitle': 'Add a new employee to your company',
                })
            
            # Create employee
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=role,
                company=company,
                department=department,
                position=position,
                staff_id=staff_id,
                branch_id=branch_id if branch_id else None,
                is_active=True,
                is_verified=True,
            )
            
            messages.success(request, f'Employee {user.get_full_name()} created successfully!')
            return redirect('employee-list')
            
        except Exception as e:
            messages.error(request, f'Error creating employee: {str(e)}')
            return render(request, 'company/employees/form.html', {
                'company': company,
                'roles': get_roles(),
                'branches': get_branches(company),
                'is_viewing_company': is_viewing_company,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
    
    # GET request - show form
    context = {
        'company': company,
        'roles': get_roles(),
        'branches': get_branches(company),
        'is_viewing_company': is_viewing_company,
        'page_title': 'Add Employee',
        'page_subtitle': 'Add a new employee to your company',
    }
    return render(request, 'company/employees/form.html', context)


@login_required
def employee_edit(request, pk):
    """Edit employee details"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized (support mode = always authorized)
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to edit employees.')
        return redirect('employee-list')
    
    employee = get_object_or_404(User, pk=pk, company=company)
    
    if request.method == 'POST':
        try:
            employee.first_name = request.POST.get('first_name', '').strip()
            employee.last_name = request.POST.get('last_name', '').strip()
            employee.phone = request.POST.get('phone', '').strip()
            employee.role = request.POST.get('role', 'company_staff')
            employee.department = request.POST.get('department', '').strip()
            employee.position = request.POST.get('position', '').strip()
            employee.staff_id = request.POST.get('staff_id', '').strip()
            employee.branch_id = request.POST.get('branch_id', None) or None
            employee.is_active = request.POST.get('is_active') == 'on'
            
            employee.save()
            
            messages.success(request, f'Employee {employee.get_full_name()} updated successfully!')
            return redirect('employee-list')
            
        except Exception as e:
            messages.error(request, f'Error updating employee: {str(e)}')
    
    context = {
        'employee': employee,
        'company': company,
        'roles': get_roles(),
        'branches': get_branches(company),
        'is_viewing_company': is_viewing_company,
        'page_title': f'Edit {employee.get_full_name()}',
        'page_subtitle': 'Edit employee details',
    }
    return render(request, 'company/employees/form.html', context)


@login_required
def employee_delete(request, pk):
    """Delete employee"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized (support mode = always authorized)
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to delete employees.')
        return redirect('employee-list')
    
    employee = get_object_or_404(User, pk=pk, company=company)
    
    # Prevent self-deletion (except super admin in support mode)
    if employee.id == request.user.id and not is_viewing_company:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('employee-list')
    
    if request.method == 'POST':
        try:
            name = employee.get_full_name()
            employee.delete()
            messages.success(request, f'Employee {name} deleted successfully!')
            return redirect('employee-list')
        except Exception as e:
            messages.error(request, f'Error deleting employee: {str(e)}')
    
    context = {
        'company': company,
        'employee': employee,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Delete Employee',
        'page_subtitle': f'Confirm deletion of {employee.get_full_name()}',
    }
    return render(request, 'company/employees/confirm_delete.html', context)


@login_required
def employee_toggle_status(request, pk):
    """Toggle employee active status"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized (support mode = always authorized)
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to change employee status.')
        return redirect('employee-list')
    
    employee = get_object_or_404(User, pk=pk, company=company)
    
    # Prevent self-status change (except super admin in support mode)
    if employee.id == request.user.id and not is_viewing_company:
        messages.error(request, 'You cannot change your own status.')
        return redirect('employee-list')
    
    if request.method == 'POST':
        employee.is_active = not employee.is_active
        employee.save()
        status = 'activated' if employee.is_active else 'deactivated'
        messages.success(request, f'Employee {employee.get_full_name()} has been {status}.')
        return redirect('employee-list')
    
    return redirect('employee-list')
