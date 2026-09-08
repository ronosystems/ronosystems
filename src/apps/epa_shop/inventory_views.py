from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from .models import (
    Electronic, Phone, Accessory, Category, 
    Sale, SaleItem, Customer, StockMovement, Supplier
)


@login_required
def inventory_list(request):
    """Main inventory page showing all products"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Get all products
    electronics = Electronic.objects.filter(company=company, is_active=True)
    phones = Phone.objects.filter(company=company, is_active=True)
    accessories = Accessory.objects.filter(company=company, is_active=True)
    
    # Calculate stock counts
    electronics_stock = electronics.aggregate(total=Sum('quantity_in_stock'))['total'] or 0
    phones_stock = phones.aggregate(total=Sum('quantity_in_stock'))['total'] or 0
    accessories_stock = accessories.aggregate(total=Sum('quantity_in_stock'))['total'] or 0
    
    electronics_count = electronics.count()
    phones_count = phones.count()
    accessories_count = accessories.count()
    
    total_products = electronics_count + phones_count + accessories_count
    total_stock = electronics_stock + phones_stock + accessories_stock
    
    # Low stock items
    low_stock_items = []
    
    # Electronics with low stock
    for item in electronics.filter(quantity_in_stock__lte=5):
        low_stock_items.append({
            'id': item.id,
            'name': f"{item.name}",
            'brand': f"{item.brand}",
            'model': f"{item.model_number}",
            'type': 'Electronic',
            'quantity': item.quantity_in_stock,
            'min_stock': item.minimum_stock_level,
            'price': item.selling_price,
            'product_code': item.product_code or '-'
        })
    
    # Phones with low stock
    for item in phones.filter(quantity_in_stock__lte=5):
        low_stock_items.append({
            'id': item.id,
            'name': f"{item.name}",
            'brand': f"{item.brand}",
            'model': f"{item.model}",
            'type': 'Phone',
            'quantity': item.quantity_in_stock,
            'min_stock': item.minimum_stock_level,
            'price': item.selling_price,
            'product_code': item.product_code or '-'
        })
    
    # Accessories with low stock (threshold 10 for accessories)
    for item in accessories.filter(quantity_in_stock__lte=10):
        low_stock_items.append({
            'id': item.id,
            'name': f"{item.name}",
            'brand': f"{item.brand}",
            'model': f"{item.model}",
            'type': 'Accessory',
            'quantity': item.quantity_in_stock,
            'min_stock': item.minimum_stock_level,
            'price': item.selling_price,
            'product_code': item.product_code or '-'
        })
    
    # Sort low stock items by quantity (lowest first)
    low_stock_items.sort(key=lambda x: x['quantity'])
    
    context = {
        'total_products': total_products,
        'total_stock': total_stock,
        'electronics_count': electronics_count,
        'phones_count': phones_count,
        'accessories_count': accessories_count,
        'low_stock_count': len(low_stock_items),
        'low_stock_items': low_stock_items[:10],  # Show only top 10
        'page_title': 'Inventory',
        'page_subtitle': 'Manage your stock',
    }
    return render(request, 'epa/inventory.html', context)


@login_required
def low_stock(request):
    """View all low stock items with filters and pagination"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    low_stock_items = []
    
    # Electronics with low stock
    for item in Electronic.objects.filter(company=company, is_active=True):
        if item.quantity_in_stock <= item.minimum_stock_level:
            low_stock_items.append({
                'id': item.id,
                'product_code': item.product_code or '-',
                'name': item.name,
                'type': 'Electronic',
                'brand': item.brand or '-',
                'model': item.model_number or '-',
                'specs': f"{item.ram} {item.storage}".strip() or '-',
                'quantity': item.quantity_in_stock,
                'min_stock': item.minimum_stock_level,
                'price': item.selling_price,
                'purchase_price': item.purchase_price,
                'sku': item.model_number or '-',
                'is_active': item.is_active,
                'created_at': item.created_at,
            })
    
    # Phones with low stock
    for item in Phone.objects.filter(company=company, is_active=True):
        if item.quantity_in_stock <= item.minimum_stock_level:
            low_stock_items.append({
                'id': item.id,
                'product_code': item.product_code or '-',
                'name': item.name,
                'type': 'Phone',
                'brand': item.brand or '-',
                'model': item.model or '-',
                'specs': f"{item.ram} {item.storage_capacity}".strip() or '-',
                'quantity': item.quantity_in_stock,
                'min_stock': item.minimum_stock_level,
                'price': item.selling_price,
                'purchase_price': item.purchase_price,
                'sku': item.imei or '-',
                'is_active': item.is_active,
                'created_at': item.created_at,
            })
    
    # Accessories with low stock
    for item in Accessory.objects.filter(company=company, is_active=True):
        if item.quantity_in_stock <= item.minimum_stock_level:
            low_stock_items.append({
                'id': item.id,
                'product_code': item.product_code or '-',
                'name': item.name,
                'type': 'Accessory',
                'brand': item.brand or '-',
                'model': item.model or '-',
                'specs': item.accessory_type or '-',
                'quantity': item.quantity_in_stock,
                'min_stock': item.minimum_stock_level,
                'price': item.selling_price,
                'purchase_price': item.purchase_price,
                'sku': item.model or '-',
                'is_active': item.is_active,
                'created_at': item.created_at,
            })
    
    # Apply search filter
    search_query = request.GET.get('search', '')
    if search_query:
        search_lower = search_query.lower()
        low_stock_items = [i for i in low_stock_items if 
                          search_lower in i['name'].lower() or 
                          search_lower in i['brand'].lower() or
                          search_lower in i['model'].lower() or
                          search_lower in i['product_code'].lower()]
    
    # Apply category filter
    category_filter = request.GET.get('category', '')
    if category_filter:
        low_stock_items = [i for i in low_stock_items if i['type'] == category_filter]
    
    # Apply stock level filter
    stock_filter = request.GET.get('stock', '')
    if stock_filter:
        if stock_filter == 'critical':
            low_stock_items = [i for i in low_stock_items if i['quantity'] <= 0]
        elif stock_filter == 'low':
            low_stock_items = [i for i in low_stock_items if 1 <= i['quantity'] <= 5]
        elif stock_filter == 'medium':
            low_stock_items = [i for i in low_stock_items if 6 <= i['quantity'] <= 10]
    
    # Sort by quantity (lowest first)
    low_stock_items.sort(key=lambda x: x['quantity'])
    
    # Pagination
    per_page = int(request.GET.get('per_page', 10))
    paginator = Paginator(low_stock_items, per_page)
    page = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    context = {
        'page_obj': page_obj,
        'total_count': len(low_stock_items),
        'search_query': search_query,
        'category_filter': category_filter,
        'stock_filter': stock_filter,
        'per_page': per_page,
        'page_title': 'Low Stock Items',
        'page_subtitle': 'Items that need restocking',
    }
    return render(request, 'epa/low_stock.html', context)


