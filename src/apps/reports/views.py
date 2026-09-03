from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from apps.companies.models import Company
from apps.plans.models import Plan, Subscription
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
@staff_member_required
def reports_dashboard(request):
    """Main reports dashboard"""
    
    # Get date range from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    period = request.GET.get('period', 'month')  # month, quarter, year
    
    # Default to current month
    if not start_date or not end_date:
        today = timezone.now().date()
        if period == 'month':
            start_date = today.replace(day=1).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        elif period == 'quarter':
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            start_date = today.replace(month=quarter_month, day=1).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        elif period == 'year':
            start_date = today.replace(month=1, day=1).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
    
    # Convert to datetime
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    # ============================================
    # COMPANY REPORTS
    # ============================================
    
    # Total companies
    total_companies = Company.objects.count()
    active_companies = Company.objects.filter(is_active=True).count()
    inactive_companies = total_companies - active_companies
    
    # Companies by plan
    companies_by_plan = Company.objects.values('plan').annotate(count=Count('id'))
    
    # Companies by business type
    companies_by_business = Company.objects.values('business_type__name').annotate(count=Count('id'))
    
    # ============================================
    # USER REPORTS
    # ============================================
    
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    
    # Users by role
    users_by_role = User.objects.values('role').annotate(count=Count('id'))
    
    # Users by company
    users_by_company = User.objects.values('company__name').annotate(count=Count('id'))
    
    # ============================================
    # SUBSCRIPTION REPORTS
    # ============================================
    
    # Total subscriptions
    total_subscriptions = Subscription.objects.count()
    active_subscriptions = Subscription.objects.filter(status='active').count()
    
    # Expiring soon (next 30 days)
    thirty_days_from_now = timezone.now() + timedelta(days=30)
    expiring_subscriptions = Subscription.objects.filter(
        end_date__lte=thirty_days_from_now,
        end_date__gte=timezone.now(),
        status='active'
    ).count()
    
    # Expired subscriptions
    expired_subscriptions = Subscription.objects.filter(
        end_date__lt=timezone.now(),
        status='active'
    ).count()
    
    # ============================================
    # REVENUE REPORTS (Selected Period)
    # ============================================
    
    # Get subscriptions within date range
    period_subscriptions = Subscription.objects.filter(
        start_date__gte=start_datetime,
        start_date__lte=end_datetime
    )
    
    total_revenue = period_subscriptions.aggregate(
        total=Sum('plan__price')
    )['total'] or 0
    
    # Revenue by plan
    revenue_by_plan = period_subscriptions.values('plan__display_name').annotate(
        total=Sum('plan__price'),
        count=Count('id')
    )
    
    # Monthly revenue (for chart)
    monthly_revenue = []
    current_month = start_datetime
    while current_month <= end_datetime:
        month_start = current_month
        if current_month.month == 12:
            next_month = current_month.replace(year=current_month.year + 1, month=1)
        else:
            next_month = current_month.replace(month=current_month.month + 1)
        
        month_subs = Subscription.objects.filter(
            start_date__gte=month_start,
            start_date__lt=next_month
        )
        month_total = month_subs.aggregate(total=Sum('plan__price'))['total'] or 0
        
        monthly_revenue.append({
            'month': current_month.strftime('%B %Y'),
            'revenue': float(month_total),
            'count': month_subs.count()
        })
        current_month = next_month
    
    # ============================================
    # STORAGE REPORTS
    # ============================================
    
    # Placeholder for storage calculations
    total_storage_used = 0
    total_storage_limit = 0
    
    for company in Company.objects.all():
        # Calculate storage used (you can add actual storage tracking)
        # For now, we'll use mock data
        total_storage_used += 50  # Mock value
        if company.plan == 'free':
            total_storage_limit += 100
        elif company.plan == 'basic':
            total_storage_limit += 500
        elif company.plan == 'pro':
            total_storage_limit += 2000
        elif company.plan == 'enterprise':
            total_storage_limit += 10000
        else:
            total_storage_limit += 100
    
    # ============================================
    # EXPIRING COMPANIES
    # ============================================
    
    expiring_companies = Company.objects.filter(
        subscription_end__lte=thirty_days_from_now,
        subscription_end__gte=timezone.now(),
        is_active=True
    ).order_by('subscription_end')[:10]
    
    # ============================================
    # CONTEXT
    # ============================================
    
    context = {
        # Company Stats
        'total_companies': total_companies,
        'active_companies': active_companies,
        'inactive_companies': inactive_companies,
        'companies_by_plan': companies_by_plan,
        'companies_by_business': companies_by_business,
        
        # User Stats
        'total_users': total_users,
        'active_users': active_users,
        'users_by_role': users_by_role,
        'users_by_company': users_by_company,
        
        # Subscription Stats
        'total_subscriptions': total_subscriptions,
        'active_subscriptions': active_subscriptions,
        'expiring_subscriptions': expiring_subscriptions,
        'expired_subscriptions': expired_subscriptions,
        
        # Revenue Stats
        'total_revenue': total_revenue,
        'revenue_by_plan': revenue_by_plan,
        'monthly_revenue': monthly_revenue,
        
        # Storage Stats
        'total_storage_used': total_storage_used,
        'total_storage_limit': total_storage_limit,
        'storage_percentage': round((total_storage_used / total_storage_limit) * 100, 1) if total_storage_limit > 0 else 0,
        
        # Expiring Companies
        'expiring_companies': expiring_companies,
        
        # Date Range
        'start_date': start_date,
        'end_date': end_date,
        'period': period,
        
        'page_title': 'Reports',
        'page_subtitle': 'Company & Analytics Reports',
    }
    
    return render(request, 'admin/reports_dashboard.html', context)
