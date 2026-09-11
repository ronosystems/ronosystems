"""
Support Mode utilities - Centralize company resolution across all views.
Super Admins can enter Support Mode to view any company's interface.
"""

from apps.companies.models import Company


def get_active_company(request):
    """
    Get the currently active company for the request.
    
    Returns:
        tuple: (company, is_support_mode)
    """
    user = request.user
    
    # Support Mode: Super admin viewing a specific company
    if user.is_authenticated and user.role == 'super_admin':
        viewing_company_id = request.session.get('viewing_company_id')
        if viewing_company_id:
            try:
                company = Company.objects.get(id=viewing_company_id)
                return company, True
            except Company.DoesNotExist:
                request.session.pop('viewing_company_id', None)
                request.session.pop('support_mode', None)
                request.session.pop('support_started_at', None)
    
    # Regular mode
    if user.is_authenticated and user.company:
        return user.company, False
    
    return None, False


def is_support_mode(request):
    """Check if current request is in support mode"""
    return (
        request.user.is_authenticated 
        and request.user.role == 'super_admin'
        and request.session.get('support_mode', False)
        and request.session.get('viewing_company_id')
    )


def is_effective_admin(request):
    """Check if user should be treated as admin (support mode super admin = admin)"""
    if is_support_mode(request):
        return True
    return request.user.role in ['super_admin', 'company_admin', 'company_manager', 'stock_controller']


def get_effective_branch(request):
    """Get effective branch for filtering (None in support mode)"""
    if is_support_mode(request):
        return None
    user = request.user
    if user.role in ['super_admin', 'company_admin', 'company_manager', 'stock_controller']:
        return None
    return user.branch if user.branch else None