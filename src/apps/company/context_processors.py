def company_context(request):
    """
    Add company to template context for all requests.

    Priority order for resolving the "current" company:
      1. request.tenant_company  (set by CustomDomainMiddleware when a
                                  verified custom domain is used)
      2. request.user.company    (the user's own tenant)
      3. request.company         (legacy fallback)
    """
    company = None
    user_branch = None

    # 1. Custom domain resolution wins
    company = getattr(request, 'tenant_company', None)

    # 2. Fall back to the authenticated user's company
    if not company and request.user.is_authenticated:
        if hasattr(request.user, 'company') and request.user.company:
            company = request.user.company

    # 3. Legacy fallback
    if not company and hasattr(request, 'company'):
        company = request.company

    # User's branch
    if request.user.is_authenticated:
        if hasattr(request.user, 'branch') and request.user.branch:
            user_branch = request.user.branch

    return {
        'company': company,
        'company_id': company.id if company else None,
        'user_branch': user_branch,
    }