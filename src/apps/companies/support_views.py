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
    
    active_session = SupportSession.objects.filter(
        super_admin=request.user,
        is_active=True
    ).first()
    
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
def delete_support_session(request, session_id):
    """Delete a single support session (audit log entry)"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('support-selector')
    
    session = get_object_or_404(
        SupportSession,
        id=session_id,
        super_admin=request.user  # Only own sessions
    )
    
    company_name = session.company.name
    session.delete()
    
    messages.success(request, f'🗑️ Support session for "{company_name}" removed.')
    return redirect('support-selector')


@login_required
@super_admin_required
def clear_all_support_sessions(request):
    """Clear ALL ended support sessions for the current super admin"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('support-selector')
    
    # Only delete ENDED sessions — keep active one
    count, _ = SupportSession.objects.filter(
        super_admin=request.user,
        is_active=False
    ).delete()
    
    if count > 0:
        messages.success(request, f'🗑️ Cleared {count} ended support session(s).')
    else:
        messages.info(request, 'No ended sessions to clear.')
    
    return redirect('support-selector')


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
    
    return redirect('/epa_shop/dashboard/')


@login_required
@super_admin_required
def exit_support_mode(request):
    """Exit support mode"""
    SupportSession.objects.filter(
        super_admin=request.user,
        is_active=True
    ).update(is_active=False, ended_at=timezone.now())
    
    # Clear session flags
    for key in ['viewing_company_id', 'support_mode', 'support_started_at']:
        request.session.pop(key, None)
    request.session.modified = True
    request.session.save()
    
    messages.success(request, '👋 Exited Support Mode')
    return redirect('/companies/')