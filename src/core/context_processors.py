def company_context(request):
    """
    Hakikisha kila template inapata `company`, `current_company`,
    `support_company` - hata kama view haikupita.
    Inachukua kutoka kwenye middleware: request.tenant / request.company
    """
    company = getattr(request, 'tenant', None) or getattr(request, 'company', None)
    return {
        'company': company,
        'current_company': company,
        'support_company': company,
    }
