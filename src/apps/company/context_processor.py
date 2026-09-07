def company_context(request):
    """
    Add company to template context for all requests
    """
    company = None
    
    # Get company from user
    if request.user.is_authenticated and hasattr(request.user, 'company'):
        company = request.user.company
    
    # If company is not on user, try from session or URL
    if not company and hasattr(request, 'company'):
        company = request.company
    
    return {
        'company': company,
        'company_id': company.id if company else None,
    }