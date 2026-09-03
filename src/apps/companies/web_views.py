from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .models import Company, BusinessType
from apps.plans.models import Plan
from django.db.models import Count

@login_required
@staff_member_required
def company_list(request):
    """List all companies with plan details"""
    companies = Company.objects.all().order_by('-created_at')
    
    # Get stats
    total_companies = companies.count()
    active_companies = companies.filter(is_active=True).count()
    
    # Get all plans for lookup
    plans = {plan.name: plan for plan in Plan.objects.all()}
    
    # Annotate companies with plan details
    for company in companies:
        company.plan_details = plans.get(company.plan)
    
    context = {
        'companies': companies,
        'total_companies': total_companies,
        'active_companies': active_companies,
        'plans': plans,
        'page_title': 'Companies',
        'page_subtitle': 'Manage all companies',
    }
    return render(request, 'companies/list.html', context)

@login_required
@staff_member_required
def company_create(request):
    """Create a new company"""
    business_types = BusinessType.objects.filter(is_active=True)
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        business_type_id = request.POST.get('business_type')
        registration_number = request.POST.get('registration_number', '')
        address = request.POST.get('address', '')
        city = request.POST.get('city', '')
        state = request.POST.get('state', '')
        country = request.POST.get('country', '')
        postal_code = request.POST.get('postal_code', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        website = request.POST.get('website', '')
        plan_name = request.POST.get('plan', 'free')
        
        # Validate
        if not name:
            messages.error(request, 'Company name is required.')
            return render(request, 'companies/create.html', {
                'business_types': business_types,
                'plans': plans
            })
        
        # Create company
        try:
            company = Company.objects.create(
                name=name,
                business_type_id=business_type_id or None,
                registration_number=registration_number,
                address=address,
                city=city,
                state=state,
                country=country,
                postal_code=postal_code,
                email=email,
                phone=phone,
                website=website,
                plan=plan_name,
                created_by=request.user,
                is_active=True
            )
            messages.success(request, f'Company "{name}" created successfully!')
            return redirect('/companies/')
        except Exception as e:
            messages.error(request, f'Error creating company: {str(e)}')
    
    context = {
        'business_types': business_types,
        'plans': plans,
        'page_title': 'Create Company',
        'page_subtitle': 'Add a new company',
    }
    return render(request, 'companies/create.html', context)

@login_required
@staff_member_required
def company_detail(request, pk):
    """View company details"""
    company = get_object_or_404(Company, pk=pk)
    
    # Get employee count
    employee_count = company.users.count()
    
    # Get plan details
    plan_details = None
    try:
        plan_details = Plan.objects.get(name=company.plan)
    except Plan.DoesNotExist:
        pass
    
    context = {
        'company': company,
        'employee_count': employee_count,
        'plan_details': plan_details,
        'page_title': company.name,
        'page_subtitle': 'Company details',
    }
    return render(request, 'companies/detail.html', context)

@login_required
@staff_member_required
def company_edit(request, pk):
    """Edit a company"""
    company = get_object_or_404(Company, pk=pk)
    business_types = BusinessType.objects.filter(is_active=True)
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        business_type_id = request.POST.get('business_type')
        registration_number = request.POST.get('registration_number', '')
        address = request.POST.get('address', '')
        city = request.POST.get('city', '')
        state = request.POST.get('state', '')
        country = request.POST.get('country', '')
        postal_code = request.POST.get('postal_code', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        website = request.POST.get('website', '')
        plan_name = request.POST.get('plan', 'free')
        is_active = request.POST.get('is_active') == 'on'
        
        # Validate
        if not name:
            messages.error(request, 'Company name is required.')
            return render(request, 'companies/edit.html', {
                'company': company,
                'business_types': business_types,
                'plans': plans
            })
        
        # Update company
        try:
            company.name = name
            company.business_type_id = business_type_id or None
            company.registration_number = registration_number
            company.address = address
            company.city = city
            company.state = state
            company.country = country
            company.postal_code = postal_code
            company.email = email
            company.phone = phone
            company.website = website
            company.plan = plan_name
            company.is_active = is_active
            company.save()
            
            messages.success(request, f'Company "{name}" updated successfully!')
            return redirect('/companies/')
        except Exception as e:
            messages.error(request, f'Error updating company: {str(e)}')
    
    context = {
        'company': company,
        'business_types': business_types,
        'plans': plans,
        'page_title': 'Edit Company',
        'page_subtitle': f'Editing {company.name}',
    }
    return render(request, 'companies/edit.html', context)

@login_required
@staff_member_required
def company_delete(request, pk):
    """Delete a company"""
    company = get_object_or_404(Company, pk=pk)
    
    if request.method == 'POST':
        try:
            name = company.name
            company.delete()
            messages.success(request, f'Company "{name}" deleted successfully!')
            return redirect('/companies/')
        except Exception as e:
            messages.error(request, f'Error deleting company: {str(e)}')
    
    context = {
        'company': company,
        'page_title': 'Delete Company',
        'page_subtitle': f'Confirm deletion of {company.name}',
    }
    return render(request, 'companies/delete.html', context)
