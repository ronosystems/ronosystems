# apps/accounts/join_company.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from apps.companies.models import Company, CompanyJoinRequest

User = get_user_model()

def join_company(request):
    """
    Public portal for a new user to request to join a company.
    """
    company_id = request.GET.get('company_id') or request.POST.get('company_id')
    company = Company.objects.filter(id=company_id).first() if company_id else None

    if request.method == 'POST':
        # --- Collect fields ---
        full_names  = (request.POST.get('full_names') or '').strip()
        phone       = (request.POST.get('phone') or '').strip()
        id_number   = (request.POST.get('id_number') or '').strip() # Kept for validation, but model doesn't have a field for it
        email       = (request.POST.get('email') or '').strip().lower()
        password    = request.POST.get('password') or ''
        pw_confirm  = request.POST.get('password_confirm') or ''
        accept_pol  = request.POST.get('accept_policy') == 'on'
        accept_trm  = request.POST.get('accept_terms') == 'on'

        errors = []

        # --- Find company if missing from URL ---
        if not company:
            code = (request.POST.get('code') or '').strip().upper()
            company = Company.objects.filter(company_id__iexact=code).first()
            if not company:
                errors.append('Invalid company code.')

        # --- Validation ---
        if not full_names:
            errors.append('Full names are required.')
        if not phone:
            errors.append('Phone number is required.')
        if not id_number:
            errors.append('ID number is required.')
        
        try:
            validate_email(email)
        except ValidationError:
            errors.append('Please enter a valid email address.')

        # Check if email already exists in User OR JoinRequest
        if User.objects.filter(email=email).exists():
            errors.append('An account with this email already exists.')
        elif company and CompanyJoinRequest.objects.filter(company=company, email=email).exists():
            errors.append('You have already requested to join this company.')

        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != pw_confirm:
            errors.append('Passwords do not match.')
        if not accept_pol:
            errors.append('You must accept the Privacy Policy.')
        if not accept_trm:
            errors.append('You must accept the Terms of Service.')

        # --- Handle Errors ---
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'account/join_company.html', {'company': company})

        # --- Create Join Request (No User created yet!) ---
        name_parts = full_names.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        try:
            CompanyJoinRequest.objects.create(
                company=company,
                first_name=first_name,
                last_name=last_name,
                username=email,               # Using email as username
                email=email,
                phone=phone,                  # ✅ SAVING PHONE HERE
                password_hash=make_password(password), # ✅ SAVING HASHED PASSWORD
                requested_role='company_staff',
                status='pending',
            )

            messages.success(request, f'Registration successful! Request sent to {company.display_name}. Please wait for approval.')
            
            # Redirect to login page
            return redirect('/auth/login/') 

        except Exception as e:
            messages.error(request, f'An error occurred during registration: {e}')
            return render(request, 'account/join_company.html', {'company': company})

    return render(request, 'account/join_company.html', {'company': company})