@login_required
def stock_movement(request):
    """View stock movement history with pagination and filters"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    movements = StockMovement.objects.filter(company=company).order_by('-created_at')
    
    # Apply filters
    movement_type = request.GET.get('type', '')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    
    # Search by product name
    search_query = request.GET.get('search', '')
    if search_query:
        # We need to filter by product name using the generic relation
        # This is a simplified approach - you may need to adjust
        pass
    
    # Pagination
    per_page = int(request.GET.get('per_page', 20))
    paginator = Paginator(movements, per_page)
    page = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    context = {
        'page_obj': page_obj,
        'movements': page_obj.object_list,
        'total_count': movements.count(),
        'search_query': search_query,
        'movement_type': movement_type,
        'per_page': per_page,
        'page_title': 'Stock Movements',
        'page_subtitle': 'Inventory transaction history',
    }
    return render(request, 'epa/stock_movement.html', context)


@login_required
def customer_list(request):
    """List all customers"""
    company = request.user.company
    
    if not company:
        return redirect('/dashboard/')
    
    customers = Customer.objects.filter(company=company).order_by('-created_at')[:50]
    
    context = {
        'customers': customers,
        'total_count': customers.count(),
        'page_title': 'Customers',
        'page_subtitle': 'Customer management',
    }
    return render(request, 'epa/customers.html', context)


@login_required
def customer_create(request):
    """Create a new customer"""
    # Placeholder
    messages.info(request, 'Customer creation coming soon.')
    return redirect('/epa/customers/')
