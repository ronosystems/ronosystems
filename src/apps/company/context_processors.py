def company_context(request):
    """
    Add company to template context for all requests
    """
    company = None
    user_branch = None
    
    # Get company from user
    if request.user.is_authenticated:
        if hasattr(request.user, 'company') and request.user.company:
            company = request.user.company
        
        # Get user's branch
        if hasattr(request.user, 'branch') and request.user.branch:
            user_branch = request.user.branch
    
    # If company is not on user, try from session or URL
    if not company and hasattr(request, 'company'):
        company = request.company
    
    return {
        'company': company,
        'company_id': company.id if company else None,
        'user_branch': user_branch,
    }
