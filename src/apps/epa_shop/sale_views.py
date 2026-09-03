# apps/epa_shop/sale_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from .models import Phone, Electronic, Accessory, Category, Branch, Unit, Sale, SaleItem, Customer, Owner
from django.contrib.contenttypes.models import ContentType
from django.db import models
from .utils import record_stock_movement
from decimal import Decimal
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json




# ============================================
# HELPER FUNCTION - User Role Checks
# ============================================

def is_admin_or_manager(user):
    """Check if user is admin, manager, or super admin"""
    return user.role in ['super_admin', 'company_admin', 'company_manager']


def get_user_branch(user):
    """Get the user's branch"""
    return user.branch if user else None


# ============================================
# PROCESS SALE
# ============================================
@login_required
def process_sale(request):
    """Process a sale from the POS using product_code"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    try:
        data = json.loads(request.body)
        branch_id = data.get('branch_id')
        customer_name = data.get('customer_name', 'Walk-in Customer')
        customer_phone = data.get('customer_phone', '')
        customer_email = data.get('customer_email', '')
        items = data.get('items', [])
        
        if not branch_id:
            return JsonResponse({'error': 'Branch is required'}, status=400)
        
        if not items:
            return JsonResponse({'error': 'No items in cart'}, status=400)
        
        branch = Branch.objects.filter(id=branch_id, company=company).first()
        if not branch:
            return JsonResponse({'error': 'Branch not found'}, status=404)
        
        # Create customer if phone exists
        customer = None
        if customer_phone:
            customer = Customer.objects.filter(phone=customer_phone, company=company).first()
            if not customer:
                customer = Customer.objects.create(
                    company=company,
                    name=customer_name,
                    phone=customer_phone,
                    email=customer_email,
                    is_active=True
                )
        
        # Start transaction
        with transaction.atomic():
            # Calculate totals
            subtotal = 0
            sale_items_data = []
            
            for item in items:
                product_code = item.get('product_code')
                quantity = item.get('quantity', 1)
                price = item.get('price', 0)
                unit_identifier = item.get('unit_identifier')
                
                if not product_code:
                    return JsonResponse({'error': 'Product code is required'}, status=400)
                
                # Find product by product_code across all models
                product = None
                product_name = ''
                sku = ''
                category_type = ''
                
                # Try Phone
                try:
                    product = Phone.objects.get(company=company, product_code=product_code)
                    category_type = 'Phone'
                    sku = product.model or ''
                except Phone.DoesNotExist:
                    pass
                
                # Try Electronic
                if not product:
                    try:
                        product = Electronic.objects.get(company=company, product_code=product_code)
                        category_type = 'Electronic'
                        sku = product.model_number or ''
                    except Electronic.DoesNotExist:
                        pass
                
                # Try Accessory
                if not product:
                    try:
                        product = Accessory.objects.get(company=company, product_code=product_code)
                        category_type = 'Accessory'
                        sku = product.model or ''
                    except Accessory.DoesNotExist:
                        pass
                
                if not product:
                    return JsonResponse({'error': f'Product with code "{product_code}" not found'}, status=404)
                
                product_name = product.name
                subtotal += price * quantity
                
                # Handle stock/units based on product type
                previous_quantity = product.quantity_in_stock
                unit = None
                
                if category_type == 'Phone':
                    # For phones: update units if specified
                    if unit_identifier:
                        unit = Unit.objects.filter(
                            phone=product, 
                            identifier=unit_identifier, 
                            status='available'
                        ).first()
                        if unit:
                            unit.status = 'sold'
                            unit.sold_date = timezone.now()
                            unit.owner_name = customer_name
                            unit.owner_phone = customer_phone
                            unit.save()
                        else:
                            return JsonResponse({'error': f'IMEI "{unit_identifier}" not available'}, status=400)
                    
                    # Reduce stock
                    product.quantity_in_stock -= quantity
                    product.save()
                    
                elif category_type == 'Electronic':
                    # For electronics: update units if specified
                    if unit_identifier:
                        unit = Unit.objects.filter(
                            electronic=product, 
                            identifier=unit_identifier, 
                            status='available'
                        ).first()
                        if unit:
                            unit.status = 'sold'
                            unit.sold_date = timezone.now()
                            unit.owner_name = customer_name
                            unit.owner_phone = customer_phone
                            unit.save()
                        else:
                            return JsonResponse({'error': f'Serial "{unit_identifier}" not available'}, status=400)
                    
                    # Reduce stock
                    product.quantity_in_stock -= quantity
                    product.save()
                    
                elif category_type == 'Accessory':
                    # For accessories: reduce stock by quantity
                    if product.quantity_in_stock < quantity:
                        return JsonResponse({
                            'error': f'Insufficient stock for "{product_name}". Available: {product.quantity_in_stock}'
                        }, status=400)
                    
                    product.quantity_in_stock -= quantity
                    product.save()
                
                # Record stock movement for sale
                record_stock_movement(
                    product=product,
                    movement_type='sale',
                    quantity=-quantity,
                    previous_quantity=previous_quantity,
                    new_quantity=product.quantity_in_stock,
                    branch=branch,
                    unit=unit,
                    notes=f"Sale - {customer_name}",
                    performed_by=request.user
                )
                
                # Store sale item data for later
                sale_items_data.append({
                    'product': product,
                    'product_code': product_code,
                    'product_name': product_name,
                    'sku': sku,
                    'category_type': category_type,
                    'quantity': quantity,
                    'unit_price': price,
                    'total_price': price * quantity,
                    'unit_identifier': unit_identifier
                })
            
            # Create sale
            sale = Sale.objects.create(
                company=company,
                branch=branch,
                customer=customer,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                total_amount=subtotal,
                discount=0,
                tax=0,
                net_amount=subtotal,
                payment_status='paid',
                payment_method=data.get('payment_method', 'cash'),
                sold_by=request.user,
                sale_date=timezone.now()
            )
            
            # Create sale items
            for item_data in sale_items_data:
                product = item_data['product']
                
                # Get content type for generic foreign key
                if isinstance(product, Phone):
                    content_type = ContentType.objects.get_for_model(Phone)
                elif isinstance(product, Electronic):
                    content_type = ContentType.objects.get_for_model(Electronic)
                elif isinstance(product, Accessory):
                    content_type = ContentType.objects.get_for_model(Accessory)
                else:
                    content_type = None
                
                # Create SaleItem
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    content_type=content_type,
                    object_id=product.id,
                    item=product,
                    item_name=item_data['product_name'],
                    item_sku=item_data['product_code'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    total_price=item_data['total_price']
                )
                
                # Link unit if specified
                if item_data.get('unit_identifier'):
                    if item_data['category_type'] == 'Phone':
                        unit = Unit.objects.filter(
                            phone=product, 
                            identifier=item_data['unit_identifier']
                        ).first()
                    elif item_data['category_type'] == 'Electronic':
                        unit = Unit.objects.filter(
                            electronic=product, 
                            identifier=item_data['unit_identifier']
                        ).first()
                    else:
                        unit = None
                    
                    if unit:
                        sale_item.unit = unit
                        sale_item.save()
            
            # Update customer stats
            if customer:
                customer.total_purchases += subtotal
                customer.visit_count += 1
                customer.last_visit = timezone.now()
                customer.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Sale completed successfully!',
                'sale_id': sale.id,
                'sale_number': f"SALE-{sale.id:06d}",
                'total': float(subtotal),
                'items_count': len(sale_items_data),
                'customer': customer_name
            })
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)


# ============================================
# SINGLE ITEM SALE - Create Page
# ============================================

@login_required
def sale_create_single(request):
    """Create a single item sale page"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branches = Branch.objects.filter(company=company, is_active=True)
    customers = Customer.objects.filter(company=company, is_active=True).order_by('name')[:50]
    
    context = {
        'branches': branches,
        'customers': customers,
        'page_title': 'Create Single Sale',
        'page_subtitle': 'Sell an item by scanning IMEI/Serial',
    }
    return render(request, 'epa/sale_create_single.html', context)


