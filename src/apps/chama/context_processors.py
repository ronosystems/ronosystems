def chama_badges(request):
    """
    Inject sidebar badge counts for the Chama app.
    Safe for anonymous users and users without a company.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}

    company = (
        getattr(request, 'company', None)
        or getattr(request, 'current_company', None)
        or getattr(request.user, 'company', None)
    )
    if not company:
        return {}

    from .models import Registration, Loan  # local import avoids AppRegistryNotReady

    return {
        'pending_registrations_count': Registration.objects.filter(
            company=company, status='pending',
        ).count(),
        'pending_loans_count': Loan.objects.filter(
            company=company, status='pending',
        ).count(),
    }