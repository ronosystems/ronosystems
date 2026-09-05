from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from apps.companies.models import Company
from django.contrib.auth import get_user_model

User = get_user_model()


@login_required
def company_dashboard_view(request):
    """
    Company dashboard for super admins viewing a company
    Also used by regular company admins
    """
    
    # Check if user is super admin or company admin
    if request.user.role == 'super_admin':
        # Super admin - check if viewing a company
        if 'viewing_company_id' not in request.session:
            messages.warning(request, 'You are not viewing any company.')
            return redirect('/super-admin/dashboard/')
        
        company = get_object_or_404(Company, id=request.session['viewing_company_id'])
        is_viewing_company = True
        
    elif request.user.role in ['company_admin', 'company_manager']:
        # Company admin/manager - use their own company
        if not request.user.company:
            messages.warning(request, 'You are not assigned to any company.')
            return redirect('/dashboard/')
        company = request.user.company
        is_viewing_company = False
        
    else:
        # Regular user - access denied
        messages.warning(request, 'Access denied.')
        return redirect('/dashboard/')
    
    # Get company stats
    total_users = company.users.filter(is_active=True).count()
    
    # Users by role
    users_by_role = company.users.values('role').annotate(count=Count('id'))
    
    # Get company branches
    branches_count = 0
    branches = []
    try:
        from apps.epa_shop.models import Branch
        branches = Branch.objects.filter(company=company, is_active=True)
        branches_count = branches.count()
    except:
        pass
    
    # Get company products
    products_count = 0
    try:
        from apps.epa_shop.models import Phone, Electronic, Accessory
        products_count = Phone.objects.filter(company=company).count() + \
                       Electronic.objects.filter(company=company).count() + \
                       Accessory.objects.filter(company=company).count()
    except:
        pass
    
    # Get recent employees
    recent_employees = company.users.filter(is_active=True).order_by('-created_at')[:5]
    
    # Get sales stats (if available)
    sales_count = 0
    revenue = 0
    try:
        from apps.epa_shop.models import Sale
        sales = Sale.objects.filter(company=company)
        sales_count = sales.count()
        revenue = sales.aggregate(Sum('net_amount'))['net_amount__sum'] or 0
    except:
        pass
    
    context = {
        'company': company,
        'viewing_company': company,
        'is_viewing_company': is_viewing_company,
        'total_users': total_users,
        'users_by_role': users_by_role,
        'branches': branches,
        'branches_count': branches_count,
        'products_count': products_count,
        'recent_employees': recent_employees,
        'sales_count': sales_count,
        'revenue': revenue,
        'page_title': f'Dashboard - {company.name}',
        'page_subtitle': 'Company Dashboard',
    }
    
    return render(request, 'company/dashboard.html', context)


@login_required
def company_dashboard_stats(request):
    """
    API endpoint for company dashboard stats
    Used by AJAX for real-time updates
    """
    
    if request.user.role == 'super_admin':
        if 'viewing_company_id' not in request.session:
            return JsonResponse({'error': 'No company selected'}, status=400)
        company = get_object_or_404(Company, id=request.session['viewing_company_id'])
        
    elif request.user.role in ['company_admin', 'company_manager']:
        if not request.user.company:
            return JsonResponse({'error': 'No company assigned'}, status=400)
        company = request.user.company
    else:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    stats = {
        'total_users': company.users.filter(is_active=True).count(),
        'total_employees': company.users.filter(is_active=True, role__in=['company_employee', 'company_staff']).count(),
        'total_admins': company.users.filter(is_active=True, role__in=['company_admin', 'company_manager']).count(),
    }
    
    try:
        from apps.epa_shop.models import Sale
        sales = Sale.objects.filter(company=company)
        stats['total_sales'] = sales.count()
        stats['revenue'] = sales.aggregate(Sum('net_amount'))['net_amount__sum'] or 0
    except:
        pass
    
    return JsonResponse(stats)


@login_required
def switch_to_company(request, pk):
    """
    Switch to company dashboard as if you are the company admin
    Super admin stays logged in but session tracks the company being viewed
    """
    # Check if user is super admin
    if request.user.role != 'super_admin':
        messages.warning(request, 'Access denied. Super Admin only.')
        return redirect('/dashboard/')
    
    company = get_object_or_404(Company, id=pk)
    
    # Store the company ID in session
    request.session['viewing_company_id'] = company.id
    
    # Store the original user ID for easy return
    if 'original_user_id' not in request.session:
        request.session['original_user_id'] = request.user.id
    
    messages.success(request, f'✅ You are now viewing {company.name} as company admin')
    
    # Redirect to company dashboard
    return redirect('/company/dashboard/')


@login_required
def exit_company_view(request):
    """Exit company view and return to super admin dashboard"""
    
    # Check if user is super admin
    if request.user.role != 'super_admin':
        messages.warning(request, 'Access denied. Super Admin only.')
        return redirect('/dashboard/')
    
    if 'viewing_company_id' in request.session:
        company_name = None
        try:
            company = Company.objects.get(id=request.session['viewing_company_id'])
            company_name = company.name
        except:
            pass
        
        # Clear the viewing company session
        if 'viewing_company_id' in request.session:
            del request.session['viewing_company_id']
        
        if company_name:
            messages.success(request, f'✅ Exited {company_name}. Returned to your dashboard.')
        else:
            messages.success(request, '✅ Exited company view. Returned to your dashboard.')
    else:
        messages.warning(request, 'You are not viewing any company.')
    
    return redirect('/super-admin/dashboard/')