# ============================================
# PRODUCT SEARCH - Autocomplete (Filtered by Company & Branch)
# ============================================

@login_required
def sale_search_units(request):
    """Search for units by identifier (IMEI/Serial) - Autocomplete"""
    company = request.user.company
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # Check if user is admin/manager
    is_admin = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    results = []
    
    # Base filter - only show units for this company
    base_filter = {
        'identifier__icontains': query,
        'status': 'available'
    }
    
    # If not admin/manager, filter by user's branch
    if not is_admin and request.user.branch:
        units = Unit.objects.filter(
            **base_filter
        ).filter(
            models.Q(phone__branch=request.user.branch) |
            models.Q(electronic__branch=request.user.branch)
        ).select_related(
            'phone', 'phone__branch', 
            'electronic', 'electronic__branch'
        )[:20]
    else:
        units = Unit.objects.filter(
            **base_filter,
            phone__company=company
        ).select_related(
            'phone', 'phone__branch', 
            'electronic', 'electronic__branch'
        )[:20]
        
        # Also get electronic units for the company
        electronic_units = Unit.objects.filter(
            **base_filter,
            electronic__company=company
        ).select_related(
            'electronic', 'electronic__branch'
        )[:20]
        
        # Combine both querysets
        units = list(units) + list(electronic_units)
        # Remove duplicates by id
        seen = set()
        units = [u for u in units if u.id not in seen and not seen.add(u.id)]
    
    for unit in units:
        product = None
        product_type = None
        product_info = {}
        
        if unit.phone:
            product = unit.phone
            product_type = 'Phone'
            product_info = {
                'name': product.name,
                'brand': product.brand,
                'model': product.model,
                'product_code': product.product_code,
                'selling_price': float(product.selling_price),
                'specs': f"{product.ram} RAM, {product.storage_capacity} Storage",
                'branch_name': product.branch.name if product.branch else '',
            }
        elif unit.electronic:
            product = unit.electronic
            product_type = 'Electronic'
            product_info = {
                'name': product.name,
                'brand': product.brand,
                'model': product.model_number,
                'product_code': product.product_code,
                'selling_price': float(product.selling_price),
                'specs': f"{product.ram} RAM, {product.storage} Storage",
                'branch_name': product.branch.name if product.branch else '',
            }
        else:
            continue
        
        results.append({
            'unit_id': unit.id,
            'identifier': unit.identifier,
            'unit_type': unit.unit_type,
            'product_type': product_type,
            'product': product_info,
            'display': f"{unit.identifier} - {product_info['brand']} {product_info['name']}",
            'status': unit.status,
        })
    
    return JsonResponse({'results': results})


# ============================================
# SINGLE ITEM SALE - Process
# ============================================

