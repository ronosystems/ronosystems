# apps/company/employee_views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.companies.models import Company
from apps.companies.models import BusinessType
from apps.epa_shop.models import Branch
from django.utils import timezone

User = get_user_model()


@login_required
@staff_member_required
def employee_list(request):
    """List all users/employees with search and filters (Super Admin)"""
    
    # Get all users
    users = User.objects.all().order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(staff_id__icontains=search_query)  # Changed from employee_id to staff_id
        )
    
    # Filter by role
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(role=role_filter)
    
    # Filter by company
    company_filter = request.GET.get('company', '')
    if company_filter:
        users = users.filter(company_id=company_filter)
    
    # Filter by business type
    business_type_filter = request.GET.get('business_type', '')
    if business_type_filter:
        users = users.filter(company__business_type_id=business_type_filter)
    
    # Filter by branch
    branch_filter = request.GET.get('branch', '')
    if branch_filter:
        users = users.filter(branch_id=branch_filter)
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        if status_filter == 'active':
            users = users.filter(is_active=True)
        elif status_filter == 'inactive':
            users = users.filter(is_active=False)
    
    # Get counts for stats
    all_users = User.objects.all()
    active_count = all_users.filter(is_active=True).count()
    inactive_count = all_users.filter(is_active=False).count()
    verified_count = all_users.filter(is_verified=True).count()
    
    # Get all companies for filter dropdown
    companies = Company.objects.filter(is_active=True).order_by('name')
    
    # Get all business types for filter dropdown
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')
    
    # Get all branches for filter dropdown
    branches = Branch.objects.filter(is_active=True).order_by('name')
    
    # Role choices
    roles = User._meta.get_field('role').choices
    
    context = {
        'users': users,
        'total_users': all_users.count(),
        'active_count': active_count,
        'inactive_count': inactive_count,
        'verified_count': verified_count,
        'search_query': search_query,
        'role_filter': role_filter,
        'company_filter': company_filter,
        'business_type_filter': business_type_filter,
        'branch_filter': branch_filter,
        'status_filter': status_filter,
        'companies': companies,
        'business_types': business_types,
        'branches': branches,
        'roles': roles,
        'page_title': 'Employees',
        'page_subtitle': 'Manage all employees',
    }
    return render(request, 'employees/list.html', context)


@login_required
@staff_member_required
def employee_detail(request, pk):
    """View employee details"""
    user = get_object_or_404(User, pk=pk)
    
    context = {
        'user': user,
        'page_title': user.get_full_name() or user.username,
        'page_subtitle': 'Employee details',
    }
    return render(request, 'employees/detail.html', context)


@login_required
@staff_member_required
def employee_edit(request, pk):
    """Edit employee details"""
    user = get_object_or_404(User, pk=pk)
    companies = Company.objects.filter(is_active=True).order_by('name')
    branches = Branch.objects.filter(is_active=True).order_by('name')
    roles = User._meta.get_field('role').choices
    
    if request.method == 'POST':
        # Get form data
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        staff_id = request.POST.get('staff_id', '')  # Changed from employee_id
        company_id = request.POST.get('company', '')
        branch_id = request.POST.get('branch', '')
        role = request.POST.get('role', '')
        department = request.POST.get('department', '')
        position = request.POST.get('position', '')
        hire_date = request.POST.get('hire_date', '')
        is_active = request.POST.get('is_active') == 'on'
        is_verified = request.POST.get('is_verified') == 'on'
        two_factor_enabled = request.POST.get('two_factor_enabled') == 'on'
        
        # Update user
        try:
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.phone = phone
            user.staff_id = staff_id  # Changed from employee_id
            user.company_id = company_id if company_id else None
            user.branch_id = branch_id if branch_id else None
            user.role = role
            user.department = department
            user.position = position
            user.hire_date = hire_date if hire_date else None
            user.is_active = is_active
            user.is_verified = is_verified
            user.two_factor_enabled = two_factor_enabled
            user.save()
            
            messages.success(request, f'Employee {user.get_full_name()} updated successfully!')
            return redirect('superadmin-employee-list')
        except Exception as e:
            messages.error(request, f'Error updating employee: {str(e)}')
    
    context = {
        'user': user,
        'companies': companies,
        'branches': branches,
        'roles': roles,
        'page_title': f'Edit {user.get_full_name()}',
        'page_subtitle': 'Edit employee details',
    }
    return render(request, 'employees/edit.html', context)


@login_required
@staff_member_required
def employee_toggle_status(request, pk):
    """Toggle employee active status"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        user.is_active = not user.is_active
        user.save()
        status = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'Employee {user.get_full_name()} has been {status}.')
        return redirect('superadmin-employee-list')
    
    return redirect('superadmin-employee-list')


@login_required
@staff_member_required
def employee_delete(request, pk):
    """Delete employee"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        try:
            name = user.get_full_name()
            user.delete()
            messages.success(request, f'Employee {name} deleted successfully!')
            return redirect('superadmin-employee-list')
        except Exception as e:
            messages.error(request, f'Error deleting employee: {str(e)}')
    
    context = {
        'user': user,
        'page_title': 'Delete Employee',
        'page_subtitle': f'Confirm deletion of {user.get_full_name()}',
    }
    return render(request, 'employees/delete.html', context)


@login_required
def employee_create(request):
    """Create a new employee (Company Admin/Manager)"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized
    is_authorized = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to add employees.')
        return redirect('employee-list')
    
    branches = Branch.objects.filter(company=company, is_active=True)
    roles = User._meta.get_field('role').choices
    
    if request.method == 'POST':
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        staff_id = request.POST.get('staff_id', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        role = request.POST.get('role', '')
        department = request.POST.get('department', '').strip()
        position = request.POST.get('position', '').strip()
        hire_date = request.POST.get('hire_date', '')
        branch_id = request.POST.get('branch_id', '')
        
        # Validate required fields
        if not first_name:
            messages.error(request, 'First name is required.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        if not last_name:
            messages.error(request, 'Last name is required.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        if not email:
            messages.error(request, 'Email is required.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        if not username:
            messages.error(request, 'Username is required.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        if not role:
            messages.error(request, 'Role is required.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        # Validate password
        if not password:
            messages.error(request, 'Password is required.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        # Check if username already exists
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        # Check if email already exists
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return render(request, 'employees/create.html', {
                'branches': branches,
                'roles': roles,
                'page_title': 'Add Employee',
                'page_subtitle': 'Add a new employee to your company',
            })
        
        # Create user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                staff_id=staff_id,  # Changed from employee_id
                role=role,
                company=company,
                department=department,
                position=position,
                hire_date=hire_date if hire_date else None,
                branch_id=branch_id if branch_id else None,
                is_active=True,
                is_verified=True
            )
            
            messages.success(request, f'Employee {user.get_full_name()} created successfully!')
            return redirect('employee-list')
            
        except Exception as e:
            messages.error(request, f'Error creating employee: {str(e)}')
    
    context = {
        'branches': branches,
        'roles': roles,
        'page_title': 'Add Employee',
        'page_subtitle': 'Add a new employee to your company',
    }
    return render(request, 'employees/create.html', context)