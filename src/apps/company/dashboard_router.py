from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

@login_required
def dashboard_router(request):
    """Route user to correct dashboard based on role and business type"""
    
    user = request.user
    
    # SUPER ADMIN
    if user.role == 'super_admin':
        return redirect(reverse('super-admin-dashboard'))
    
    # COMPANY USERS
    if not user.company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/admin/')
    
    business_type = user.company.business_type
    
    if business_type:
        name = business_type.name.lower()
        
        # EPA Shop - Web Dashboard
        if 'epa' in name or 'electronics' in name:
            return redirect('/epa_shop/dashboard/')  # Changed to epa_shop
        
        # Supermarket
        elif 'supermarket' in name or 'grocery' in name:
            return redirect('/supermarket/dashboard/')
        
        # Healthcare
        elif 'healthcare' in name or 'medical' in name:
            return redirect('/healthcare/dashboard/')
        
        # Education
        elif 'education' in name or 'school' in name:
            return redirect('/education/dashboard/')
        
        # Restaurant
        elif 'restaurant' in name or 'food' in name:
            return redirect('/restaurant/dashboard/')
        
        # Retail
        elif 'retail' in name:
            return redirect('/retail/dashboard/')
    
    # Default: General Dashboard
    return redirect('/dashboard/general/')
