from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Count, Sum
from decimal import Decimal
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.utils import timezone
from .models import Electronic, Phone, Accessory, Category, Branch, Supplier, Unit, Sale, SaleItem, Customer, Owner
from django.contrib.auth import get_user_model
from .utils import record_stock_movement 
import json
import os

User = get_user_model()


# ============================================
# HELPER FUNCTION - Get product by code
# ============================================

def get_product_by_code(company, product_code):
    """Get a product by its product code across all models"""
    # Try Phone
    try:
        product = Phone.objects.get(company=company, product_code=product_code)
        return product, 'Phone'
    except Phone.DoesNotExist:
        pass
    
    # Try Electronic
    try:
        product = Electronic.objects.get(company=company, product_code=product_code)
        return product, 'Electronic'
    except Electronic.DoesNotExist:
        pass
    
    # Try Accessory
    try:
        product = Accessory.objects.get(company=company, product_code=product_code)
        return product, 'Accessory'
    except Accessory.DoesNotExist:
        pass
    
    return None, None


# ============================================
# HELPER FUNCTIONS - User Role Checks
# ============================================

def is_admin_or_manager(user):
    """Check if user is admin, manager, or super admin"""
    return user.role in ['super_admin', 'company_admin', 'company_manager']


def is_cashier(user):
    """Check if user is a cashier"""
    return user.role == 'company_cashier'


def is_agent(user):
    """Check if user is an agent"""
    return user.role == 'company_agent'


def is_staff(user):
    """Check if user is staff"""
    return user.role == 'company_staff'


def get_user_branch(user):
    """Get the user's branch"""
    return user.branch if user else None


def get_user_owned_units(user):
    """Get units owned by the user (for agents)"""
    if not user:
        return []
    
    # Get owner record for this user
    owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
    if owner:
        return Unit.objects.filter(owner=owner).values_list('id', flat=True)
    return []


def filter_by_user_access(queryset, user, model_type='product'):
    """
    Filter queryset based on user's role:
    - Admin/Manager: See everything in their company/branch
    - Cashier: See everything in their branch
    - Agent: See only their own items (created by them or assigned to them)
    - Staff: See everything in their branch (read-only)
    """
    if not user:
        return queryset
    
    # Admins and Managers see everything in their company
    if is_admin_or_manager(user):
        return queryset
    
    user_branch = get_user_branch(user)
    
    # Cashiers see everything in their branch
    if is_cashier(user):
        if user_branch:
            return queryset.filter(branch=user_branch)
        return queryset
    
    # Agents see only their own items
    if is_agent(user):
        # Get owner record for this user
        owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
        if owner:
            return queryset.filter(owner=owner)
        # If no owner record, return empty queryset
        return queryset.none()
    
    # Staff see everything in their branch (read-only)
    if is_staff(user):
        if user_branch:
            return queryset.filter(branch=user_branch)
        return queryset
    
    return queryset


def filter_units_by_user_access(units_queryset, user):
    """
    Filter units based on user's role:
    - Admin/Manager: See all units
    - Cashier: See units in their branch
    - Agent: See only AVAILABLE units they own (exclude sold)
    - Staff: See units in their branch
    """
    if not user:
        return units_queryset
    
    # Admins and Managers see all units
    if is_admin_or_manager(user):
        return units_queryset
    
    user_branch = get_user_branch(user)
    
    # Cashiers see units in their branch
    if is_cashier(user):
        if user_branch:
            return units_queryset.filter(
                Q(phone__branch=user_branch) | Q(electronic__branch=user_branch)
            )
        return units_queryset
    
    # Agents see only AVAILABLE units they own (exclude sold)
    if is_agent(user):
        owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
        if owner:
            # Only show available units that belong to the agent
            return units_queryset.filter(owner=owner, status='available')
        return units_queryset.none()
    
    # Staff see units in their branch
    if is_staff(user):
        if user_branch:
            return units_queryset.filter(
                Q(phone__branch=user_branch) | Q(electronic__branch=user_branch)
            )
        return units_queryset
    
    return units_queryset


def filter_sales_by_user_access(sales_queryset, user):
    """
    Filter sales based on user's role:
    - Admin/Manager: See all sales
    - Cashier: See sales in their branch
    - Agent: See only sales they created
    - Staff: See sales in their branch
    """
    if not user:
        return sales_queryset
    
    # Admins and Managers see all sales
    if is_admin_or_manager(user):
        return sales_queryset
    
    user_branch = get_user_branch(user)
    
    # Cashiers see sales in their branch
    if is_cashier(user):
        if user_branch:
            return sales_queryset.filter(branch=user_branch)
        return sales_queryset
    
    # Agents see only sales they created
    if is_agent(user):
        return sales_queryset.filter(sold_by=user)
    
    # Staff see sales in their branch
    if is_staff(user):
        if user_branch:
            return sales_queryset.filter(branch=user_branch)
        return sales_queryset
    
    return sales_queryset


# ============================================
# HELPER FUNCTION - Get or create Owner from User
# ============================================

def get_or_create_owner_from_user(user):
    """Get or create an Owner record from a User"""
    if not user:
        return None
    
    # Check if user already has an owner record
    owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
    if owner:
        return owner
    
    # Create owner from user data
    owner = Owner.objects.create(
        company=user.company,
        name=user.get_full_name() or user.username,
        phone=user.phone or '',
        email=user.email or '',
        is_active=True
    )
    return owner


# ============================================
# UNIT EDIT - Inline Edit
# ============================================

