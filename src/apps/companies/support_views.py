from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from .models import Company, SupportSession


def super_admin_required(view_func):
    """Decorator: Only allow super admins"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'super_admin':
            messages.error(request, 'Access denied. Super admin only.')
            return redirect('/dashboard/')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@super_admin_required
def company_selector(request):
    """Company selector page for support mode"""
    companies = Company.objects.filter(is_active=True).order_by('name')
    
    # Get active support session if any
    active_session = SupportSession.objects.filter(
        super_admin=request.user,
        is_active=True
    ).first()
    
    # Recent support sessions (last 10)
    recent_sessions = SupportSession.objects.filter(
        super_admin=request.user
    )[:10]
    
    context = {
        'companies': companies,
        'active_session': active_session,
        'recent_sessions': recent_sessions,
        'page_title': 'Support Mode - Select Company',
        'page_subtitle': 'View and support any company',
    }
    return render(request, 'companies/support_selector.html', context)


@login_required
@super_admin_required
def enter_support_mode(request, company_id):
    """Enter support mode for a specific company"""
    company = get_object_or_404(Company, id=company_id)
    
    # End any existing active session
    SupportSession.objects.filter(
        super_admin=request.user,
        is_active=True
    ).update(is_active=False, ended_at=timezone.now())
    
    # Create new support session
    SupportSession.objects.create(
        super_admin=request.user,
        company=company,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        reason=request.GET.get('reason', ''),
        is_active=True
    )
    
    # Set session flags
    request.session['viewing_company_id'] = company.id
    request.session['support_mode'] = True
    request.session['support_started_at'] = timezone.now().isoformat()
    
    messages.success(request, f'✅ Support Mode active: Viewing {company.name}')
    
    # Redirect to the company's dashboard
    business_type = company.business_type
    if business_type:
        business_name = business_type.name.lower()
        if 'epa' in business_name or 'electronics' in business_name:
            return redirect('/epa_shop/dashboard/')
        elif 'supermarket' in business_name:
            return redirect('/supermarket/dashboard/')
        # Add more business types as needed
    
    return redirect('/epa_shop/dashboard/')


@login_required
@super_admin_required
def exit_support_mode(request):
    """Exit support mode"""
    # End active session
    SupportSession.objects.filter(
        super_admin=request.user,
        is_active=True
    ).update(is_active=False, ended_at=timezone.now())
    
    # Clear session flags
    if 'viewing_company_id' in request.session:
        del request.session['viewing_company_id']
    if 'support_mode' in request.session:
        del request.session['support_mode']
    if 'support_started_at' in request.session:
        del request.session['support_started_at']
    
    messages.success(request, '👋 Exited Support Mode')
    return redirect('/companies/')