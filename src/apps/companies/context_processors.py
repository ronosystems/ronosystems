"""
Context processors - Make support mode company available in every template.
"""

from apps.companies.models import Company
from apps.companies.models import CompanyJoinRequest


def pending_join_requests(request):
    """Inject pending_join_requests_count into every template context."""
    count = 0
    try:
        user = request.user
        if user.is_authenticated and getattr(user, 'role', None) in ('company_admin', 'super_admin'):
            company = getattr(user, 'company', None)
            if company:
                count = CompanyJoinRequest.objects.filter(
                    company=company, status='pending'
                ).count()
    except Exception:
        count = 0
    return {'pending_join_requests_count': count}


def support_mode_context(request):
    """
    Adds 'support_company' to context when in support mode.
    This allows base.html to display the viewed company name correctly.
    """
    support_company = None
    
    if request.user.is_authenticated:
        viewing_company_id = request.session.get('viewing_company_id')
        support_mode = request.session.get('support_mode', False)
        
        if support_mode and viewing_company_id:
            try:
                support_company = Company.objects.get(id=viewing_company_id)
            except Company.DoesNotExist:
                pass
    
    return {
        'support_company': support_company,
        'is_support_mode': support_company is not None,
    }