@login_required
def unit_edit(request, unit_id):
    """Edit a unit's details (IMEI/Serial number)"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    unit = get_object_or_404(Unit, id=unit_id)
    
    # Check if unit belongs to company
    product = None
    product_type = None
    if unit.phone:
        product = unit.phone
        product_type = 'Phone'
    elif unit.electronic:
        product = unit.electronic
        product_type = 'Electronic'
    
    if not product or product.company != company:
        messages.error(request, 'You do not have permission to edit this unit.')
        return redirect('/epa_shop/products/')
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only edit units they own
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if not owner or unit.owner != owner:
            messages.error(request, 'You do not have permission to edit this unit.')
            return redirect('/epa_shop/products/')
    elif not is_admin_or_manager(request.user) and not is_cashier(request.user):
        # Cashiers and staff can edit units in their branch
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to edit units from other branches.')
            return redirect('/epa_shop/products/')
    
    # Get company employees (filtered by branch for non-admins)
    employees = User.objects.filter(company=company, is_active=True)
    if not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch:
            employees = employees.filter(branch=user_branch)
    employees = employees.order_by('first_name', 'last_name')
    
    # Get the referring page (default to units page)
    next_url = request.GET.get('next', f'/epa_shop/products/{product.product_code}/units/')
    
    if request.method == 'POST':
        try:
            identifier = request.POST.get('identifier', '').strip()
            status = request.POST.get('status', 'available')
            owner_id = request.POST.get('owner_id')
            
            if not identifier:
                messages.error(request, 'Identifier is required.')
                return render(request, 'epa/unit_edit.html', {
                    'unit': unit,
                    'product': product,
                    'product_type': product_type,
                    'employees': employees,
                    'next_url': next_url,
                    'page_title': 'Edit Unit',
                    'page_subtitle': 'Update unit details',
                })
            
            # Check if identifier is unique (except for this unit)
            if Unit.objects.filter(identifier=identifier).exclude(id=unit_id).exists():
                messages.error(request, f'Identifier "{identifier}" already exists.')
                return render(request, 'epa/unit_edit.html', {
                    'unit': unit,
                    'product': product,
                    'product_type': product_type,
                    'employees': employees,
                    'next_url': next_url,
                    'page_title': 'Edit Unit',
                    'page_subtitle': 'Update unit details',
                })
            
            unit.identifier = identifier
            unit.status = status
            
            # Set owner - Convert User to Owner
            if owner_id:
                try:
                    user = User.objects.get(id=owner_id, company=company)
                    owner = get_or_create_owner_from_user(user)
                    unit.owner = owner
                    unit.owner_name = owner.name
                    unit.owner_phone = owner.phone
                except User.DoesNotExist:
                    unit.owner = None
                    unit.owner_name = ''
                    unit.owner_phone = ''
            else:
                unit.owner = None
                unit.owner_name = ''
                unit.owner_phone = ''
            
            unit.save()
            
            # Update product stock if status changed
            if status == 'available':
                if unit.phone:
                    available_count = Unit.objects.filter(phone=product, status='available').count()
                    product.quantity_in_stock = available_count
                    product.save()
                elif unit.electronic:
                    available_count = Unit.objects.filter(electronic=product, status='available').count()
                    product.quantity_in_stock = available_count
                    product.save()
            
            messages.success(request, 'Unit updated successfully!')
            return redirect(next_url)
            
        except Exception as e:
            messages.error(request, f'Error updating unit: {str(e)}')
    
    context = {
        'unit': unit,
        'product': product,
        'product_type': product_type,
        'employees': employees,
        'next_url': next_url,
        'page_title': 'Edit Unit',
        'page_subtitle': 'Update unit details',
    }
    return render(request, 'epa/unit_edit.html', context)


# ============================================
# UNIT TRANSFER - Change Ownership
# ============================================

@login_required
def unit_transfer(request, unit_id):
    """Transfer unit ownership to an employee (ownership change only)"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    unit = get_object_or_404(Unit, id=unit_id)
    
    # Check if unit belongs to company
    product = None
    product_type = None
    if unit.phone:
        product = unit.phone
        product_type = 'Phone'
    elif unit.electronic:
        product = unit.electronic
        product_type = 'Electronic'
    
    if not product or product.company != company:
        messages.error(request, 'You do not have permission to transfer this unit.')
        return redirect('/epa_shop/products/')
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only transfer units they own
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if not owner or unit.owner != owner:
            messages.error(request, 'You do not have permission to transfer this unit.')
            return redirect('/epa_shop/products/')
    elif not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to transfer units from other branches.')
            return redirect('/epa_shop/products/')
    
    # Allow transfer for available units only
    if unit.status not in ['available', 'reserved']:
        messages.error(request, 'Only available or reserved units can be transferred.')
        return redirect(f'/epa_shop/products/{product.product_code}/units/')
    
    # Get company employees (filtered by branch for non-admins)
    employees = User.objects.filter(company=company, is_active=True)
    if not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch:
            employees = employees.filter(branch=user_branch)
    employees = employees.order_by('first_name', 'last_name')
    
    # Get the referring page (default to units page)
    next_url = request.GET.get('next', f'/epa_shop/products/{product.product_code}/units/')
    
    if request.method == 'POST':
        try:
            owner_id = request.POST.get('owner_id')
            
            if not owner_id:
                messages.error(request, 'Please select an owner.')
                return render(request, 'epa/unit_transfer.html', {
                    'unit': unit,
                    'product': product,
                    'product_type': product_type,
                    'employees': employees,
                    'next_url': next_url,
                    'page_title': 'Transfer Unit',
                    'page_subtitle': 'Change ownership',
                })
            
            try:
                user = User.objects.get(id=owner_id, company=company)
                owner = get_or_create_owner_from_user(user)
            except User.DoesNotExist:
                messages.error(request, 'Selected employee not found.')
                return render(request, 'epa/unit_transfer.html', {
                    'unit': unit,
                    'product': product,
                    'product_type': product_type,
                    'employees': employees,
                    'next_url': next_url,
                    'page_title': 'Transfer Unit',
                    'page_subtitle': 'Change ownership',
                })
            
            # Update unit ownership ONLY - DO NOT change status
            unit.owner = owner
            unit.owner_name = owner.name
            unit.owner_phone = owner.phone
            # Status remains unchanged (available or reserved)
            unit.save()
            
            messages.success(request, f'Unit transferred to {unit.owner_name} successfully! Status remains "{unit.status}".')
            return redirect(next_url)
            
        except Exception as e:
            messages.error(request, f'Error transferring unit: {str(e)}')
    
    context = {
        'unit': unit,
        'product': product,
        'product_type': product_type,
        'employees': employees,
        'next_url': next_url,
        'page_title': 'Transfer Unit',
        'page_subtitle': 'Change ownership',
    }
    return render(request, 'epa/unit_transfer.html', context)


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
    
    sale = get_object_or_404(Sale, id=sale_id, company=company)
    
    # Check if user has permission to reverse (admin/manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can reverse sales.')
        return redirect('/epa_shop/products/')
    
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
            
            messages.success(request, f'Sale #{sale.id} reversed successfully! {reversed_count} unit(s) returned to inventory.')
            return redirect(next_url)
            
        except Exception as e:
            messages.error(request, f'Error reversing sale: {str(e)}')
            return redirect(next_url)
    
    context = {
        'sale': sale,
        'sale_items': sale.items.all(),
        'next_url': next_url,
        'page_title': 'Reverse Sale',
        'page_subtitle': 'Confirm sale reversal',
    }
    return render(request, 'epa/sale_reverse.html', context)


# ============================================
# SALE RECEIPT
# ============================================

@login_required
def sale_receipt(request, sale_id):
    """View sale receipt"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    sale = get_object_or_404(Sale, id=sale_id, company=company)
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only view receipts for sales they created
        if sale.sold_by != request.user:
            messages.error(request, 'You do not have permission to view this receipt.')
            return redirect('/epa_shop/sales/')
    elif not is_admin_or_manager(request.user):
        # Cashiers and staff can view receipts from their branch
        user_branch = get_user_branch(request.user)
        if user_branch and sale.branch and sale.branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view receipts from other branches.')
            return redirect('/epa_shop/sales/')
    
    items = SaleItem.objects.filter(sale=sale)
    
    context = {
        'sale': sale,
        'items': items,
        'page_title': f'Receipt #{sale.id}',
        'page_subtitle': 'Sale receipt',
    }
    return render(request, 'epa/receipt.html', context)


# ============================================
# ALL PHONE UNITS
# ============================================

@login_required
def all_phone_units(request):
    """View all phone units (IMEI numbers) across all products"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Base queryset - only show units from user's company
    units = Unit.objects.filter(
        phone__company=company,
        phone__is_active=True
    ).select_related('phone', 'phone__branch').order_by('-created_at')
    
    # For agents: Only show available units they own
    if is_agent(request.user):
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if owner:
            units = units.filter(owner=owner, status='available')
        else:
            units = units.none()
    else:
        # Apply user-based filtering for other roles
        units = filter_units_by_user_access(units, request.user)
    
    # Calculate days since update for each unit
    for unit in units:
        if unit.updated_at:
            delta = timezone.now() - unit.updated_at
            unit.days_since_update = delta.days
        else:
            unit.days_since_update = 0
    
    # Get stats
    total_units = units.count()
    available_units = units.filter(status='available').count()
    sold_units = units.filter(status='sold').count()
    reserved_units = units.filter(status='reserved').count()
    repair_units = units.filter(status='repair').count()
    
    context = {
        'units': units,
        'unit_type': 'Phone',
        'unit_label': 'IMEI',
        'total_units': total_units,
        'available_units': available_units,
        'sold_units': sold_units,
        'reserved_units': reserved_units,
        'repair_units': repair_units,
        'is_agent': is_agent(request.user),
        'page_title': 'Phone Units (IMEI)',
        'page_subtitle': 'All IMEI numbers across all phone products',
    }
    return render(request, 'epa/all_units.html', context)


# ============================================
# ALL ELECTRONIC UNITS
# ============================================

