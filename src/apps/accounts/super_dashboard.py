from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Count
from django.utils import timezone
from apps.companies.models import Company
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def super_admin_dashboard(request):
    """Super Admin Dashboard - Only accessible by super admins"""
    
    # Check if user is super admin
    if request.user.role != 'super_admin':
        messages.warning(request, 'Access denied. Super Admin only.')
        return redirect('/dashboard/')
    
    # Check if super admin is viewing a specific company
    if 'viewing_company_id' in request.session:
        try:
            company = Company.objects.get(id=request.session['viewing_company_id'])
            # Redirect to company dashboard
            return redirect('/company/dashboard/')
        except Company.DoesNotExist:
            # If company not found, clear session
            if 'viewing_company_id' in request.session:
                del request.session['viewing_company_id']
            messages.warning(request, 'Company not found. Returning to your dashboard.')
    
    # Get stats
    total_companies = Company.objects.count()
    active_companies = Company.objects.filter(is_active=True).count()
    total_users = User.objects.count()
    
    # Users by role
    users_by_role = User.objects.values('role').annotate(count=Count('id'))
    
    # Companies by plan
    companies_by_plan = Company.objects.values('plan').annotate(count=Count('id'))
    
    # Expiring subscriptions (next 30 days)
    thirty_days_from_now = timezone.now() + timezone.timedelta(days=30)
    expiring_subscriptions = Company.objects.filter(
        subscription_end__lte=thirty_days_from_now,
        subscription_end__gte=timezone.now(),
        is_active=True
    ).count()
    
    # Recent companies
    recent_companies = Company.objects.order_by('-created_at')[:10]
    
    context = {
        'stats': {
            'total_companies': total_companies,
            'active_companies': active_companies,
            'total_users': total_users,
            'expiring_subscriptions': expiring_subscriptions,
        },
        'users_by_role': users_by_role,
        'companies_by_plan': companies_by_plan,
        'recent_companies': recent_companies,
        'is_super_admin': True,
        'is_viewing_company': False,
        'page_title': 'Super Admin Dashboard',
        'page_subtitle': 'Manage all companies and system settings',
    }
    
    return render(request, 'admin/super_dashboard.html', context)