@login_required
@transaction.atomic
def sale_process_single(request):
    """Process a single item sale"""
    company = request.user.company
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Get form data
        unit_id = request.POST.get('unit_id')
        customer_name = request.POST.get('customer_name', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        customer_id_number = request.POST.get('customer_id_number', '').strip()
        customer_email = request.POST.get('customer_email', '').strip()
        next_of_keen_name = request.POST.get('next_of_keen_name', '').strip()
        next_of_keen_phone = request.POST.get('next_of_keen_phone', '').strip()
        
        sale_price = request.POST.get('sale_price', '0')
        sale_type = request.POST.get('sale_type', 'cash')
        branch_id = request.POST.get('branch_id')
        
        # Validate required fields
        if not unit_id:
            return JsonResponse({'error': 'Please scan or enter a unit identifier'}, status=400)
        
        if not customer_name:
            return JsonResponse({'error': 'Customer name is required'}, status=400)
        
        if not customer_phone:
            return JsonResponse({'error': 'Customer phone number is required'}, status=400)
        
        if not customer_id_number:
            return JsonResponse({'error': 'Customer ID number is required'}, status=400)
        
        if not sale_type:
            return JsonResponse({'error': 'Please select a sale type'}, status=400)
        
        try:
            sale_price = Decimal(str(sale_price))
            if sale_price <= 0:
                return JsonResponse({'error': 'Sale price must be greater than 0'}, status=400)
        except:
            return JsonResponse({'error': 'Invalid sale price'}, status=400)
        
        # Get the unit
        unit = get_object_or_404(Unit, id=unit_id)
        
        # Verify unit is available
        if unit.status != 'available':
            return JsonResponse({'error': f'Unit "{unit.identifier}" is not available'}, status=400)
        
        # Get the product
        product = None
        if unit.phone:
            product = unit.phone
        elif unit.electronic:
            product = unit.electronic
        else:
            return JsonResponse({'error': 'Invalid product'}, status=400)
        
        # Get branch
        branch = None
        if branch_id:
            branch = Branch.objects.filter(id=branch_id, company=company).first()
        if not branch:
            branch = product.branch
        
        if not branch:
            return JsonResponse({'error': 'No branch assigned to this product'}, status=400)
        
        # Create or get customer with ALL fields
        customer = Customer.objects.filter(phone=customer_phone, company=company).first()
        if not customer:
            customer = Customer.objects.create(
                company=company,
                branch=branch,
                name=customer_name,
                phone=customer_phone,
                email=customer_email,
                id_number=customer_id_number,  # NEW: Save ID number
                next_of_keen_name=next_of_keen_name,  # NEW: Save next of keen name
                next_of_keen_phone=next_of_keen_phone,  # NEW: Save next of keen phone
                address=f"ID: {customer_id_number} | Next of Keen: {next_of_keen_name} | NOK Phone: {next_of_keen_phone}",
                is_active=True
            )
        else:
            # Update customer info if needed
            if customer_name and customer.name != customer_name:
                customer.name = customer_name
            if customer_email and not customer.email:
                customer.email = customer_email
            if customer_id_number and customer.id_number != customer_id_number:
                customer.id_number = customer_id_number  # NEW: Update ID number
            if next_of_keen_name and customer.next_of_keen_name != next_of_keen_name:
                customer.next_of_keen_name = next_of_keen_name  # NEW: Update next of keen name
            if next_of_keen_phone and customer.next_of_keen_phone != next_of_keen_phone:
                customer.next_of_keen_phone = next_of_keen_phone  # NEW: Update next of keen phone
            customer.address = f"ID: {customer_id_number} | Next of Keen: {next_of_keen_name} | NOK Phone: {next_of_keen_phone}"
            customer.save()
        
        # Create owner (if not exists)
        owner = Owner.objects.filter(phone=customer_phone, company=company).first()
        if not owner:
            owner = Owner.objects.create(
                company=company,
                branch=branch,
                name=customer_name,
                phone=customer_phone,
                email=customer_email,
                id_number=customer_id_number,  # This field exists in Owner model
                address=f"ID: {customer_id_number} | Next of Keen: {next_of_keen_name} | NOK Phone: {next_of_keen_phone}",
                is_active=True
            )
        
        # Create sale
        sale = Sale.objects.create(
            company=company,
            branch=branch,
            customer=customer,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            total_amount=sale_price,
            discount=Decimal('0'),
            tax=Decimal('0'),
            net_amount=sale_price,
            payment_status='paid' if sale_type in ['cash', 'm-pesa', 'bank_transfer'] else 'pending',
            payment_method=sale_type,
            sold_by=request.user,
            sale_date=timezone.now()
        )
        
        # Create sale item
        content_type = ContentType.objects.get_for_model(product)
        sale_item = SaleItem.objects.create(
            sale=sale,
            content_type=content_type,
            object_id=product.id,
            item=product,
            item_name=f"{product.brand} {product.name}",
            item_sku=product.product_code,
            quantity=1,
            unit_price=sale_price,
            total_price=sale_price,
            unit=unit
        )
        
        # Update unit status
        unit.status = 'sold'
        unit.owner = owner
        unit.owner_name = customer_name
        unit.owner_phone = customer_phone
        unit.sold_date = timezone.now()
        unit.save()
        
        # Update product stock
        previous_quantity = product.quantity_in_stock
        if product.quantity_in_stock > 0:
            product.quantity_in_stock -= 1
            product.save()
        
        # Update customer stats
        customer.total_purchases += sale_price
        customer.visit_count += 1
        customer.last_visit = timezone.now()
        customer.save()
        
        # Update owner stats
        owner.total_purchases += sale_price
        owner.purchase_count += 1
        owner.last_purchase_date = timezone.now()
        owner.save()
        
        # Record stock movement
        from .utils import record_stock_movement
        record_stock_movement(
            product=product,
            movement_type='sale',
            quantity=-1,
            previous_quantity=previous_quantity,
            new_quantity=product.quantity_in_stock,
            branch=branch,
            unit=unit,
            reference_id=f"SALE-{sale.id}",
            reference_model='Sale',
            notes=f"Sale #{sale.id} - {customer_name} ({customer_phone})",
            performed_by=request.user
        )
        
        # Return success with sale ID for receipt redirect
        return JsonResponse({
            'success': True,
            'sale_id': sale.id,
            'message': f'Sale completed successfully! Receipt #{sale.id}',
            'redirect_url': f'/epa_shop/sale/receipt/{sale.id}/'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


# ============================================
# SALE RECEIPT - View Sale Receipt
# ============================================

@login_required
def sale_receipt(request, pk):
    """Generate and return sale receipt HTML page"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Try to get sale by pk or company_sale_id
    try:
        # If pk is a string that could be company_sale_id
        if isinstance(pk, str) and not pk.isdigit():
            sale = get_object_or_404(Sale, company_sale_id=pk, company=company)
        else:
            sale = get_object_or_404(Sale, pk=int(pk), company=company)
    except (ValueError, TypeError):
        sale = get_object_or_404(Sale, company_sale_id=str(pk), company=company)
    
    # Check branch access for non-admin users
    if not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch and sale.branch and sale.branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view receipts from other branches.')
            return redirect('/epa_shop/sales/')
    
    # Get sale items
    items = sale.items.all()
    
    context = {
        'sale': sale,
        'items': items,
        'page_title': f'Receipt #{sale.company_sale_id}',
        'page_subtitle': 'Sale receipt',
        'is_receipt': True,
    }
    return render(request, 'epa/sale_receipt.html', context)



# ============================================
# SALE RECEIPT  BY COMPANY SALE ID
# ============================================

@login_required
def sale_receipt_by_id(request, company_sale_id):
    """Generate and return sale receipt data using company_sale_id"""
    company = request.user.company
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    sale = get_object_or_404(Sale, company_sale_id=company_sale_id, company=company)
    
    # Check branch access for non-admin users
    if not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch and sale.branch and sale.branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view receipts from other branches.')
            return redirect('/epa_shop/sales/')
    
    items = sale.items.all()
    
    context = {
        'sale': sale,
        'items': items,
        'page_title': f'Receipt #{sale.company_sale_id}',
        'page_subtitle': 'Sale receipt',
        'is_receipt': True,
    }
    return render(request, 'epa_shop/sale_receipt.html', context)



# ============================================
# GET BRANCHES FOR POS
# ============================================

@login_required
def get_branches(request):
    """Get branches for POS dropdown"""
    company = request.user.company
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    branches = Branch.objects.filter(company=company, is_active=True)
    data = []
    for branch in branches:
        data.append({
            'id': branch.id,
            'name': branch.name,
            'code': branch.code,
            'city': branch.city,
            'country': branch.country,
            'currency': branch.currency_symbol or 'KSh'
        })
    
    return JsonResponse({'branches': data})


# ============================================
# SALE HISTORY
# ============================================

@login_required
def sale_history(request):
    """View sale history"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    sales = Sale.objects.filter(company=company).order_by('-sale_date')
    
    context = {
        'sales': sales,
        'total_count': sales.count(),
        'total_revenue': sales.aggregate(total=models.Sum('net_amount'))['total'] or 0,
        'page_title': 'Sales History',
        'page_subtitle': 'All completed sales',
    }
    return render(request, 'epa/sale_history.html', context)


# ============================================
# SALE LIST
# ============================================

@login_required
def sale_list(request):
    """List all sales with pagination"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is admin/manager
    is_admin = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    # Base filter - only show sales for this company
    sales_queryset = Sale.objects.filter(company=company)
    
    # If not admin/manager, filter by user's branch
    if not is_admin and request.user.branch:
        sales_queryset = sales_queryset.filter(branch=request.user.branch)
    
    sales_queryset = sales_queryset.order_by('-sale_date')
    
    # Get total count
    total_count = sales_queryset.count()
    
    # Get search query
    search_query = request.GET.get('search', '').strip()
    if search_query:
        sales_queryset = sales_queryset.filter(
            models.Q(customer_name__icontains=search_query) |
            models.Q(company_sale_id__icontains=search_query) |  # Search by company_sale_id
            models.Q(payment_method__icontains=search_query) |
            models.Q(payment_status__icontains=search_query)
        )
    
    # Get per_page parameter
    per_page = request.GET.get('per_page', '10')
    if per_page == 'all':
        per_page = total_count or 10
    else:
        try:
            per_page = int(per_page)
        except ValueError:
            per_page = 10
    
    # Pagination
    paginator = Paginator(sales_queryset, per_page)
    page = request.GET.get('page', 1)
    
    try:
        sales = paginator.page(page)
    except PageNotAnInteger:
        sales = paginator.page(1)
    except EmptyPage:
        sales = paginator.page(paginator.num_pages)
    
    context = {
        'sales': sales,
        'page_obj': sales,
        'total_count': total_count,
        'per_page': per_page,
        'search_query': search_query,
        'is_admin_or_manager': is_admin,
        'page_title': 'Sales',
        'page_subtitle': 'Sales history',
    }
    return render(request, 'epa/sales.html', context)


# ============================================
# SALE DETAIL
# ============================================

@login_required
def sale_detail(request, pk):
    """View sale details"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    sale = get_object_or_404(Sale, pk=pk, company=company)
    items = sale.items.all()
    
    context = {
        'sale': sale,
        'items': items,
        'page_title': f'Sale #{sale.id}',
        'page_subtitle': 'Sale details',
    }
    return render(request, 'epa/sale_detail.html', context)


# ============================================
# PRODUCT SEARCH - Autocomplete (Filtered by Company & Branch)
# ============================================

@login_required
def sale_search_units(request):
    """Search for units by identifier (IMEI/Serial) - Autocomplete"""
    company = request.user.company
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # Check if user is admin/manager
    is_admin = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    results = []
    
    # Get phone units for this company
    phone_units = Unit.objects.filter(
        identifier__icontains=query,
        status='available',
        phone__company=company  # Filter by company
    ).select_related('phone', 'phone__branch')[:20]
    
    # Get electronic units for this company
    electronic_units = Unit.objects.filter(
        identifier__icontains=query,
        status='available',
        electronic__company=company  # Filter by company
    ).select_related('electronic', 'electronic__branch')[:20]
    
    # Combine both querysets
    units = list(phone_units) + list(electronic_units)
    
    # Remove duplicates by id
    seen = set()
    units = [u for u in units if u.id not in seen and not seen.add(u.id)]
    
    # If not admin/manager, filter by user's branch
    if not is_admin and request.user.branch:
        filtered_units = []
        for unit in units:
            unit_branch = None
            if unit.phone:
                unit_branch = unit.phone.branch
            elif unit.electronic:
                unit_branch = unit.electronic.branch
            if unit_branch and unit_branch.id == request.user.branch.id:
                filtered_units.append(unit)
        units = filtered_units
    
    for unit in units:
        product = None
        product_type = None
        product_info = {}
        
        if unit.phone:
            product = unit.phone
            product_type = 'Phone'
            product_info = {
                'name': product.name,
                'brand': product.brand,
                'model': product.model,
                'product_code': product.product_code,
                'selling_price': float(product.selling_price),
                'specs': f"{product.ram} RAM, {product.storage_capacity} Storage",
                'branch_name': product.branch.name if product.branch else '',
            }
        elif unit.electronic:
            product = unit.electronic
            product_type = 'Electronic'
            product_info = {
                'name': product.name,
                'brand': product.brand,
                'model': product.model_number,
                'product_code': product.product_code,
                'selling_price': float(product.selling_price),
                'specs': f"{product.ram} RAM, {product.storage} Storage",
                'branch_name': product.branch.name if product.branch else '',
            }
        else:
            continue
        
        results.append({
            'unit_id': unit.id,
            'identifier': unit.identifier,
            'unit_type': unit.unit_type,
            'product_type': product_type,
            'product': product_info,
            'display': f"{unit.identifier} - {product_info['brand']} {product_info['name']}",
            'status': unit.status,
        })
    
    return JsonResponse({'results': results})

# ============================================
# GET UNIT BY IDENTIFIER (Quick Scan) - Filtered
# ============================================

@login_required
def sale_get_unit_by_identifier(request):
    """Get unit details by identifier (IMEI/Serial) - Quick lookup"""
    company = request.user.company
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    identifier = request.GET.get('identifier', '').strip()
    
    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    
    try:
        # Check if user is admin/manager
        is_admin = (
            request.user.is_company_admin or 
            request.user.is_company_manager or 
            request.user.is_super_admin or
            request.user.is_superuser or
            request.user.is_staff
        )
        
        # Search for the unit - MUST belong to the user's company
        unit = Unit.objects.filter(
            identifier=identifier
        ).select_related(
            'phone', 'phone__branch', 'electronic', 'electronic__branch'
        ).first()
        
        if not unit:
            return JsonResponse({'error': f'Unit "{identifier}" not found'}, status=404)
        
        # Check if unit belongs to the user's company
        unit_company = None
        unit_branch = None
        
        if unit.phone:
            unit_company = unit.phone.company
            unit_branch = unit.phone.branch
        elif unit.electronic:
            unit_company = unit.electronic.company
            unit_branch = unit.electronic.branch
        else:
            return JsonResponse({'error': 'Invalid product type'}, status=400)
        
        # CRITICAL: Check company access
        if not unit_company or unit_company.id != company.id:
            return JsonResponse({'error': 'Unit not found in your company'}, status=404)
        
        # If not admin/manager, check branch access
        if not is_admin:
            user_branch = request.user.branch
            if user_branch and unit_branch:
                if unit_branch.id != user_branch.id:
                    return JsonResponse({
                        'error': 'You do not have access to units from other branches'
                    }, status=403)
        
        # Check if unit is available
        if unit.status != 'available':
            return JsonResponse({
                'error': f'Unit "{identifier}" is already {unit.status}',
                'status': unit.status
            }, status=400)
        
        # Get product info
        product = None
        product_type = None
        product_data = {}
        
        if unit.phone:
            product = unit.phone
            product_type = 'Phone'
            product_data = {
                'product_code': product.product_code,
                'name': product.name,
                'brand': product.brand,
                'model': product.model,
                'specs': f"{product.ram} RAM, {product.storage_capacity} Storage",
                'color': product.color,
                'selling_price': float(product.selling_price),
                'purchase_price': float(product.purchase_price),
                'branch_id': product.branch_id,
                'branch_name': product.branch.name if product.branch else '',
                'stock': product.quantity_in_stock,
                'image': product.image.url if product.image else None,
            }
        elif unit.electronic:
            product = unit.electronic
            product_type = 'Electronic'
            product_data = {
                'product_code': product.product_code,
                'name': product.name,
                'brand': product.brand,
                'model': product.model_number,
                'specs': f"{product.ram} RAM, {product.storage} Storage",
                'color': product.color,
                'selling_price': float(product.selling_price),
                'purchase_price': float(product.purchase_price),
                'branch_id': product.branch_id,
                'branch_name': product.branch.name if product.branch else '',
                'stock': product.quantity_in_stock,
                'image': product.image.url if product.image else None,
            }
        else:
            return JsonResponse({'error': 'Invalid product type'}, status=400)
        
        # Get owner history if exists
        owner_history = None
        if unit.owner:
            owner_history = {
                'name': unit.owner.name,
                'phone': unit.owner.phone,
                'email': unit.owner.email,
                'total_purchases': float(unit.owner.total_purchases) if unit.owner.total_purchases else 0,
                'purchase_count': unit.owner.purchase_count,
            }
        
        return JsonResponse({
            'success': True,
            'unit': {
                'id': unit.id,
                'identifier': unit.identifier,
                'status': unit.status,
                'unit_type': unit.unit_type,
                'is_available': unit.status == 'available',
                'sold_date': unit.sold_date,
            },
            'product': product_data,
            'product_type': product_type,
            'owner_history': owner_history,
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
        

# ============================================
# CREATE SALE FROM UNIT (Legacy - Keep for compatibility)
# ============================================

@login_required
def sale_create(request):
    """Create a new sale from a unit (IMEI/Serial) - Legacy method"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Get unit and product from URL parameters
    unit_id = request.GET.get('unit')
    product_code = request.GET.get('product')
    
    unit = None
    product = None
    product_type = None
    
    if unit_id:
        unit = get_object_or_404(Unit, id=unit_id)
        # Find the associated product
        if unit.phone:
            product = unit.phone
            product_type = 'Phone'
        elif unit.electronic:
            product = unit.electronic
            product_type = 'Electronic'
    
    if not product and product_code:
        # Find product by code
        from .product_views import get_product_by_code
        product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, 'Product not found.')
        return redirect('/epa_shop/products/')
    
    # Get branches - filter by user's branch if not admin
    branches = Branch.objects.filter(company=company, is_active=True)
    
    # If user is not admin/manager, only show their branch
    is_admin = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_admin and request.user.branch:
        branches = branches.filter(id=request.user.branch.id)
    
    if request.method == 'POST':
        try:
            branch_id = request.POST.get('branch_id')
            customer_name = request.POST.get('customer_name', 'Walk-in Customer').strip()
            customer_phone = request.POST.get('customer_phone', '').strip()
            customer_email = request.POST.get('customer_email', '').strip()
            payment_method = request.POST.get('payment_method', 'cash')
            selling_price = float(request.POST.get('selling_price', 0))
            unit_id = request.POST.get('unit_id')
            
            if not branch_id:
                messages.error(request, 'Please select a branch.')
                return render(request, 'epa/sale_form.html', {
                    'product': product,
                    'product_type': product_type,
                    'unit': unit,
                    'branches': branches,
                    'page_title': 'Create Sale',
                    'page_subtitle': 'Sell a unit',
                    'default_price': product.selling_price if product else 0,
                })
            
            if selling_price <= 0:
                messages.error(request, 'Please enter a valid selling price.')
                return render(request, 'epa/sale_form.html', {
                    'product': product,
                    'product_type': product_type,
                    'unit': unit,
                    'branches': branches,
                    'page_title': 'Create Sale',
                    'page_subtitle': 'Sell a unit',
                    'default_price': product.selling_price if product else 0,
                })
            
            branch = get_object_or_404(Branch, id=branch_id, company=company)
            
            # Get the unit to sell
            if unit_id:
                unit_to_sell = get_object_or_404(Unit, id=unit_id)
            elif unit:
                unit_to_sell = unit
            else:
                messages.error(request, 'No unit selected for sale.')
                return render(request, 'epa/sale_form.html', {
                    'product': product,
                    'product_type': product_type,
                    'unit': unit,
                    'branches': branches,
                    'page_title': 'Create Sale',
                    'page_subtitle': 'Sell a unit',
                    'default_price': product.selling_price if product else 0,
                })
            
            # Create customer if phone exists
            customer = None
            if customer_phone:
                customer = Customer.objects.filter(phone=customer_phone, company=company).first()
                if not customer:
                    customer = Customer.objects.create(
                        company=company,
                        name=customer_name,
                        phone=customer_phone,
                        email=customer_email,
                        is_active=True
                    )
            
            # Start transaction
            with transaction.atomic():
                # Create sale
                sale = Sale.objects.create(
                    company=company,
                    branch=branch,
                    customer=customer,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    total_amount=selling_price,
                    discount=0,
                    tax=0,
                    net_amount=selling_price,
                    payment_status='paid',
                    payment_method=payment_method,
                    sold_by=request.user,
                    sale_date=timezone.now()
                )
                
                # Update unit status
                unit_to_sell.status = 'sold'
                unit_to_sell.sold_date = timezone.now()
                unit_to_sell.owner_name = customer_name
                unit_to_sell.owner_phone = customer_phone
                unit_to_sell.save()
                
                # Update product stock
                previous_quantity = product.quantity_in_stock
                product.quantity_in_stock -= 1
                product.save()
                
                # Record stock movement
                record_stock_movement(
                    product=product,
                    movement_type='sale',
                    quantity=-1,
                    previous_quantity=previous_quantity,
                    new_quantity=product.quantity_in_stock,
                    branch=branch,
                    unit=unit_to_sell,
                    notes=f"Sale - {customer_name}",
                    performed_by=request.user
                )
                
                # Create sale item
                content_type = ContentType.objects.get_for_model(product)
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    content_type=content_type,
                    object_id=product.id,
                    item=product,
                    item_name=product.name,
                    item_sku=product.product_code,
                    quantity=1,
                    unit_price=selling_price,
                    total_price=selling_price
                )
                
                # Link unit to sale item
                sale_item.unit = unit_to_sell
                sale_item.save()
                
                # Update customer stats
                if customer:
                    customer.total_purchases += selling_price
                    customer.visit_count += 1
                    customer.last_visit = timezone.now()
                    customer.save()
                
                messages.success(request, f'Sale completed successfully! Receipt #{sale.id}')
                return redirect(f'/epa_shop/sale/receipt/{sale.id}/')
                
        except Exception as e:
            messages.error(request, f'Error processing sale: {str(e)}')
    
    context = {
        'product': product,
        'product_type': product_type,
        'unit': unit,
        'branches': branches,
        'page_title': 'Create Sale',
        'page_subtitle': 'Sell a unit',
        'default_price': product.selling_price if product else 0,
    }
    return render(request, 'epa/sale_form.html', context)


# ============================================
# SALE EDIT - Update Sale Details
# ============================================

@login_required
def sale_edit(request, pk):
    """Edit sale details (Admin & Manager only)"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized
    is_authorized = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to edit sales.')
        return redirect('epa-sales')
    
    # Get the sale
    sale = get_object_or_404(Sale, pk=pk, company=company)
    
    # Get branches - filter by user's branch if not admin
    branches = Branch.objects.filter(company=company, is_active=True)
    
    # If user is not admin/manager, only show their branch
    is_admin = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_admin and request.user.branch:
        branches = branches.filter(id=request.user.branch.id)
    
    # Get all items in this sale
    sale_items = sale.items.all()
    
    if request.method == 'POST':
        try:
            # Get form data
            branch_id = request.POST.get('branch_id')
            customer_name = request.POST.get('customer_name', '').strip()
            customer_phone = request.POST.get('customer_phone', '').strip()
            customer_email = request.POST.get('customer_email', '').strip()
            payment_method = request.POST.get('payment_method', 'cash')
            payment_status = request.POST.get('payment_status', 'pending')
            selling_price = request.POST.get('selling_price', 0)
            
            # Validate
            if not branch_id:
                messages.error(request, 'Please select a branch.')
                return render(request, 'epa/sale_form.html', {
                    'sale': sale,
                    'sale_items': sale_items,
                    'branches': branches,
                    'page_title': f'Edit Sale #{sale.company_sale_id}',
                    'page_subtitle': 'Update sale details',
                })
            
            try:
                selling_price = float(selling_price)
                if selling_price <= 0:
                    messages.error(request, 'Please enter a valid selling price.')
                    return render(request, 'epa/sale_form.html', {
                        'sale': sale,
                        'sale_items': sale_items,
                        'branches': branches,
                        'page_title': f'Edit Sale #{sale.company_sale_id}',
                        'page_subtitle': 'Update sale details',
                    })
            except ValueError:
                messages.error(request, 'Invalid selling price.')
                return render(request, 'epa/sale_form.html', {
                    'sale': sale,
                    'sale_items': sale_items,
                    'branches': branches,
                    'page_title': f'Edit Sale #{sale.company_sale_id}',
                    'page_subtitle': 'Update sale details',
                })
            
            if not customer_name:
                messages.error(request, 'Customer name is required.')
                return render(request, 'epa/sale_form.html', {
                    'sale': sale,
                    'sale_items': sale_items,
                    'branches': branches,
                    'page_title': f'Edit Sale #{sale.company_sale_id}',
                    'page_subtitle': 'Update sale details',
                })
            
            # Get branch
            branch = get_object_or_404(Branch, id=branch_id, company=company)
            
            # Update sale
            sale.branch = branch
            sale.customer_name = customer_name
            sale.customer_phone = customer_phone
            sale.customer_email = customer_email
            sale.payment_method = payment_method
            sale.payment_status = payment_status
            sale.total_amount = Decimal(str(selling_price))
            sale.net_amount = Decimal(str(selling_price))
            sale.save()
            
            # Update sale items (update unit prices)
            for item in sale_items:
                item.unit_price = Decimal(str(selling_price))
                item.total_price = Decimal(str(selling_price))
                item.save()
            
            # Update customer if exists
            if sale.customer:
                sale.customer.name = customer_name
                sale.customer.phone = customer_phone
                if customer_email:
                    sale.customer.email = customer_email
                sale.customer.save()
            
            messages.success(request, f'Sale #{sale.company_sale_id} updated successfully!')
            return redirect(f'/epa_shop/sale/receipt/{sale.id}/')
            
        except Exception as e:
            messages.error(request, f'Error updating sale: {str(e)}')
            import traceback
            print(traceback.format_exc())
    
    # Default selling price from sale
    default_price = sale.net_amount
    
    context = {
        'sale': sale,
        'sale_items': sale_items,
        'branches': branches,
        'default_price': default_price,
        'page_title': f'Edit Sale #{sale.company_sale_id}',
        'page_subtitle': 'Update sale details',
    }
    return render(request, 'epa/sale_form.html', context)
    

# ============================================
# SALE COMPLETE - Mark Sale as Completed
# ============================================

@login_required
def sale_complete(request, sale_id):
    """Mark a sale as completed (Admin & Manager only)"""
    company = request.user.company
    
    if not company:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'No company assigned'}, status=400)
        messages.error(request, 'No company assigned.')
        return redirect('epa-dashboard')
    
    sale = get_object_or_404(Sale, id=sale_id, company=company)
    
    # Check if user is authorized (Company Admin or Manager)
    is_authorized = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'error': 'Unauthorized. Only Company Admins and Managers can complete sales.'
            }, status=403)
        messages.error(request, 'You do not have permission to complete sales.')
        return redirect('epa-sales')
    
    if request.method == 'POST':
        try:
            # Update sale status
            sale.payment_status = 'paid'
            sale.save()
            
            # Update customer stats if customer exists
            if sale.customer:
                sale.customer.total_purchases += sale.net_amount
                sale.customer.visit_count += 1
                sale.customer.last_visit = timezone.now()
                sale.customer.save()
            
            # Update owner stats if exists
            for item in sale.items.all():
                if item.unit and item.unit.owner:
                    owner = item.unit.owner
                    owner.total_purchases += item.total_price
                    owner.purchase_count += 1
                    owner.last_purchase_date = timezone.now()
                    owner.save()
            
            messages.success(request, f'Sale #{sale.id} has been marked as completed!')
            
            # Check if AJAX request
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': f'Sale #{sale.id} marked as completed.',
                    'sale_id': sale.id,
                    'redirect_url': f'/epa_shop/sale/receipt/{sale.id}/'
                })
            
            return redirect(f'/epa_shop/sale/receipt/{sale.id}/')
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f'Error completing sale: {str(e)}')
            return redirect('epa-sales')
    
    # GET request - show verification page
    context = {
        'sale': sale,
        'page_title': 'Verify Sale',
        'page_subtitle': f'Verify and complete sale #{sale.id}',
    }
    return render(request, 'epa/sale_verify.html', context)