@login_required
def all_electronic_units(request):
    """View all electronic units (Serial numbers) across all products"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Base queryset - only show units from user's company
    units = Unit.objects.filter(
        electronic__company=company,
        electronic__is_active=True
    ).select_related('electronic', 'electronic__branch').order_by('-created_at')
    
    # For agents: Only show available units they own
    if is_agent(request.user):
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if owner:
            units = units.filter(owner=owner, status='available')
        else:
            units = units.none()
    else:
        # Apply user-based filtering for other roles
        units = filter_units_by_user_access(units, request.user)
    
    # Calculate days since update for each unit
    for unit in units:
        if unit.updated_at:
            delta = timezone.now() - unit.updated_at
            unit.days_since_update = delta.days
        else:
            unit.days_since_update = 0
    
    # Get stats
    total_units = units.count()
    available_units = units.filter(status='available').count()
    sold_units = units.filter(status='sold').count()
    reserved_units = units.filter(status='reserved').count()
    repair_units = units.filter(status='repair').count()
    
    context = {
        'units': units,
        'unit_type': 'Electronic',
        'unit_label': 'Serial',
        'total_units': total_units,
        'available_units': available_units,
        'sold_units': sold_units,
        'reserved_units': reserved_units,
        'repair_units': repair_units,
        'is_agent': is_agent(request.user),
        'page_title': 'Electronic Units (Serial)',
        'page_subtitle': 'All serial numbers across all electronic products',
    }
    return render(request, 'epa/all_units.html', context)


# ============================================
# UNIT DELETE - Using Product Code
# ============================================

@login_required
def unit_delete(request, product_code, identifier):
    """Delete a specific IMEI/Serial unit using product code"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Find the unit
    unit = get_object_or_404(Unit, identifier=identifier)
    
    # Check if the unit belongs to the company
    product = None
    product_type = None
    if unit.phone:
        product = unit.phone
        product_type = 'Phone'
    elif unit.electronic:
        product = unit.electronic
        product_type = 'Electronic'
    
    if not product or product.company != company:
        messages.error(request, 'You do not have permission to delete this unit.')
        return redirect('/epa_shop/products/')
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only delete units they own
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if not owner or unit.owner != owner:
            messages.error(request, 'You do not have permission to delete this unit.')
            return redirect('/epa_shop/products/')
    elif not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to delete units from other branches.')
            return redirect('/epa_shop/products/')
    
    # Verify product code matches
    if product.product_code != product_code:
        messages.error(request, 'Product code mismatch.')
        return redirect('/epa_shop/products/')
    
    if request.method == 'POST':
        identifier_value = unit.identifier
        
        # Store product info before deleting
        product_code_value = product.product_code
        product_type_value = product_type
        
        unit.delete()
        
        # Update product stock
        if product.quantity_in_stock > 0:
            product.quantity_in_stock -= 1
            product.save()
        
        messages.success(request, f'Unit "{identifier_value}" removed successfully!')
        
        # Redirect to the appropriate "All Units" page
        if product_type_value == 'Phone':
            return redirect('/epa_shop/units/phones/')
        elif product_type_value == 'Electronic':
            return redirect('/epa_shop/units/electronics/')
        else:
            # Fallback to product detail page
            return redirect(f'/epa_shop/products/{product_code_value}/')
    
    # GET request - show confirmation page
    context = {
        'unit': unit,
        'product': product,
        'product_type': product_type,
        'product_code': product_code,
        'page_title': 'Delete Unit',
        'page_subtitle': f'Confirm deletion of {identifier}',
    }
    return render(request, 'epa/unit_delete_confirm.html', context)


# ============================================
# PRODUCT LIST WITH PAGINATION
# ============================================

@login_required
def product_list(request):
    """List all products with proper data from database with pagination"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    all_products = []
    
    # Get Electronics with user-based filtering
    electronics = Electronic.objects.filter(company=company)
    electronics = filter_by_user_access(electronics, request.user, 'product')
    
    for item in electronics:
        all_products.append({
            'id': item.id,
            'product_code': item.product_code or '-',
            'display_id': item.product_code or f"E{item.id}",
            'name': item.name,
            'type': 'Electronic',
            'brand': item.brand or '-',
            'model': item.model_number or '-',
            'specs': f"{item.ram} {item.storage}".strip() or '-',
            'stock': item.quantity_in_stock,
            'purchase_price': float(item.purchase_price),
            'selling_price': float(item.selling_price),
            'best_price': float(item.best_price),
            'sku': item.model_number or '-',
            'is_active': item.is_active,
            'created_at': item.created_at,
            'image': item.image.url if item.image else None,
        })
    
    # Get Phones with user-based filtering - FIXED: Distinguish Smartphone vs Feature Phone
    phones = Phone.objects.filter(company=company)
    phones = filter_by_user_access(phones, request.user, 'product')
    
    for item in phones:
        # Determine if it's a Smartphone or Feature Phone
        # Check if the product has a phone_type field (if you added it to your model)
        phone_type = 'Smartphone'  # Default
        
        # Method 1: Check if 'phone_type' attribute exists on the model
        if hasattr(item, 'phone_type'):
            if item.phone_type == 'feature':
                phone_type = 'Feature Phone'
            else:
                phone_type = 'Smartphone'
        else:
            # Method 2: Detect by RAM/ROM values
            # Feature phones typically have 'N/A' or empty RAM/ROM
            ram_empty = not item.ram or item.ram == 'N/A' or item.ram == ''
            rom_empty = not item.storage_capacity or item.storage_capacity == 'N/A' or item.storage_capacity == ''
            
            if ram_empty and rom_empty:
                phone_type = 'Feature Phone'
            else:
                phone_type = 'Smartphone'
        
        all_products.append({
            'id': item.id,
            'product_code': item.product_code or '-',
            'display_id': item.product_code or f"P{item.id}",
            'name': item.name,
            'type': phone_type,  # Will be 'Smartphone' or 'Feature Phone'
            'brand': item.brand or '-',
            'model': item.model or '-',
            'specs': f"{item.ram} {item.storage_capacity}".strip() or '-',
            'stock': item.quantity_in_stock,
            'purchase_price': float(item.purchase_price),
            'selling_price': float(item.selling_price),
            'best_price': float(item.best_price),
            'sku': item.imei or '-',
            'is_active': item.is_active,
            'created_at': item.created_at,
            'image': item.image.url if item.image else None,
        })
    
    # Get Accessories with user-based filtering
    accessories = Accessory.objects.filter(company=company)
    accessories = filter_by_user_access(accessories, request.user, 'product')
    
    for item in accessories:
        all_products.append({
            'id': item.id,
            'product_code': item.product_code or '-',
            'display_id': item.product_code or f"A{item.id}",
            'name': item.name,
            'type': 'Accessory',
            'brand': item.brand or '-',
            'model': item.model or '-',
            'specs': item.accessory_type or '-',
            'stock': item.quantity_in_stock,
            'purchase_price': float(item.purchase_price),
            'selling_price': float(item.selling_price),
            'best_price': float(item.best_price),
            'sku': item.model or '-',
            'is_active': item.is_active,
            'created_at': item.created_at,
            'image': item.image.url if item.image else None,
        })
    
    # Sort by created date (newest first)
    all_products.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Apply search filter
    search_query = request.GET.get('search', '')
    if search_query:
        search_lower = search_query.lower()
        all_products = [p for p in all_products if 
                       search_lower in p['name'].lower() or 
                       search_lower in p['brand'].lower() or
                       search_lower in p['model'].lower() or
                       search_lower in p['product_code'].lower()]
    
    # Apply category filter - FIXED: Handle 'Phone' as filter for both Smartphone and Feature Phone
    category_filter = request.GET.get('category', '')
    if category_filter:
        if category_filter == 'Phone':
            # Filter to include both Smartphone and Feature Phone
            all_products = [p for p in all_products if p['type'] in ['Smartphone', 'Feature Phone']]
        else:
            all_products = [p for p in all_products if p['type'] == category_filter]
    
    # Pagination
    per_page = int(request.GET.get('per_page', 10))
    paginator = Paginator(all_products, per_page)
    page = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    context = {
        'products': page_obj.object_list,
        'page_obj': page_obj,
        'total_count': len(all_products),
        'search_query': search_query,
        'category_filter': category_filter,
        'per_page': per_page,
        'page_title': 'Products',
        'page_subtitle': 'Manage your products',
    }
    return render(request, 'epa/products.html', context)


    
# ============================================
# PRODUCT DETAIL - Using Product Code
# ============================================

@login_required
def product_detail(request, product_code):
    """View product details using product code"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only view products they own
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if not owner or product.owner != owner:
            messages.error(request, 'You do not have permission to view this product.')
            return redirect('/epa_shop/products/')
    elif not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view products from other branches.')
            return redirect('/epa_shop/products/')
    
    units = []
    total_units = 0
    
    if product_type == 'Phone':
        units = Unit.objects.filter(phone=product).order_by('-created_at')
        # Apply unit filtering for agents
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner)
            else:
                units = units.none()
        total_units = units.count()
        
        # Attach sale info to each unit
        for unit in units:
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            unit.sale = sale_item.sale if sale_item else None
            
    elif product_type == 'Electronic':
        units = Unit.objects.filter(electronic=product).order_by('-created_at')
        # Apply unit filtering for agents
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner)
            else:
                units = units.none()
        total_units = units.count()
        
        # Attach sale info to each unit
        for unit in units:
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            unit.sale = sale_item.sale if sale_item else None
            
    elif product_type == 'Accessory':
        # Accessories don't have individual units, use quantity_in_stock
        total_units = product.quantity_in_stock
    
    # ============================================
    # BRANCH STOCK INFORMATION (UNITS)
    # ============================================
    branches = Branch.objects.filter(company=company, is_active=True)
    
    # Filter branches based on role
    if is_agent(request.user):
        # Agents only see their own branch
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)
    elif not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)
    
    branch_stock_data = []
    
    for branch in branches:
        unit_count = 0
        
        if product_type == 'Phone':
            # Count units (IMEI numbers) for this phone in this branch
            unit_count = Unit.objects.filter(
                phone=product,
                phone__branch=branch,
                status='available'
            ).count()
            # Apply agent filtering
            if is_agent(request.user):
                owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
                if owner:
                    unit_count = Unit.objects.filter(
                        phone=product,
                        phone__branch=branch,
                        status='available',
                        owner=owner
                    ).count()
                else:
                    unit_count = 0
            
        elif product_type == 'Electronic':
            # Count units (Serial numbers) for this electronic in this branch
            unit_count = Unit.objects.filter(
                electronic=product,
                electronic__branch=branch,
                status='available'
            ).count()
            # Apply agent filtering
            if is_agent(request.user):
                owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
                if owner:
                    unit_count = Unit.objects.filter(
                        electronic=product,
                        electronic__branch=branch,
                        status='available',
                        owner=owner
                    ).count()
                else:
                    unit_count = 0
            
        elif product_type == 'Accessory':
            # Accessories: stock is stored on the product, not per unit
            # Show stock for the branch the accessory is assigned to
            if product.branch_id == branch.id:
                unit_count = product.quantity_in_stock
            else:
                unit_count = 0
        
        branch_stock_data.append({
            'id': branch.id,
            'name': branch.name,
            'code': branch.code,
            'unit_count': unit_count,
            'address': branch.address,
            'phone': branch.phone,
            'has_units': unit_count > 0,
            'is_primary': product.branch_id == branch.id if product_type == 'Accessory' else False,
        })
    
    # Sort: Primary branch first, then by unit count
    branch_stock_data.sort(key=lambda x: (not x['is_primary'], -x['unit_count']))
    
    # Count total units by branch
    total_available_units = sum(b['unit_count'] for b in branch_stock_data)
    
    context = {
        'product': product,
        'product_type': product_type,
        'units': units,
        'unit_count': total_units,
        'branches': branch_stock_data,
        'total_available_units': total_available_units,
        'product_code': product.product_code,
        'page_title': f'Product: {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
    }
    return render(request, 'epa/product_detail.html', context)


