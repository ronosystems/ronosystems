from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from apps.companies.models import BusinessType
from apps.business_types.business_type_registry import BusinessTypeEnum

@login_required
@staff_member_required
def business_type_list(request):
    """List all business types"""
    business_types = BusinessType.objects.all().order_by('name')
    
    context = {
        'business_types': business_types,
        'page_title': 'Business Types',
        'page_subtitle': 'Manage business types',
    }
    return render(request, 'business_types/list.html', context)

@login_required
@staff_member_required
def business_type_create(request):
    """Create a new business type"""
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        icon = request.POST.get('icon', '')
        
        # Validate against registry
        if not BusinessTypeEnum.validate_name(name):
            valid_names = ', '.join(BusinessTypeEnum.get_all_names())
            messages.error(request, f'Invalid business type. Must be one of: {valid_names}')
            return render(request, 'business_types/create.html', {
                'available_types': BusinessTypeEnum.get_all_active()
            })
        
        # Check if exists
        if BusinessType.objects.filter(name=name).exists():
            messages.error(request, f'Business type "{name}" already exists.')
            return render(request, 'business_types/create.html', {
                'available_types': BusinessTypeEnum.get_all_active()
            })
        
        # Create
        try:
            BusinessType.objects.create(
                name=name,
                description=description,
                icon=icon,
                is_active=True
            )
            messages.success(request, f'Business type "{name}" created successfully!')
            return redirect('/business-types/')
        except Exception as e:
            messages.error(request, f'Error creating business type: {str(e)}')
    
    context = {
        'available_types': BusinessTypeEnum.get_all_active(),
        'page_title': 'Create Business Type',
        'page_subtitle': 'Add a new business type',
    }
    return render(request, 'business_types/create.html', context)

@login_required
@staff_member_required
def business_type_edit(request, pk):
    """Edit an existing business type"""
    
    business_type = get_object_or_404(BusinessType, pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        icon = request.POST.get('icon', '')
        is_active = request.POST.get('is_active') == 'on'
        
        # Validate against registry
        if not BusinessTypeEnum.validate_name(name):
            valid_names = ', '.join(BusinessTypeEnum.get_all_names())
            messages.error(request, f'Invalid business type. Must be one of: {valid_names}')
            return render(request, 'business_types/edit.html', {
                'business_type': business_type,
                'available_types': BusinessTypeEnum.get_all_active()
            })
        
        # Update
        try:
            business_type.name = name
            business_type.description = description
            business_type.icon = icon
            business_type.is_active = is_active
            business_type.save()
            
            messages.success(request, f'Business type "{name}" updated successfully!')
            return redirect('/business-types/')
        except Exception as e:
            messages.error(request, f'Error updating business type: {str(e)}')
    
    context = {
        'business_type': business_type,
        'available_types': BusinessTypeEnum.get_all_active(),
        'page_title': 'Edit Business Type',
        'page_subtitle': f'Editing {business_type.name}',
    }
    return render(request, 'business_types/edit.html', context)

@login_required
@staff_member_required
def business_type_delete(request, pk):
    """Delete a business type"""
    
    business_type = get_object_or_404(BusinessType, pk=pk)
    
    if request.method == 'POST':
        try:
            name = business_type.name
            business_type.delete()
            messages.success(request, f'Business type "{name}" deleted successfully!')
            return redirect('/business-types/')
        except Exception as e:
            messages.error(request, f'Error deleting business type: {str(e)}')
    
    context = {
        'business_type': business_type,
        'page_title': 'Delete Business Type',
        'page_subtitle': f'Confirm deletion of {business_type.name}',
    }
    return render(request, 'business_types/delete.html', context)