# ============================================
# PENDING SALES LIST
# ============================================

@login_required
def sale_pending_list(request):
    """List all pending sales"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is admin/manager
    is_admin = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    # Base filter - only show sales for this company
    pending_sales = Sale.objects.filter(
        company=company,
        payment_status='pending'
    ).select_related('customer', 'sold_by', 'branch').prefetch_related('items', 'items__unit')
    
    # If not admin/manager, filter by user's branch
    if not is_admin and request.user.branch:
        pending_sales = pending_sales.filter(branch=request.user.branch)
    
    pending_sales = pending_sales.order_by('-sale_date')
    
    # Get all sales for count
    all_sales = Sale.objects.filter(company=company)
    total_sales = all_sales.count()
    total_pending = pending_sales.count()
    total_completed = all_sales.filter(payment_status='paid').count()
    
    context = {
        'sales': pending_sales,
        'total_pending': total_pending,
        'total_sales': total_sales,
        'total_completed': total_completed,
        'is_authorized': is_admin,
        'page_title': 'Pending Sales',
        'page_subtitle': 'Sales awaiting completion verification',
    }
    return render(request, 'epa/sales_pending.html', context)


# ============================================
# UNIT REVERSE SALE - Return to Available
# ============================================

@login_required
def unit_reverse_sale(request, sale_id):
    """Reverse a sale and return unit to available"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Try to get sale by id first, then by company_sale_id
    try:
        # First try as integer (pk)
        if str(sale_id).isdigit():
            sale = get_object_or_404(Sale, id=int(sale_id), company=company)
        else:
            # Try as company_sale_id
            sale = get_object_or_404(Sale, company_sale_id=sale_id, company=company)
    except (ValueError, TypeError):
        sale = get_object_or_404(Sale, company_sale_id=sale_id, company=company)
    
    # Check if user is authorized (Admin/Manager only)
    is_authorized = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'Only admins and managers can reverse sales.')
        return redirect('/epa_shop/sales/')
    
    # Get the referring page
    next_url = request.GET.get('next', '/epa_shop/units/phones/')
    
    if request.method == 'POST':
        try:
            # Find all units in this sale
            sale_items = SaleItem.objects.filter(sale=sale)
            reversed_count = 0
            
            for sale_item in sale_items:
                if sale_item.unit:
                    # Return unit to available
                    unit = sale_item.unit
                    unit.status = 'available'
                    unit.owner_name = ''
                    unit.owner_phone = ''
                    unit.sold_date = None
                    unit.save()
                    
                    # Update product stock
                    if unit.phone:
                        product = unit.phone
                    elif unit.electronic:
                        product = unit.electronic
                    else:
                        product = None
                    
                    if product:
                        product.quantity_in_stock += 1
                        product.save()
                    
                    reversed_count += 1
            
            # Update sale status
            sale.payment_status = 'refunded'
            sale.save()
            
            messages.success(request, f'Sale #{sale.company_sale_id} reversed successfully! {reversed_count} unit(s) returned to inventory.')
            return redirect(next_url)
            
        except Exception as e:
            messages.error(request, f'Error reversing sale: {str(e)}')
            return redirect(next_url)
    
    context = {
        'sale': sale,
        'sale_items': sale.items.all(),
        'next_url': next_url,
        'page_title': 'Reverse Sale',
        'page_subtitle': f'Confirm reversal of sale #{sale.company_sale_id}',
    }
    return render(request, 'epa/sale_reverse.html', context)


# ============================================
# SALE DELETE - Delete a Refunded Sale
# ============================================

@login_required
def sale_delete(request, pk):
    """Delete a refunded sale (Admin & Manager only)"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Check if user is authorized
    is_authorized = (
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to delete sales.')
        return redirect('epa-sales')
    
    sale = get_object_or_404(Sale, pk=pk, company=company)
    
    # Only allow deletion of refunded sales
    if sale.payment_status != 'refunded':
        messages.error(request, 'Only refunded sales can be deleted.')
        return redirect('epa-sales')
    
    if request.method == 'POST':
        try:
            sale_id = sale.company_sale_id
            sale.delete()
            messages.success(request, f'Sale #{sale_id} deleted successfully!')
            return redirect('epa-sales')
        except Exception as e:
            messages.error(request, f'Error deleting sale: {str(e)}')
            return redirect('epa-sales')
    
    context = {
        'sale': sale,
        'page_title': 'Delete Sale',
        'page_subtitle': f'Confirm deletion of sale #{sale.company_sale_id}',
    }
    return render(request, 'epa/sale_delete_confirm.html', context)