# ============================================
# PRODUCT CREATE - WITH IMAGE UPLOAD (FULLY FIXED)
# ============================================

@login_required
def product_create(request):
    """Create a new product - checks for duplicates first"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Agents cannot create products
    if is_agent(request.user):
        messages.error(request, 'Agents cannot create products. Please contact your manager.')
        return redirect('/epa_shop/products/')
    
    # Only admins, managers, and cashiers can create products
    if not is_admin_or_manager(request.user) and not is_cashier(request.user):
        messages.error(request, 'You do not have permission to create products.')
        return redirect('/epa_shop/products/')
    
    # Filter branches by user's branch for non-super-admin
    branches = Branch.objects.filter(company=company, is_active=True)
    if not request.user.is_super_admin and not request.user.is_company_admin:
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)
    
    # Initialize form data for GET request
    form_data = {}
    category_value = ''
    units_json = '[]'
    units = []
    
    if request.method == 'POST':
        try:
            # Get form data
            category_type = request.POST.get('category', '').strip()
            branch_id = request.POST.get('branch')
            name = request.POST.get('name', '').strip()
            brand = request.POST.get('brand', '').strip()
            model = request.POST.get('model', '').strip()
            
            # Get RAM and ROM from the list, use first non-empty value
            ram_list = request.POST.getlist('ram')
            ram = ''
            for val in ram_list:
                if val and val.strip():
                    ram = val.strip()
                    break
            
            # Get ROM for smartphones
            rom_list = request.POST.getlist('rom')
            rom = ''
            for val in rom_list:
                if val and val.strip():
                    rom = val.strip()
                    break
            
            # Get Storage for electronics
            storage_list = request.POST.getlist('storage')
            storage = ''
            for val in storage_list:
                if val and val.strip():
                    storage = val.strip()
                    break
            
            # If storage is still empty and we're on electronics, try 'rom' as fallback
            if category_type == 'electronics' and not storage:
                for val in rom_list:
                    if val and val.strip():
                        storage = val.strip()
                        break
            
            screen_size_list = request.POST.getlist('screen_size')
            screen_size = ''
            for val in screen_size_list:
                if val and val.strip():
                    screen_size = val.strip()
                    break
            
            color_list = request.POST.getlist('color')
            color = ''
            for val in color_list:
                if val and val.strip():
                    color = val.strip()
                    break
            
            battery_capacity_list = request.POST.getlist('battery_capacity')
            battery_capacity = ''
            for val in battery_capacity_list:
                if val and val.strip():
                    battery_capacity = val.strip()
                    break
            
            condition = request.POST.get('condition', 'new')
            
            # Feature phone specific fields
            network_type = request.POST.get('network_type', '').strip()
            memory_card = request.POST.get('memory_card', 'no')
            features = request.POST.get('features', '').strip()
            
            # Electronic specific fields
            device_type = request.POST.get('device_type', 'other')
            processor = request.POST.get('processor', '').strip()
            specs = request.POST.get('specs', '').strip()
            
            # Accessory specific fields
            accessory_type = request.POST.get('accessory_type', 'other')
            barcode = request.POST.get('barcode', '').strip()
            size = request.POST.get('size', '').strip()
            
            # Handle image upload
            image = request.FILES.get('product_image')
            
            # Parse prices
            try:
                purchase_price = Decimal(str(request.POST.get('purchase_price', 0) or 0))
            except:
                purchase_price = Decimal('0')
                
            try:
                selling_price = Decimal(str(request.POST.get('selling_price', 0) or 0))
            except:
                selling_price = Decimal('0')
            
            try:
                best_price = Decimal(str(request.POST.get('best_price', 0) or 0))
            except:
                best_price = Decimal('0')
            
            try:
                quantity = int(request.POST.get('quantity', 0) or 0)
            except:
                quantity = 0
            
            # ============================================
            # VALIDATIONS
            # ============================================
            if not category_type:
                messages.error(request, 'Please select a category.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            if not brand:
                messages.error(request, 'Brand is required.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            if not model:
                messages.error(request, 'Model is required.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            if not branch_id:
                messages.error(request, 'Please select a branch.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            try:
                branch = Branch.objects.get(id=branch_id, company=company, is_active=True)
            except Branch.DoesNotExist:
                messages.error(request, 'Selected branch is invalid or inactive.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            if purchase_price <= 0:
                messages.error(request, 'Buying price must be greater than 0.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            if selling_price <= 0:
                messages.error(request, 'Selling price must be greater than 0.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            # ============================================
            # CATEGORY-SPECIFIC VALIDATIONS
            # ============================================
            if category_type == 'smartphone':
                if not ram:
                    messages.error(request, 'RAM is required for smartphones.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
                if not rom:
                    messages.error(request, 'Storage (ROM) is required for smartphones.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
            
            elif category_type == 'feature_phone':
                # Feature phones - RAM/ROM are optional
                pass
            
            elif category_type == 'electronics':
                if not ram:
                    messages.error(request, 'RAM is required for electronics.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
                if not storage:
                    messages.error(request, 'Storage is required for electronics.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
                if not processor:
                    messages.error(request, 'Processor is required for electronics.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
            
            elif category_type == 'accessory':
                if not accessory_type or accessory_type == '':
                    messages.error(request, 'Accessory type is required.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
                if quantity <= 0:
                    messages.error(request, 'Quantity must be greater than 0 for accessories.')
                    return render(request, 'epa/product_form.html', {
                        'branches': branches,
                        'form_data': request.POST,
                        'category_value': category_type,
                        'units': units,
                        'units_json': '[]',
                        'is_edit': False,
                        'page_title': 'Add Product',
                        'page_subtitle': 'Create a new product',
                    })
            
            # Get units from hidden field
            units_data = request.POST.get('units', '[]')
            try:
                units = json.loads(units_data)
            except:
                units = []
            
            # ============================================
            # CHECK FOR EXISTING PRODUCT - PREVENT DUPLICATES
            # ============================================
            
            # Build the search criteria based on category
            existing_product = None
            existing_product_type = None
            
            if category_type in ['smartphone', 'feature_phone']:
                # Check for existing phone with same brand, model, ram, rom
                existing_phones = Phone.objects.filter(
                    company=company,
                    brand__iexact=brand,
                    model__iexact=model,
                    ram=ram,
                    storage_capacity=rom,
                    branch=branch,
                    is_active=True
                )
                
                if existing_phones.exists():
                    existing_product = existing_phones.first()
                    existing_product_type = 'Phone'
                    print(f"✅ Found existing Phone: {existing_product.product_code}")
            
            elif category_type == 'electronics':
                # Check for existing electronic with same brand, model, ram, storage, processor
                existing_electronics = Electronic.objects.filter(
                    company=company,
                    brand__iexact=brand,
                    model_number__iexact=model,
                    ram=ram,
                    storage=storage,
                    processor=processor,
                    branch=branch,
                    is_active=True
                )
                
                if existing_electronics.exists():
                    existing_product = existing_electronics.first()
                    existing_product_type = 'Electronic'
                    print(f"✅ Found existing Electronic: {existing_product.product_code}")
            
            elif category_type == 'accessory':
                # Check for existing accessory with same brand, model, accessory_type
                existing_accessories = Accessory.objects.filter(
                    company=company,
                    brand__iexact=brand,
                    model__iexact=model,
                    accessory_type=accessory_type,
                    branch=branch,
                    is_active=True
                )
                
                if existing_accessories.exists():
                    existing_product = existing_accessories.first()
                    existing_product_type = 'Accessory'
                    print(f"✅ Found existing Accessory: {existing_product.product_code}")
            
            # ============================================
            # IF PRODUCT EXISTS - ADD UNITS ONLY
            # ============================================
            if existing_product and existing_product_type:
                # Get or create owner from user
                owner = get_or_create_owner_from_user(request.user)
                
                added_count = 0
                skipped_count = 0
                
                # Add units to existing product
                if existing_product_type in ['Phone', 'Electronic']:
                    for unit_data in units:
                        identifier = unit_data.get('identifier', '').strip()
                        status = unit_data.get('status', 'available')
                        
                        if not identifier:
                            continue
                        
                        # Check if unit already exists
                        if Unit.objects.filter(identifier=identifier).exists():
                            skipped_count += 1
                            continue
                        
                        # Create the unit
                        if existing_product_type == 'Phone':
                            Unit.objects.create(
                                phone=existing_product,
                                identifier=identifier,
                                unit_type='imei',
                                status=status,
                                owner=owner
                            )
                        else:  # Electronic
                            Unit.objects.create(
                                electronic=existing_product,
                                identifier=identifier,
                                unit_type='serial',
                                status=status,
                                owner=owner
                            )
                        added_count += 1
                    
                    # Update stock count
                    if existing_product_type == 'Phone':
                        total_units = Unit.objects.filter(phone=existing_product).count()
                    else:
                        total_units = Unit.objects.filter(electronic=existing_product).count()
                    
                    existing_product.quantity_in_stock = total_units
                    existing_product.save()
                    
                elif existing_product_type == 'Accessory':
                    # For accessories, just add to quantity
                    existing_product.quantity_in_stock += quantity
                    existing_product.save()
                    added_count = quantity
                
                # Build success message
                if added_count > 0:
                    msg = f'✅ Product "{existing_product.name}" already exists (Code: {existing_product.product_code}). '
                    msg += f'Added {added_count} new unit(s) to stock.'
                    if skipped_count > 0:
                        msg += f' {skipped_count} identifier(s) already existed and were skipped.'
                    messages.success(request, msg)
                else:
                    if skipped_count > 0:
                        messages.warning(request, f'All {skipped_count} identifier(s) already exist in the system. No new units added.')
                    else:
                        messages.info(request, 'No new units to add. The product already exists.')
                
                return redirect('/epa_shop/products/')
            
            # ============================================
            # IF PRODUCT DOES NOT EXIST - CREATE NEW
            # ============================================
            
            # Auto-generate name if empty
            if not name or name.strip() == '':
                if category_type == 'smartphone':
                    name = f"{brand} {model} {rom} {ram}".strip()
                elif category_type == 'feature_phone':
                    name = f"{brand} {model}".strip()
                    if network_type:
                        name += f" ({network_type.upper()})"
                elif category_type == 'electronics':
                    name = f"{brand} {model} {ram} {storage}".strip()
                elif category_type == 'accessory':
                    name = f"{brand} {model} {accessory_type}".strip()
                else:
                    name = f"{brand} {model}".strip()
            
            # Get or create category
            category_map = {
                'smartphone': 'phones',
                'feature_phone': 'phones',
                'electronics': 'electronics',
                'accessory': 'accessories'
            }
            category_type_db = category_map.get(category_type, 'other')
            
            category = Category.objects.filter(
                company=company, 
                category_type=category_type_db
            ).first()
            
            if not category:
                category = Category.objects.create(
                    company=company,
                    name=category_type.replace('_', ' ').title(),
                    category_type=category_type_db,
                    is_active=True
                )
            
            # Get or create owner from user
            owner = get_or_create_owner_from_user(request.user)
            
            # ============================================
            # CREATE NEW PRODUCT
            # ============================================
            if category_type in ['smartphone', 'feature_phone']:
                # For feature phones, store extra data
                if category_type == 'feature_phone':
                    ram_value = ram or 'N/A'
                    rom_value = rom or 'N/A'
                    phone_type_value = 'feature'
                    network_type_value = network_type if network_type else None
                    memory_card_value = memory_card
                    features_value = features if features else None
                else:
                    ram_value = ram
                    rom_value = rom
                    phone_type_value = 'smartphone'
                    network_type_value = None
                    memory_card_value = 'no'
                    features_value = None
                
                # Create Phone
                product = Phone.objects.create(
                    company=company,
                    branch=branch,
                    category=category,
                    name=name,
                    brand=brand,
                    model=model,
                    imei=None,
                    color=color or '',
                    storage_capacity=rom_value,
                    ram=ram_value,
                    screen_size=screen_size or '',
                    battery_capacity=battery_capacity or '',
                    condition=condition,
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    best_price=best_price,
                    quantity_in_stock=len(units),
                    image=image,
                    owner=owner,
                    # Feature phone fields
                    phone_type=phone_type_value,
                    network_type=network_type_value,
                    memory_card=memory_card_value,
                    features=features_value
                )
                # Create units for this phone
                for unit_data in units:
                    Unit.objects.create(
                        phone=product,
                        identifier=unit_data['identifier'],
                        unit_type='imei',
                        status=unit_data.get('status', 'available'),
                        owner=owner
                    )
                
                product_type_label = "Feature Phone" if category_type == 'feature_phone' else "Smartphone"
                messages.success(request, f'✅ New {product_type_label} "{product.name}" created successfully! Product Code: {product.product_code}')
                
            elif category_type == 'electronics':
                # Create Electronic
                product = Electronic.objects.create(
                    company=company,
                    branch=branch,
                    category=category,
                    name=name,
                    brand=brand,
                    model_number=model,
                    serial_number=None,
                    device_type=device_type,
                    processor=processor,
                    ram=ram,
                    storage=storage,
                    screen_size=screen_size or '',
                    color=color or '',
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    best_price=best_price,
                    quantity_in_stock=len(units),
                    image=image,
                    owner=owner
                )
                # Create units for this electronic
                for unit_data in units:
                    Unit.objects.create(
                        electronic=product,
                        identifier=unit_data['identifier'],
                        unit_type='serial',
                        status=unit_data.get('status', 'available'),
                        owner=owner
                    )
                messages.success(request, f'✅ New Electronics "{product.name}" created successfully! Product Code: {product.product_code}')
                
            elif category_type == 'accessory':
                # Create Accessory
                product = Accessory.objects.create(
                    company=company,
                    branch=branch,
                    category=category,
                    name=name,
                    brand=brand,
                    accessory_type=accessory_type,
                    model=model or '',
                    compatible_phone_models=barcode or '',
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    best_price=best_price,
                    quantity_in_stock=quantity,
                    image=image,
                    owner=owner
                )
                messages.success(request, f'✅ New Accessory "{product.name}" created successfully! Product Code: {product.product_code}')
            
            else:
                messages.error(request, f'Unknown category: {category_type}')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': category_type,
                    'units': units,
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })
            
            return redirect('/epa_shop/products/')
            
        except Exception as e:
            messages.error(request, f'Error creating product: {str(e)}')
            import traceback
            traceback.print_exc()
            
            # Preserve form data for re-render
            form_data = request.POST
            category_value = request.POST.get('category', '')
            units_data = request.POST.get('units', '[]')
            try:
                units = json.loads(units_data)
            except:
                units = []
            units_json = json.dumps(units)
            
            return render(request, 'epa/product_form.html', {
                'branches': branches,
                'form_data': form_data,
                'category_value': category_value,
                'units': units,
                'units_json': units_json,
                'is_edit': False,
                'page_title': 'Add Product',
                'page_subtitle': 'Create a new product',
            })
    
    # GET request
    context = {
        'branches': branches,
        'form_data': {},
        'category_value': '',
        'units': [],
        'units_json': '[]',
        'is_edit': False,
        'page_title': 'Add Product',
        'page_subtitle': 'Create a new product',
    }
    return render(request, 'epa/product_form.html', context)


# ============================================
# PRODUCT EDIT - Using Product Code (FULLY FIXED)
# ============================================

@login_required
def product_edit(request, product_code):
    """Edit product details using product code"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Agents cannot edit products
    if is_agent(request.user):
        messages.error(request, 'Agents cannot edit products. Please contact your manager.')
        return redirect('/epa_shop/products/')
    
    # Only admins, managers, and cashiers can edit products
    if not is_admin_or_manager(request.user) and not is_cashier(request.user):
        messages.error(request, 'You do not have permission to edit products.')
        return redirect('/epa_shop/products/')
    
    product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    # Check branch access for non-admin users
    if not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to edit products from other branches.')
            return redirect('/epa_shop/products/')
    
    # Get units for this product
    units = []
    units_json = '[]'
    
    if product_type == 'Phone':
        units = Unit.objects.filter(phone=product).order_by('-created_at')
        units_json = json.dumps([{'identifier': u.identifier, 'status': u.status} for u in units])
    elif product_type == 'Electronic':
        units = Unit.objects.filter(electronic=product).order_by('-created_at')
        units_json = json.dumps([{'identifier': u.identifier, 'status': u.status} for u in units])
    
    # Get branches
    branches = Branch.objects.filter(company=company, is_active=True)
    if not request.user.is_super_admin and not request.user.is_company_admin:
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)
    
    # Determine category for the form
    if product_type == 'Phone':
        # Check if it's a feature phone or smartphone using the new phone_type field
        if hasattr(product, 'phone_type') and product.phone_type == 'feature':
            category_value = 'feature_phone'
        else:
            # Fallback: Detect by RAM/ROM values
            ram_empty = not product.ram or product.ram == 'N/A' or product.ram == ''
            rom_empty = not product.storage_capacity or product.storage_capacity == 'N/A' or product.storage_capacity == ''
            if ram_empty and rom_empty:
                category_value = 'feature_phone'
            else:
                category_value = 'smartphone'
    elif product_type == 'Electronic':
        category_value = 'electronics'
    elif product_type == 'Accessory':
        category_value = 'accessory'
    else:
        category_value = ''
    
    if request.method == 'POST':
        try:
            # Get form data
            category_type = request.POST.get('category', '').strip()
            branch_id = request.POST.get('branch')
            name = request.POST.get('name', '').strip()
            brand = request.POST.get('brand', '').strip()
            model = request.POST.get('model', '').strip()
            
            # Smartphone/Phone specific fields
            ram = request.POST.get('ram', '').strip()
            rom = request.POST.get('rom', '').strip()
            screen_size = request.POST.get('screen_size', '').strip()
            color = request.POST.get('color', '').strip()
            battery_capacity = request.POST.get('battery_capacity', '').strip()
            condition = request.POST.get('condition', 'new')
            
            # Feature phone specific fields - FIXED: Get these from POST
            network_type = request.POST.get('network_type', '').strip()
            memory_card = request.POST.get('memory_card', 'no')
            features = request.POST.get('features', '').strip()
            
            # Electronic specific fields
            device_type = request.POST.get('device_type', 'other')
            processor = request.POST.get('processor', '').strip()
            storage = request.POST.get('storage', '').strip()
            
            # Accessory specific fields
            accessory_type = request.POST.get('accessory_type', 'other')
            barcode = request.POST.get('barcode', '').strip()
            size = request.POST.get('size', '').strip()
            
            # Handle image upload
            image = request.FILES.get('product_image')
            
            # Parse prices
            try:
                purchase_price = Decimal(str(request.POST.get('purchase_price', 0) or 0))
            except:
                purchase_price = Decimal('0')
                
            try:
                selling_price = Decimal(str(request.POST.get('selling_price', 0) or 0))
            except:
                selling_price = Decimal('0')
            
            try:
                best_price = Decimal(str(request.POST.get('best_price', 0) or 0))
            except:
                best_price = Decimal('0')
            
            try:
                quantity = int(request.POST.get('quantity', 0) or 0)
            except:
                quantity = 0
                
            try:
                min_stock = int(request.POST.get('min_stock', 5) or 5)
            except:
                min_stock = 5
            
            # Validate
            if not branch_id:
                messages.error(request, 'Please select a branch.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'product': product,
                    'product_type': product_type,
                    'units': units,
                    'units_json': units_json,
                    'category_value': category_value,
                    'is_edit': True,
                    'page_title': f'Edit {product.name}',
                    'page_subtitle': f'Code: {product.product_code}',
                })
            
            if not brand:
                messages.error(request, 'Brand is required.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'product': product,
                    'product_type': product_type,
                    'units': units,
                    'units_json': units_json,
                    'category_value': category_value,
                    'is_edit': True,
                    'page_title': f'Edit {product.name}',
                    'page_subtitle': f'Code: {product.product_code}',
                })
            
            if not model:
                messages.error(request, 'Model is required.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'product': product,
                    'product_type': product_type,
                    'units': units,
                    'units_json': units_json,
                    'category_value': category_value,
                    'is_edit': True,
                    'page_title': f'Edit {product.name}',
                    'page_subtitle': f'Code: {product.product_code}',
                })
            
            if purchase_price <= 0:
                messages.error(request, 'Buying price must be greater than 0.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'product': product,
                    'product_type': product_type,
                    'units': units,
                    'units_json': units_json,
                    'category_value': category_value,
                    'is_edit': True,
                    'page_title': f'Edit {product.name}',
                    'page_subtitle': f'Code: {product.product_code}',
                })
            
            if selling_price <= 0:
                messages.error(request, 'Selling price must be greater than 0.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'product': product,
                    'product_type': product_type,
                    'units': units,
                    'units_json': units_json,
                    'category_value': category_value,
                    'is_edit': True,
                    'page_title': f'Edit {product.name}',
                    'page_subtitle': f'Code: {product.product_code}',
                })
            
            # Auto-generate name if empty
            if not name:
                if product_type == 'Phone':
                    name = f"{brand} {model} {rom} {ram}".strip()
                elif product_type == 'Electronic':
                    name = f"{brand} {model} {ram} {storage}".strip()
                else:
                    name = f"{brand} {model} {accessory_type}".strip()
            
            # Get or create owner
            owner = get_or_create_owner_from_user(request.user)
            
            # ============================================
            # UPDATE BASED ON CATEGORY
            # ============================================
            
            # Update common fields
            product.name = name
            product.brand = brand
            product.purchase_price = purchase_price
            product.selling_price = selling_price
            
            if hasattr(product, 'best_price'):
                product.best_price = best_price
            
            if branch_id:
                product.branch_id = branch_id
            
            # Handle image
            if image:
                if product.image:
                    try:
                        if os.path.isfile(product.image.path):
                            os.remove(product.image.path)
                    except:
                        pass
                product.image = image
            
            # Update based on type
            if product_type == 'Phone':
                # Common phone fields
                product.model = model
                product.ram = ram or ''
                product.storage_capacity = rom or ''
                product.screen_size = screen_size or ''
                product.color = color or ''
                product.battery_capacity = battery_capacity or ''
                product.condition = condition
                
                # FIXED: Save feature phone specific fields
                if category_type == 'feature_phone':
                    product.phone_type = 'feature'
                    product.network_type = network_type if network_type else None
                    product.memory_card = memory_card
                    product.features = features if features else None
                else:
                    product.phone_type = 'smartphone'
                    product.network_type = None
                    product.memory_card = 'no'
                    product.features = None
                
                product.save()
                
                # Update units
                units_data = request.POST.get('units', '[]')
                try:
                    new_units = json.loads(units_data)
                except:
                    new_units = []
                
                existing_units = Unit.objects.filter(phone=product)
                existing_identifiers = set(existing_units.values_list('identifier', flat=True))
                new_identifiers = set()
                
                for unit_data in new_units:
                    if 'identifier' in unit_data:
                        new_identifiers.add(unit_data['identifier'])
                
                units_to_delete = existing_identifiers - new_identifiers
                if units_to_delete:
                    Unit.objects.filter(phone=product, identifier__in=units_to_delete).delete()
                
                for unit_data in new_units:
                    identifier = unit_data.get('identifier')
                    status = unit_data.get('status', 'available')
                    
                    if not identifier:
                        continue
                    
                    existing_unit = Unit.objects.filter(phone=product, identifier=identifier).first()
                    if existing_unit:
                        existing_unit.status = status
                        existing_unit.save()
                    else:
                        Unit.objects.create(
                            phone=product,
                            identifier=identifier,
                            unit_type='imei',
                            status=status,
                            owner=owner
                        )
                
                total_units = Unit.objects.filter(phone=product).count()
                product.quantity_in_stock = total_units
                product.save()
                
                phone_type_label = "Feature Phone" if category_type == 'feature_phone' else "Smartphone"
                messages.success(request, f'{phone_type_label} "{product.name}" updated successfully! Product Code: {product.product_code}')
                
            elif product_type == 'Electronic':
                product.model_number = model
                product.device_type = device_type
                product.processor = processor or ''
                product.ram = ram or ''
                product.storage = storage or ''
                product.screen_size = screen_size or ''
                product.color = color or ''
                product.save()
                
                # Update units
                units_data = request.POST.get('units', '[]')
                try:
                    new_units = json.loads(units_data)
                except:
                    new_units = []
                
                existing_units = Unit.objects.filter(electronic=product)
                existing_identifiers = set(existing_units.values_list('identifier', flat=True))
                new_identifiers = set()
                
                for unit_data in new_units:
                    if 'identifier' in unit_data:
                        new_identifiers.add(unit_data['identifier'])
                
                units_to_delete = existing_identifiers - new_identifiers
                if units_to_delete:
                    Unit.objects.filter(electronic=product, identifier__in=units_to_delete).delete()
                
                for unit_data in new_units:
                    identifier = unit_data.get('identifier')
                    status = unit_data.get('status', 'available')
                    
                    if not identifier:
                        continue
                    
                    existing_unit = Unit.objects.filter(electronic=product, identifier=identifier).first()
                    if existing_unit:
                        existing_unit.status = status
                        existing_unit.save()
                    else:
                        Unit.objects.create(
                            electronic=product,
                            identifier=identifier,
                            unit_type='serial',
                            status=status,
                            owner=owner
                        )
                
                total_units = Unit.objects.filter(electronic=product).count()
                product.quantity_in_stock = total_units
                product.save()
                
                messages.success(request, f'Electronics "{product.name}" updated successfully! Product Code: {product.product_code}')
                
            elif product_type == 'Accessory':
                product.model = model or ''
                product.accessory_type = accessory_type
                product.compatible_phone_models = barcode or ''
                product.quantity_in_stock = quantity
                product.minimum_stock_level = min_stock
                product.save()
                
                messages.success(request, f'Accessory "{product.name}" updated successfully! Product Code: {product.product_code}')
            
            return redirect('/epa_shop/products/')
            
        except Exception as e:
            messages.error(request, f'Error updating product: {str(e)}')
            import traceback
            traceback.print_exc()
            return render(request, 'epa/product_form.html', {
                'branches': branches,
                'product': product,
                'product_type': product_type,
                'units': units,
                'units_json': units_json,
                'category_value': category_value,
                'is_edit': True,
                'form_data': request.POST,
                'page_title': f'Edit {product.name}',
                'page_subtitle': f'Code: {product.product_code}',
            })
    
    # GET request - Pass existing data to template
    context = {
        'branches': branches,
        'product': product,
        'product_type': product_type,
        'units': units,
        'units_json': units_json,
        'category_value': category_value,
        'is_edit': True,
        'page_title': f'Edit {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
        # Pass feature phone data to template for pre-population
        'form_data': {
            'network_type': getattr(product, 'network_type', ''),
            'features': getattr(product, 'features', ''),
            'memory_card': getattr(product, 'memory_card', 'no'),
            'phone_type': getattr(product, 'phone_type', 'smartphone'),
        }
    }
    return render(request, 'epa/product_form.html', context)

