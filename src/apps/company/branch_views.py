from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.epa_shop.models import Branch
from apps.companies.models import Company
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)


@login_required
def branch_list(request):
    """List all branches for the user's company"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branches = Branch.objects.filter(company=company).order_by('name')
    
    context = {
        'company': company,
        'branches': branches,
        'total_count': branches.count(),
        'is_viewing_company': is_viewing_company,
        'page_title': 'Branches',
        'page_subtitle': 'Manage your branches',
    }
    return render(request, 'company/branches/list.html', context)


@login_required
def branch_create(request):
    """Create a new branch"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        country = request.POST.get('country', '').strip()
        currency = request.POST.get('currency', 'KES')
        currency_symbol = request.POST.get('currency_symbol', 'KSh')
        
        if not name:
            messages.error(request, 'Branch name is required.')
            return render(request, 'company/branch_form.html', {
                'branch': None,
                'company': company,
                'is_viewing_company': is_viewing_company,
                'page_title': 'Create Branch',
                'page_subtitle': 'Add a new branch'
            })
        
        try:
            branch = Branch.objects.create(
                company=company,
                name=name,
                code=code or name[:3].upper(),
                address=address,
                phone=phone,
                email=email,
                city=city,
                country=country,
                is_active=True,
                currency=currency,
                currency_symbol=currency_symbol
            )
            messages.success(request, f'Branch "{name}" created successfully!')
            return redirect('/company/branches/')
        except Exception as e:
            messages.error(request, f'Error creating branch: {str(e)}')
    
    context = {
        'branch': None,
        'company': company,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Create Branch',
        'page_subtitle': 'Add a new branch',
    }
    return render(request, 'company/branches/form.html', context)


@login_required
def branch_edit(request, pk):
    """Edit a branch"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch = get_object_or_404(Branch, pk=pk, company=company)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        country = request.POST.get('country', '').strip()
        currency = request.POST.get('currency', 'KES')
        currency_symbol = request.POST.get('currency_symbol', 'KSh')
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Branch name is required.')
            return render(request, 'company/branch_form.html', {
                'branch': branch,
                'company': company,
                'is_viewing_company': is_viewing_company,
                'page_title': 'Edit Branch',
                'page_subtitle': f'Editing {branch.name}'
            })
        
        try:
            branch.name = name
            branch.code = code or name[:3].upper()
            branch.address = address
            branch.phone = phone
            branch.email = email
            branch.city = city
            branch.country = country
            branch.currency = currency
            branch.currency_symbol = currency_symbol
            branch.is_active = is_active
            branch.save()
            
            messages.success(request, f'Branch "{name}" updated successfully!')
            return redirect('/company/branches/')
        except Exception as e:
            messages.error(request, f'Error updating branch: {str(e)}')
    
    context = {
        'branch': branch,
        'company': company,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Edit Branch',
        'page_subtitle': f'Editing {branch.name}',
    }
    return render(request, 'company/branches/form.html', context)


@login_required
def branch_delete(request, pk):
    """Delete a branch"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch = get_object_or_404(Branch, pk=pk, company=company)
    
    if request.method == 'POST':
        try:
            name = branch.name
            branch.delete()
            messages.success(request, f'Branch "{name}" deleted successfully!')
            return redirect('/company/branches/')
        except Exception as e:
            messages.error(request, f'Error deleting branch: {str(e)}')
    
    context = {
        'branch': branch,
        'company': company,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Delete Branch',
        'page_subtitle': f'Confirm deletion of {branch.name}',
    }
    return render(request, 'company/branches/delete.html', context)