# /home/rs/ronosystems/src/apps/epa_shop/customer_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Value, Q
from django.db.models.functions import Coalesce
from decimal import Decimal
import cloudinary
import cloudinary.uploader
from django.conf import settings

# Import the global Customer model and the EPA Shop Sale model
from apps.customers.models import Customer
from apps.epa_shop.models import Sale
from apps.companies.support_utils import get_active_company

# ============================================
# HELPER: Role check (mirrors product helpers)
# ============================================
def can_manage_customers(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) in [
        'super_admin', 'company_admin', 'company_manager', 'stock_controller'
    ]

# ============================================
# HELPER: Cloudinary Upload
# ============================================
def _upload_customer_file(uploaded_file, folder='epa_shop/customers/kyc'):
    """Uploads a KYC document to Cloudinary and returns the public_id."""
    if not uploaded_file:
        return None
    try:
        cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
        cloudinary.config(
            cloud_name=cfg.get('CLOUD_NAME', ''),
            api_key=cfg.get('API_KEY', ''),
            api_secret=cfg.get('API_SECRET', ''),
            secure=True,
        )
        result = cloudinary.uploader.upload(
            uploaded_file,
            folder=folder,
            resource_type='image'
        )
        return result.get('public_id')
    except Exception as e:
        print(f"❌ Cloudinary upload failed: {e}")
        return None

# ============================================
# CUSTOMER LIST
# ============================================
@login_required
def customer_list(request):
    """List all customers for the active company with sales totals."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_viewing_company and not can_manage_customers(request.user):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('/no-access/')

    # Annotate the total amount they have spent in the EPA shop
    customers = Customer.objects.filter(company=company).annotate(
        total_spent=Coalesce(Sum('epa_sales__net_amount'), Value(Decimal('0.00')))
    ).order_by('-created_at')

    search_query = request.GET.get('q', '').strip()
    if search_query:
        customers = customers.filter(
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(national_id__icontains=search_query) |
            Q(location__icontains=search_query)
        )

    context = {
        'company': company,
        'customers': customers,
        'search_query': search_query,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Customers',
        'page_subtitle': f'Manage customers for {company.name}',
    }
    return render(request, 'epa_shop/customers/list.html', context)

# ============================================
# CUSTOMER CREATE
# ============================================
@login_required
def customer_create(request):
    """Create a new customer for the active company."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_viewing_company and not can_manage_customers(request.user):
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('/no-access/')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()
        national_id = request.POST.get('national_id', '').strip()
        location = request.POST.get('location', '').strip()

        if not full_name or not phone_number:
            messages.error(request, "Full Name and Phone Number are required.")
        elif Customer.objects.filter(company=company, phone_number=phone_number).exists():
            messages.error(request, f"A customer with phone number {phone_number} already exists in this company.")
        else:
            # Process File Uploads
            id_front_file = request.FILES.get('id_front')
            id_back_file = request.FILES.get('id_back')
            profile_photo_file = request.FILES.get('profile_photo')

            id_front_id = _upload_customer_file(id_front_file) if id_front_file else None
            id_back_id = _upload_customer_file(id_back_file) if id_back_file else None
            profile_photo_id = _upload_customer_file(profile_photo_file) if profile_photo_file else None

            # Create Customer
            Customer.objects.create(
                company=company,
                full_name=full_name,
                phone_number=phone_number,
                email=email,
                national_id=national_id,
                location=location,
                id_front=id_front_id,
                id_back=id_back_id,
                profile_photo=profile_photo_id,
            )
            messages.success(request, f"Customer '{full_name}' created successfully.")
            return redirect('epa_shop:customer-list')

    return render(request, 'epa_shop/customers/form.html', {
        'company': company,
        'is_edit': False,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Add Customer',
        'page_subtitle': f'Create a new customer for {company.name}',
    })

# ============================================
# CUSTOMER UPDATE
# ============================================
@login_required
def customer_update(request, pk):
    """Update an existing customer."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_viewing_company and not can_manage_customers(request.user):
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('/no-access/')

    customer = get_object_or_404(Customer, pk=pk, company=company)

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()
        national_id = request.POST.get('national_id', '').strip()
        location = request.POST.get('location', '').strip()

        if not full_name or not phone_number:
            messages.error(request, "Full Name and Phone Number are required.")
        elif Customer.objects.filter(company=company, phone_number=phone_number).exclude(pk=pk).exists():
            messages.error(request, f"A customer with phone number {phone_number} already exists in this company.")
        else:
            # Update text fields
            customer.full_name = full_name
            customer.phone_number = phone_number
            customer.email = email
            customer.national_id = national_id
            customer.location = location

            # Process File Uploads (only update if a new file was provided)
            if request.FILES.get('id_front'):
                customer.id_front = _upload_customer_file(request.FILES['id_front'])
            
            if request.FILES.get('id_back'):
                customer.id_back = _upload_customer_file(request.FILES['id_back'])
            
            if request.FILES.get('profile_photo'):
                customer.profile_photo = _upload_customer_file(request.FILES['profile_photo'])

            customer.save()
            messages.success(request, f"Customer '{full_name}' updated successfully.")
            return redirect('epa_shop:customer-list')

    return render(request, 'epa_shop/customers/form.html', {
        'company': company,
        'customer': customer,
        'is_edit': True,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Edit Customer',
        'page_subtitle': f'Editing {customer.full_name}',
    })

# ============================================
# CUSTOMER DELETE
# ============================================
@login_required
def customer_delete(request, pk):
    """Delete a customer."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_viewing_company and not can_manage_customers(request.user):
        messages.error(request, "You don't have permission to perform this action.")
        return redirect('/no-access/')

    customer = get_object_or_404(Customer, pk=pk, company=company)

    if request.method == 'POST':
        name = customer.full_name
        customer.delete()
        messages.success(request, f"Customer '{name}' has been deleted.")
        return redirect('epa_shop:customer-list')

    return render(request, 'epa_shop/customers/delete.html', {
        'company': company,
        'customer': customer,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Delete Customer',
        'page_subtitle': f'Are you sure you want to delete {customer.full_name}?',
    })

# ============================================
# CUSTOMER DETAIL
# ============================================
@login_required
def customer_detail(request, pk):
    """View a single customer's profile and purchase history."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_viewing_company and not can_manage_customers(request.user):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('/no-access/')
        
    customer = get_object_or_404(Customer, pk=pk, company=company)
    
    # Fetch their recent sales from the EPA Shop Sale model
    recent_sales = Sale.objects.filter(customer=customer, company=company).order_by('-sale_date')[:10]

    return render(request, 'epa_shop/customers/detail.html', {
        'customer': customer,
        'recent_sales': recent_sales,
        'is_viewing_company': is_viewing_company,
        'page_title': f'Customer: {customer.full_name}',
        'page_subtitle': f'Joined on {customer.created_at.strftime("%Y-%m-%d")}',
    })