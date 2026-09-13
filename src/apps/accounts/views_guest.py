from django.shortcuts import render


def no_access(request):
    """Page shown to guests without a company — tells them to contact support."""
    return render(request, 'accounts/no_access.html')