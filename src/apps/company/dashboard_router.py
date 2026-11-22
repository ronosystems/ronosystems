from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse



@login_required
def dashboard_router(request):
    """Route user to correct dashboard based on role and business type."""
    user = request.user

    # 1. CUSTOMERS (Must be first!)
    if getattr(user, 'role', None) == 'customer':
        return redirect('customers:dashboard')

    # 2. SUPER ADMIN
    if user.role == 'super_admin':
        return redirect('web_accounts:super-admin-dashboard')

    # 3. COMPANY USERS — must have a company
    if not user.company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/no-access/')

    business_type = user.company.business_type

    if business_type and business_type.name:
        name = business_type.name.lower()

        # EPA Shop
        if 'epa' in name or 'electronics' in name:
            return redirect('/epa_shop/dashboard/')

        # Kuku Biz (poultry)
        if 'kuku' in name or 'poultry' in name or 'chicken' in name:
            return redirect('/kuku_biz/dashboard/')

        # Chama / SACCO / Savings
        if 'chama' in name or 'sacco' in name or 'savings' in name:
            return redirect('/chama/dashboard/')
            
        # ... rest of your business types ...

    # FALLBACK
    messages.warning(
        request,
        'No dashboard is configured for your account. Please contact support.'
    )
    return redirect('/no-access/')


    
