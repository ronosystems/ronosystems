from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, Count
from .models import Category, Electronic, Phone, Accessory

@login_required
def category_list(request):
    """List all categories"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    categories = Category.objects.filter(company=company)
    
    # Get counts for stats
    electronics_count = categories.filter(category_type='electronics').count()
    phones_count = categories.filter(category_type='phones').count()
    accessories_count = categories.filter(category_type='accessories').count()
    active_count = categories.filter(is_active=True).count()
    
    context = {
        'categories': categories,
        'electronics_count': electronics_count,
        'phones_count': phones_count,
        'accessories_count': accessories_count,
        'active_count': active_count,
        'page_title': 'Categories',
        'page_subtitle': 'Product categories',
    }
    return render(request, 'epa/categories.html', context)

@login_required
def category_create(request):
    """Create a new category"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_type = request.POST.get('category_type', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Category name is required.')
            return render(request, 'epa/category_form.html', {
                'page_title': 'Add Category',
                'page_subtitle': 'Create a new category',
            })
        
        if not category_type:
            messages.error(request, 'Category type is required.')
            return render(request, 'epa/category_form.html', {
                'page_title': 'Add Category',
                'page_subtitle': 'Create a new category',
            })
        
        # Check if category already exists
        if Category.objects.filter(company=company, name=name).exists():
            messages.error(request, f'Category "{name}" already exists.')
            return render(request, 'epa/category_form.html', {
                'page_title': 'Add Category',
                'page_subtitle': 'Create a new category',
            })
        
        try:
            Category.objects.create(
                company=company,
                name=name,
                category_type=category_type,
                description=description,
                is_active=is_active
            )
            messages.success(request, f'Category "{name}" created successfully!')
            return redirect('epa-categories')
        except Exception as e:
            messages.error(request, f'Error creating category: {str(e)}')
    
    return render(request, 'epa/category_form.html', {
        'page_title': 'Add Category',
        'page_subtitle': 'Create a new category',
    })

@login_required
def category_edit(request, pk):
    """Edit a category"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    category = get_object_or_404(Category, pk=pk, company=company)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_type = request.POST.get('category_type', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        if not name:
            messages.error(request, 'Category name is required.')
            return render(request, 'epa/category_form.html', {
                'category': category,
                'page_title': 'Edit Category',
                'page_subtitle': 'Update category details',
            })
        
        if not category_type:
            messages.error(request, 'Category type is required.')
            return render(request, 'epa/category_form.html', {
                'category': category,
                'page_title': 'Edit Category',
                'page_subtitle': 'Update category details',
            })
        
        # Check if category already exists (excluding current)
        if Category.objects.filter(company=company, name=name).exclude(pk=pk).exists():
            messages.error(request, f'Category "{name}" already exists.')
            return render(request, 'epa/category_form.html', {
                'category': category,
                'page_title': 'Edit Category',
                'page_subtitle': 'Update category details',
            })
        
        try:
            category.name = name
            category.category_type = category_type
            category.description = description
            category.is_active = is_active
            category.save()
            messages.success(request, f'Category "{name}" updated successfully!')
            return redirect('epa-categories')
        except Exception as e:
            messages.error(request, f'Error updating category: {str(e)}')
    
    return render(request, 'epa/category_form.html', {
        'category': category,
        'page_title': 'Edit Category',
        'page_subtitle': 'Update category details',
    })

@login_required
def category_delete(request, pk):
    """Delete a category"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    category = get_object_or_404(Category, pk=pk, company=company)
    
    if request.method == 'POST':
        try:
            category_name = category.name
            category.delete()
            messages.success(request, f'Category "{category_name}" deleted successfully!')
            return redirect('epa-categories')
        except Exception as e:
            messages.error(request, f'Error deleting category: {str(e)}')
    
    context = {
        'category': category,
        'page_title': 'Delete Category',
        'page_subtitle': 'Confirm deletion',
    }
    return render(request, 'epa/category_delete.html', context)

@login_required
def category_products(request, pk):
    """View products in a category"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    category = get_object_or_404(Category, pk=pk, company=company)
    products = []
    
    # Get products based on category type
    if category.category_type == 'phones':
        items = Phone.objects.filter(company=company, category=category, is_active=True)
        for item in items:
            products.append({
                'id': item.id,
                'name': item.name,
                'brand': item.brand,
                'model': item.model,
                'stock': item.quantity_in_stock,
                'price': item.selling_price,
                'type': 'Phone',
                'product_code': item.product_code if item.product_code else f"P{item.id}",
                'has_units': True,
                'has_code': bool(item.product_code),
            })
    elif category.category_type == 'electronics':
        items = Electronic.objects.filter(company=company, category=category, is_active=True)
        for item in items:
            products.append({
                'id': item.id,
                'name': item.name,
                'brand': item.brand,
                'model': item.model_number,
                'stock': item.quantity_in_stock,
                'price': item.selling_price,
                'type': 'Electronic',
                'product_code': item.product_code if item.product_code else f"E{item.id}",
                'has_units': True,
                'has_code': bool(item.product_code),
            })
    elif category.category_type == 'accessories':
        items = Accessory.objects.filter(company=company, category=category, is_active=True)
        for item in items:
            products.append({
                'id': item.id,
                'name': item.name,
                'brand': item.brand,
                'model': item.model,
                'stock': item.quantity_in_stock,
                'price': item.selling_price,
                'type': 'Accessory',
                'product_code': item.product_code if item.product_code else f"A{item.id}",
                'has_units': False,
                'has_code': bool(item.product_code),
            })
    
    # Sort by name
    products.sort(key=lambda x: x['name'])
    
    context = {
        'category': category,
        'products': products,
        'total_count': len(products),
        'page_title': f'Products in {category.name}',
        'page_subtitle': 'Category products',
    }
    return render(request, 'epa/category_products.html', context)


@login_required
def category_toggle_status(request, pk):
    """Toggle category active status"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    category = get_object_or_404(Category, pk=pk, company=company)
    
    if request.method == 'POST':
        category.is_active = not category.is_active
        category.save()
        status = 'activated' if category.is_active else 'deactivated'
        messages.success(request, f'Category "{category.name}" has been {status}.')
        return redirect('epa-categories')
    
    return redirect('epa-categories')