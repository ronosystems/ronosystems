from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse


@login_required
def dashboard_router(request):
    """Route user to correct dashboard based on role and business type."""

    user = request.user

    # SUPER ADMIN
    if user.role == 'super_admin':
        return redirect(reverse('super-admin-dashboard'))

    # COMPANY USERS — must have a company
    if not user.company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/admin/')

    business_type = user.company.business_type

    if business_type and business_type.name:
        name = business_type.name.lower()

        # EPA Shop
        if 'epa' in name or 'electronics' in name:
            return redirect('/epa_shop/dashboard/')

        # Kuku Biz (poultry) ← ADDED
        if 'kuku' in name or 'poultry' in name or 'chicken' in name:
            return redirect('/kuku_biz/dashboard/')

        # Supermarket / Grocery
        if 'supermarket' in name or 'grocery' in name:
            return redirect('/supermarket/dashboard/')

        # Healthcare
        if 'healthcare' in name or 'medical' in name:
            return redirect('/healthcare/dashboard/')

        # Education
        if 'education' in name or 'school' in name:
            return redirect('/education/dashboard/')

        # Restaurant / Food
        if 'restaurant' in name or 'food' in name:
            return redirect('/restaurant/dashboard/')

        # Retail
        if 'retail' in name:
            return redirect('/retail/dashboard/')

    # ─────────────────────────────────────────────
    # FALLBACK — no business type or no match
    # ─────────────────────────────────────────────
    messages.warning(
        request,
        'No dashboard is configured for your account. Please contact support.'
    )
    return redirect('/no-access/')