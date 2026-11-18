from django.shortcuts import render


def no_access(request):
    """Page shown to guests without a company — tells them to contact support."""
    return render(request, 'accounts/no_access.html')



from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from apps.companies.models import CompanyApplication

def apply_company(request):
    """
    Multi-step form to apply for a new company account.
    """
    if request.method == 'POST':
        # Collect all data from the form (hidden fields carry data across steps)
        company_name = request.POST.get('company_name')
        company_pin = request.POST.get('company_pin')
        company_email = request.POST.get('company_email')
        company_phone = request.POST.get('company_phone')
        company_website = request.POST.get('company_website', '')

        address = request.POST.get('address')
        city = request.POST.get('city')
        state = request.POST.get('state')
        country = request.POST.get('country')
        postal_code = request.POST.get('postal_code', '')

        admin_first_name = request.POST.get('admin_first_name')
        admin_last_name = request.POST.get('admin_last_name')
        admin_email = request.POST.get('admin_email')
        admin_phone = request.POST.get('admin_phone')
        admin_id_number = request.POST.get('admin_id_number', '')

        password = request.POST.get('password')
        pw_confirm = request.POST.get('password_confirm')

        # Validation
        if password != pw_confirm:
            messages.error(request, "Passwords do not match.")
            return render(request, 'account/apply_company.html', {'post_data': request.POST})

        if CompanyApplication.objects.filter(admin_email=admin_email).exists():
            messages.error(request, "An application with this email already exists.")
            return render(request, 'account/apply_company.html', {'post_data': request.POST})

        # Create the Pending Application
        CompanyApplication.objects.create(
            company_name=company_name,
            company_pin=company_pin,
            company_email=company_email,
            company_phone=company_phone,
            company_website=company_website,
            address=address,
            city=city,
            state=state,
            country=country,
            postal_code=postal_code,
            admin_first_name=admin_first_name,
            admin_last_name=admin_last_name,
            admin_email=admin_email,
            admin_phone=admin_phone,
            admin_id_number=admin_id_number,
            password_hash=make_password(password),
            status='pending'
        )

        messages.success(request, "Application submitted successfully! Our team will review it and contact you shortly.")
        return redirect('account_login')

    return render(request, 'account/apply_company.html')