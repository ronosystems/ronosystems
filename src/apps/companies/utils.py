# apps/companies/utils.py

def get_current_company(request):
    """
    Resolve the 'current' company for a request.

    Priority:
      1. request.tenant_company  (set by CustomDomainMiddleware for
                                  verified custom domains)
      2. request.user.company    (the authenticated user's own company)
      3. None
    """
    company = getattr(request, 'tenant_company', None)
    if company is not None:
        return company

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return getattr(user, 'company', None)
    return None


def get_current_company_id(request):
    """Convenience: just the ID, or None."""
    company = get_current_company(request)
    return company.id if company else None