# ============================================
# PRODUCT DELETE - Using Product Code
# ============================================

@login_required
def product_delete(request, product_code):
    """Delete a product using product code"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Agents cannot delete products
    if is_agent(request.user):
        messages.error(request, 'Agents cannot delete products. Please contact your manager.')
        return redirect('/epa_shop/products/')
    
    # Only admins and managers can delete products
    if not is_admin_or_manager(request.user):
        messages.error(request, 'You do not have permission to delete products.')
        return redirect('/epa_shop/products/')
    
    product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    # Check branch access for non-admin users
    if not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to delete products from other branches.')
            return redirect('/epa_shop/products/')
    
    if request.method == 'POST':
        try:
            product_name = product.name
            product_code_value = product.product_code
            
            # Delete associated units first
            if product_type == 'Phone':
                Unit.objects.filter(phone=product).delete()
            elif product_type == 'Electronic':
                Unit.objects.filter(electronic=product).delete()
            
            # Delete the product
            product.delete()
            messages.success(request, f'Product "{product_name}" deleted successfully!')
            return redirect('/epa_shop/products/')
            
        except Exception as e:
            messages.error(request, f'Error deleting product: {str(e)}')
            return redirect('/epa_shop/products/')
    
    context = {
        'product': product,
        'product_type': product_type,
        'page_title': f'Delete {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
    }
    return render(request, 'epa/product_delete_confirm.html', context)


# ============================================
# PRODUCT RESTOCK - Using Product Code
# ============================================

# ============================================
# PRODUCT RESTOCK - Using Product Code (FIXED)
# ============================================

@login_required
def product_restock(request, product_code):
    """Restock a product using product code"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Get the product
    product, product_type = get_product_by_code(company, product_code)
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only restock products they own
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if not owner:
            messages.error(request, 'You do not have an owner profile. Please contact your manager.')
            return redirect('/epa_shop/products/')
        if product.owner != owner:
            messages.error(request, 'You can only restock products you own.')
            return redirect('/epa_shop/products/')
    elif not is_admin_or_manager(request.user) and not is_cashier(request.user):
        messages.error(request, 'You do not have permission to restock products.')
        return redirect('/epa_shop/products/')
    
    # Check branch access for non-admin users
    if not is_admin_or_manager(request.user) and not is_cashier(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to restock products from other branches.')
            return redirect('/epa_shop/products/')
    
    # Get existing units for display
    existing_units = []
    if product_type in ['Phone', 'Electronic']:
        if product_type == 'Phone':
            existing_units = Unit.objects.filter(phone=product).order_by('-created_at')
        else:
            existing_units = Unit.objects.filter(electronic=product).order_by('-created_at')
    
    # Initialize variables for form data preservation
    form_units = []
    form_units_json = '[]'
    submitted_quantity = 0
    
    if request.method == 'POST':
        try:
            # ============================================
            # FOR PHONES AND ELECTRONICS - Add Units (IMEI/Serial)
            # ============================================
            if product_type in ['Phone', 'Electronic']:
                # Get units from hidden field
                units_data = request.POST.get('units', '[]')
                try:
                    new_units = json.loads(units_data)
                except:
                    new_units = []
                
                # Store for re-render if needed
                form_units = new_units
                form_units_json = units_data
                
                if not new_units:
                    messages.error(request, 'Please add at least one IMEI/Serial number.')
                    # Re-render with the form data preserved
                    context = {
                        'product': product,
                        'product_type': product_type,
                        'existing_units': existing_units,
                        'form_units': form_units,
                        'form_units_json': form_units_json,
                        'page_title': f'Restock - {product.name}',
                        'page_subtitle': f'Code: {product.product_code}',
                        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
                    }
                    return render(request, 'epa/product_restock.html', context)
                
                # Get or create owner from user
                owner = get_or_create_owner_from_user(request.user)
                
                added_count = 0
                skipped_count = 0
                duplicate_identifiers = []
                
                # Create units
                for unit_data in new_units:
                    identifier = unit_data.get('identifier', '').strip()
                    status = unit_data.get('status', 'available')
                    
                    if not identifier:
                        continue
                    
                    # Check if identifier already exists
                    if Unit.objects.filter(identifier=identifier).exists():
                        skipped_count += 1
                        duplicate_identifiers.append(identifier)
                        continue
                    
                    # Create the unit
                    if product_type == 'Phone':
                        Unit.objects.create(
                            phone=product,
                            identifier=identifier,
                            unit_type='imei',
                            status=status,
                            owner=owner
                        )
                    else:  # Electronic
                        Unit.objects.create(
                            electronic=product,
                            identifier=identifier,
                            unit_type='serial',
                            status=status,
                            owner=owner
                        )
                    added_count += 1
                
                if added_count == 0:
                    # Build detailed error message
                    error_msg = 'No new units were added. '
                    if duplicate_identifiers:
                        error_msg += f'The following identifiers already exist: {", ".join(duplicate_identifiers[:5])}'
                        if len(duplicate_identifiers) > 5:
                            error_msg += f' and {len(duplicate_identifiers) - 5} more.'
                    else:
                        error_msg += 'All identifiers were invalid or empty.'
                    
                    messages.error(request, error_msg)
                    
                    # Re-render with the form data preserved
                    context = {
                        'product': product,
                        'product_type': product_type,
                        'existing_units': existing_units,
                        'form_units': form_units,
                        'form_units_json': form_units_json,
                        'page_title': f'Restock - {product.name}',
                        'page_subtitle': f'Code: {product.product_code}',
                        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
                    }
                    return render(request, 'epa/product_restock.html', context)
                
                # Update stock count
                if product_type == 'Phone':
                    total_units = Unit.objects.filter(phone=product).count()
                else:
                    total_units = Unit.objects.filter(electronic=product).count()
                
                product.quantity_in_stock = total_units
                product.save()
                
                if skipped_count > 0:
                    messages.warning(request, f'Added {added_count} units to {product.name}. {skipped_count} identifiers already existed and were skipped. New stock: {total_units}')
                else:
                    messages.success(request, f'Added {added_count} units to {product.name}. New stock: {total_units}')
                
                return redirect('/epa_shop/products/')
            
            # ============================================
            # FOR ACCESSORIES - Add Quantity
            # ============================================
            elif product_type == 'Accessory':
                quantity = int(request.POST.get('quantity', 0))
                submitted_quantity = quantity
                
                if quantity <= 0:
                    messages.error(request, 'Quantity must be greater than 0.')
                    # Re-render with the form data preserved
                    context = {
                        'product': product,
                        'product_type': product_type,
                        'existing_units': existing_units,
                        'submitted_quantity': submitted_quantity,
                        'page_title': f'Restock - {product.name}',
                        'page_subtitle': f'Code: {product.product_code}',
                        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
                    }
                    return render(request, 'epa/product_restock.html', context)
                
                # Update stock
                product.quantity_in_stock += quantity
                product.save()
                
                messages.success(request, f'Added {quantity} units to {product.name}. New stock: {product.quantity_in_stock}')
                return redirect('/epa_shop/products/')
            
            else:
                messages.error(request, 'Unknown product type.')
                return redirect('/epa_shop/products/')
            
        except Exception as e:
            messages.error(request, f'Error restocking product: {str(e)}')
            import traceback
            traceback.print_exc()
            
            # Re-render with form data preserved
            context = {
                'product': product,
                'product_type': product_type,
                'existing_units': existing_units,
                'form_units': form_units,
                'form_units_json': form_units_json,
                'page_title': f'Restock - {product.name}',
                'page_subtitle': f'Code: {product.product_code}',
                'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
            }
            return render(request, 'epa/product_restock.html', context)
    
    # ============================================
    # GET REQUEST - Show restock form
    # ============================================
    context = {
        'product': product,
        'product_type': product_type,
        'existing_units': existing_units,
        'form_units': form_units,
        'form_units_json': form_units_json,
        'submitted_quantity': submitted_quantity,
        'page_title': f'Restock - {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
    }
    return render(request, 'epa/product_restock.html', context)

# ============================================
# PRODUCT UNIT - Using Product Code
# ============================================

@login_required
def product_units(request, product_code):
    """View all units (IMEI/Serial) for a product with days since update"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    # Check permissions based on role
    if is_agent(request.user):
        # Agents can only view units they own
        owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
        if not owner or product.owner != owner:
            messages.error(request, 'You do not have permission to view units for this product.')
            return redirect('/epa_shop/products/')
    elif not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view units from other branches.')
            return redirect('/epa_shop/products/')
    
    units = []
    unit_count = 0
    available_count = 0
    sold_count = 0
    reserved_count = 0
    repair_count = 0
    
    if product_type == 'Phone':
        units = Unit.objects.filter(phone=product).select_related('phone', 'phone__branch').order_by('-created_at')
        
        # AGENT FILTER: Exclude sold units for agents
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                # Agents can only see their own units that are NOT sold
                units = units.filter(owner=owner).exclude(status='sold')
            else:
                units = units.none()
        
        unit_count = units.count()
        
        # Attach sale info and calculate days since update
        for unit in units:
            # Get the sale item for this unit
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            if sale_item:
                unit.sale = sale_item.sale
            else:
                unit.sale = None
            
            # Calculate days since last update
            if unit.updated_at:
                delta = timezone.now() - unit.updated_at
                unit.days_since_update = delta.days
            else:
                unit.days_since_update = 0
            
        # Count by status
        available_count = units.filter(status='available').count()
        sold_count = units.filter(status='sold').count()
        reserved_count = units.filter(status='reserved').count()
        repair_count = units.filter(status='repair').count()
        
    elif product_type == 'Electronic':
        units = Unit.objects.filter(electronic=product).select_related('electronic', 'electronic__branch').order_by('-created_at')
        
        # AGENT FILTER: Exclude sold units for agents
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                # Agents can only see their own units that are NOT sold
                units = units.filter(owner=owner).exclude(status='sold')
            else:
                units = units.none()
        
        unit_count = units.count()
        
        # Attach sale info and calculate days since update
        for unit in units:
            # Get the sale item for this unit
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            if sale_item:
                unit.sale = sale_item.sale
            else:
                unit.sale = None
            
            # Calculate days since last update
            if unit.updated_at:
                delta = timezone.now() - unit.updated_at
                unit.days_since_update = delta.days
            else:
                unit.days_since_update = 0
            
        # Count by status
        available_count = units.filter(status='available').count()
        sold_count = units.filter(status='sold').count()
        reserved_count = units.filter(status='reserved').count()
        repair_count = units.filter(status='repair').count()
        
    elif product_type == 'Accessory':
        messages.info(request, 'Accessories do not have individual units.')
        return redirect(f'/epa_shop/products/{product_code}/')
    
    context = {
        'product': product,
        'product_type': product_type,
        'units': units,
        'unit_count': unit_count,
        'available_count': available_count,
        'sold_count': sold_count,
        'reserved_count': reserved_count,
        'repair_count': repair_count,
        'product_code': product.product_code,
        'is_agent': is_agent(request.user),
        'page_title': f'Units - {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
    }
    return render(request, 'epa/product_units.html', context)


# ============================================
# ACCESSORY LIST - Show only Accessories
# ============================================

@login_required
def accessory_list(request):
    """List only accessories with pagination"""
    company = request.user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Get only accessories with user-based filtering
    accessories = Accessory.objects.filter(company=company, is_active=True)
    accessories = filter_by_user_access(accessories, request.user, 'product')
    accessories = accessories.order_by('-created_at')
    
    # Apply search filter
    search_query = request.GET.get('search', '')
    if search_query:
        search_lower = search_query.lower()
        accessories = accessories.filter(
            Q(name__icontains=search_lower) |
            Q(brand__icontains=search_lower) |
            Q(model__icontains=search_lower) |
            Q(product_code__icontains=search_lower) |
            Q(accessory_type__icontains=search_lower)
        )
    
    # Apply category filter
    category_filter = request.GET.get('category', '')
    if category_filter:
        accessories = accessories.filter(accessory_type=category_filter)
    
    # Get unique accessory types for filter
    accessory_types = Accessory.objects.filter(company=company, is_active=True).values_list('accessory_type', flat=True).distinct()
    accessory_types = [{'value': t, 'label': t.replace('_', ' ').title()} for t in accessory_types]
    
    # Pagination
    per_page = int(request.GET.get('per_page', 20))
    paginator = Paginator(accessories, per_page)
    page = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    context = {
        'accessories': page_obj.object_list,
        'page_obj': page_obj,
        'total_count': accessories.count(),
        'search_query': search_query,
        'category_filter': category_filter,
        'per_page': per_page,
        'accessory_types': accessory_types,
        'page_title': 'Accessories',
        'page_subtitle': 'Manage your accessories',
    }
    return render(request, 'epa/accessory_list.html', context)