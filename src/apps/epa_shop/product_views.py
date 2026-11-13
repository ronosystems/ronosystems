from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q, Count, Sum
from decimal import Decimal
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from apps.company.models import Branch
from .models import Electronic, Phone, Accessory, Category, Supplier, Unit, Sale, SaleItem, Customer, Owner
from django.contrib.auth import get_user_model
from .utils import record_stock_movement
from django.http import Http404
from django.db import transaction
from django.views.decorators.http import require_POST
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)
import json
import os
import time
import cloudinary
import cloudinary.uploader
from django.conf import settings
import csv
from django.http import HttpResponse
import openpyxl
from openpyxl.styles import Font, PatternFill




User = get_user_model()



def _cloudinary_configure():
    """Match accounts.profile_picture_upload's config pattern."""
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def _upload_product_image_to_cloudinary(uploaded_file, folder='epa/products'):
    """
    Upload to Cloudinary and return the public_id, mirroring the
    accounts.profile_picture_upload pattern. Returns None on failure.
    """
    if not uploaded_file:
        return None

    try:
        _cloudinary_configure()

        # Unique public_id per upload, same idea as profiles
        base = f"{folder}/p_{int(time.time() * 1000)}"

        result = cloudinary.uploader.upload(
            uploaded_file,
            public_id=base,
            overwrite=False,
            resource_type='image',
        )
        public_id = result.get('public_id') or base
        print(f"✅ Cloudinary upload OK: {public_id}")
        return public_id
    except Exception as e:
        import traceback
        print(f"❌ Cloudinary upload FAILED: {e}")
        traceback.print_exc()
        return None



# ============================================
# BARCODE / LABEL IMPORT
# ============================================

from django.http import FileResponse, Http404
from .barcode_utils import (
    build_label_pdf,
    build_label_sheet_pdf,
    generate_barcode_image,
)


PRODUCT_KIND_MODELS = {
    'phone':      Phone,
    'electronic': Electronic,
    'accessory':  Accessory,
}



# ============================================
# HELPER FUNCTION - Get product by code
# ============================================

def get_product_by_code(company, product_code):
    """Get a product by its product code across all models"""
    try:
        product = Phone.objects.get(company=company, product_code=product_code)
        return product, 'Phone'
    except Phone.DoesNotExist:
        pass
    
    try:
        product = Electronic.objects.get(company=company, product_code=product_code)
        return product, 'Electronic'
    except Electronic.DoesNotExist:
        pass
    
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
    """Check if user is super admin, company admin, or stock controller"""
    return user.role in ['super_admin', 'company_admin', 'stock_controller']


def is_cashier(user):
    """Check if user is a cashier"""
    return user.role == 'company_cashier'


def is_agent(user):
    """Check if user is an agent"""
    return user.role == 'company_agent'


def is_staff(user):
    """Check if user is staff"""
    return user.role == 'company_staff'


def is_stock_controller(user):
    """Check if user is a stock controller"""
    return user.role == 'stock_controller'


def get_user_branch(user):
    """Get the user's branch"""
    return user.branch if user else None


def get_user_owned_units(user):
    """Get units owned by the user (for agents)"""
    if not user:
        return []
    owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
    if owner:
        return Unit.objects.filter(owner=owner).values_list('id', flat=True)
    return []


def filter_by_user_access(queryset, user, model_type='product'):
    """Filter queryset based on user's role"""
    if not user:
        return queryset
    
    if is_admin_or_manager(user):
        return queryset
    
    user_branch = get_user_branch(user)
    
    if is_cashier(user):
        if user_branch:
            return queryset
        return queryset
    
    if is_agent(user):
        owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
        if owner:
            return queryset.filter(owner=owner)
        return queryset.none()
    
    if is_staff(user):
        if user_branch:
            return queryset
        return queryset
    
    return queryset

def filter_units_by_user_access(units_queryset, user):
    """Filter units based on user's role"""
    if not user:
        return units_queryset
    
    if is_admin_or_manager(user):
        return units_queryset
    
    user_branch = get_user_branch(user)
    
    if is_cashier(user) or is_staff(user):
        if user_branch:
            # 👇 CHANGED: Filter by the Unit's branch, not the Phone's branch
            return units_queryset.filter(branch=user_branch)
        return units_queryset
    
    if is_agent(user):
        owner = Owner.objects.filter(company=user.company, phone=user.phone).first()
        if owner:
            return units_queryset.filter(owner=owner, status='available')
        return units_queryset.none()
    
    return units_queryset

def filter_sales_by_user_access(sales_queryset, user):
    """Filter sales based on user's role"""
    if not user:
        return sales_queryset
    
    if is_admin_or_manager(user):
        return sales_queryset
    
    user_branch = get_user_branch(user)
    
    if is_cashier(user):
        if user_branch:
            return sales_queryset.filter(branch=user_branch)
        return sales_queryset
    
    if is_agent(user):
        return sales_queryset.filter(sold_by=user)
    
    if is_staff(user):
        if user_branch:
            return sales_queryset.filter(branch=user_branch)
        return sales_queryset
    
    return sales_queryset


def get_or_create_owner_from_user(user, company=None):
    """
    Get or create an Owner record from a User.
    
    Args:
        user: The user to create the owner from
        company: The company to assign the owner to (required for super admin in support mode)
    
    Returns:
        Owner instance or None
    """
    if not user:
        return None
    
    # Determine which company to use (support mode aware)
    effective_company = company or user.company
    
    if not effective_company:
        print(f"⚠️ Warning: Cannot create Owner - no company for user {user.username}")
        return None
    
    # Use phone OR username as the identifier
    identifier = user.phone or user.username
    
    # Check if user already has an owner record for this company
    owner = Owner.objects.filter(
        company=effective_company,
        phone=identifier
    ).first()
    
    if owner:
        return owner
    
    # Create owner from user data
    try:
        owner = Owner.objects.create(
            company=effective_company,
            name=user.get_full_name() or user.username,
            phone=user.phone or '',
            email=user.email or '',
            is_active=True
        )
        print(f"✅ Created Owner '{owner.name}' for company '{effective_company.name}'")
        return owner
    except Exception as e:
        print(f"❌ Failed to create Owner: {e}")
        return None


# ============================================
# ALL UNITS VIEW - Phones + Electronics
# ============================================

@login_required
def all_units_combined(request):
    """View all units (both phones and electronics) in one page."""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # 1. Fetch BOTH phones and electronics
    units = Unit.objects.filter(
        Q(phone__company=company) | Q(electronic__company=company)
    ).select_related('phone', 'electronic', 'branch').order_by('-created_at')
    
    if not is_viewing_company:
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner, status='available')
            else:
                units = units.none()
        else:
            units = filter_units_by_user_access(units, request.user)
    
    for unit in units:
        if unit.updated_at:
            delta = timezone.now() - unit.updated_at
            unit.days_since_update = delta.days
        else:
            unit.days_since_update = 0

        # Attach sale if it exists (for the Sold tab)
        sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
        unit.sale = sale_item.sale if sale_item else None
    
    total_units = units.count()
    available_units = units.filter(status='available').count()
    sold_units = units.filter(status='sold').count()
    reserved_units = units.filter(status='reserved').count()
    repair_units = units.filter(status='repair').count()
    
    # 👇 FETCH BRANCHES FOR THE DROPDOWN
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    
    context = {
        'units': units,
        'branches': branches,       # 👈 Added this line
        'unit_type': 'Combined',
        'unit_label': 'Identifier',
        'total_units': total_units,
        'available_units': available_units,
        'sold_units': sold_units,
        'reserved_units': reserved_units,
        'repair_units': repair_units,
        'is_agent': is_agent(request.user) and not is_viewing_company,
        'page_title': 'All Units',
        'page_subtitle': 'All IMEIs and Serial numbers combined',
    }
    return render(request, 'epa/all_units.html', context)

# ============================================
# UNIT EDIT - Inline Edit
# ============================================

@login_required
def unit_edit(request, unit_id):
    """Edit a unit's details (IMEI/Serial number)"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
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
    
    # Check permissions (skip in support mode)
    if not is_viewing_company:
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if not owner or unit.owner != owner:
                messages.error(request, 'You do not have permission to edit this unit.')
                return redirect('/epa_shop/products/')
        elif not is_admin_or_manager(request.user) and not is_cashier(request.user):
            user_branch = get_user_branch(request.user)
            product_branch = product.branch if product else None
            if user_branch and product_branch and product_branch.id != user_branch.id:
                messages.error(request, 'You do not have permission to edit units from other branches.')
                return redirect('/epa_shop/products/')
    
    # Get company employees
    employees = User.objects.filter(company=company, is_active=True)
    if not is_admin_or_manager(request.user) and not is_viewing_company:
        user_branch = get_user_branch(request.user)
        if user_branch:
            employees = employees.filter(branch=user_branch)
    employees = employees.order_by('first_name', 'last_name')
    
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
            
            if owner_id:
                try:
                    user = User.objects.get(id=owner_id, company=company)
                    owner = get_or_create_owner_from_user(user, company=company)
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
            
            if status == 'available':
                if unit.phone:
                    available_count = Unit.objects.filter(phone=product, status='available').count()
                    product.total_quantity_in_stock = available_count
                    product.save()
                elif unit.electronic:
                    available_count = Unit.objects.filter(electronic=product, status='available').count()
                    product.total_quantity_in_stock = available_count
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
    """Transfer unit ownership to an employee"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    unit = get_object_or_404(Unit, id=unit_id)
    
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
    
    if not is_viewing_company:
        if is_agent(request.user):
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
    
    if unit.status not in ['available', 'reserved']:
        messages.error(request, 'Only available or reserved units can be transferred.')
        return redirect(f'/epa_shop/products/{product.product_code}/units/')
    
    employees = User.objects.filter(company=company, is_active=True)
    if not is_admin_or_manager(request.user) and not is_viewing_company:
        user_branch = get_user_branch(request.user)
        if user_branch:
            employees = employees.filter(branch=user_branch)
    employees = employees.order_by('first_name', 'last_name')
    
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
                owner = get_or_create_owner_from_user(user, company=company)
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
            
            unit.owner = owner
            unit.owner_name = owner.name
            unit.owner_phone = owner.phone
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
# UNIT REVERSE SALE
# ============================================

@login_required
def unit_reverse_sale(request, sale_id):
    """Reverse a sale and return items to inventory."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # --- Resolve sale by pk OR company_sale_id ---
    sale = None
    if str(sale_id).isdigit():
        sale = Sale.objects.filter(id=int(sale_id), company=company).first()
    if not sale:
        sale = Sale.objects.filter(company_sale_id=sale_id, company=company).first()
    if not sale:
        raise Http404(f'Sale "{sale_id}" not found.')

    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or
        request.user.is_company_manager or
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )

    if not is_authorized:
        messages.error(request, 'Only admins and managers can reverse sales.')
        return redirect('/epa_shop/sales/')

    next_url = request.GET.get('next', '/epa_shop/units/phones/')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Lock the sale row so double-clicks can't double-restock
                locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)

                if locked_sale.payment_status == 'refunded':
                    messages.error(request, 'This sale has already been reversed.')
                    return redirect(next_url)

                # REMOVED 'item' FROM select_related
                sale_items = SaleItem.objects.filter(sale=locked_sale).select_related('unit')
                reversed_count = 0

                for sale_item in sale_items:
                    # Force qty to be an integer — default to 1 if None or 0
                    qty = sale_item.quantity
                    if not qty or qty <= 0:
                        qty = 1

                    # --- A. Handle Units (Phones/Electronics) ---
                    if sale_item.unit:
                        unit = sale_item.unit
                        unit.status = 'available'
                        unit.owner_name = ''
                        unit.owner_phone = ''
                        unit.sold_date = None
                        unit.save()

                    # --- B. Restock Product (Phones, Electronics AND Accessories) ---
                    product = sale_item.item
                    if product:
                        previous_quantity = product.total_quantity_in_stock
                        product.total_quantity_in_stock += qty
                        product.save()

                        # --- C. Record Stock Movement ---
                        record_stock_movement(
                            product=product,
                            movement_type='return',
                            quantity=qty,
                            previous_quantity=previous_quantity,
                            new_quantity=product.total_quantity_in_stock,
                            branch=locked_sale.branch,
                            unit=sale_item.unit,
                            notes=f'Sale reversed - returned to inventory (Sale #{locked_sale.company_sale_id})',
                            performed_by=request.user
                        )

                    reversed_count += 1

                # Mark the sale as refunded
                locked_sale.payment_status = 'refunded'
                locked_sale.save(update_fields=['payment_status'])

            messages.success(request, f'Sale #{sale.company_sale_id} reversed successfully! {reversed_count} item(s) returned to inventory.')
            return redirect(next_url)

        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f'ERROR: {str(e)}')
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
# SALE RECEIPT
# ============================================

@login_required
def sale_receipt(request, sale_id):
    """View sale receipt"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    sale = get_object_or_404(Sale, id=sale_id, company=company)
    
    if not is_viewing_company:
        if is_agent(request.user):
            if sale.sold_by != request.user:
                messages.error(request, 'You do not have permission to view this receipt.')
                return redirect('/epa_shop/sales/')
        elif not is_admin_or_manager(request.user):
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
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    units = Unit.objects.filter(
        phone__company=company,
        phone__is_active=True
    ).select_related('phone', 'branch').order_by('-created_at')
    
    if not is_viewing_company:
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner, status='available')
            else:
                units = units.none()
        else:
            units = filter_units_by_user_access(units, request.user)
    
    for unit in units:
        if unit.updated_at:
            delta = timezone.now() - unit.updated_at
            unit.days_since_update = delta.days
        else:
            unit.days_since_update = 0

        # Attach sale data
        sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
        unit.sale = sale_item.sale if sale_item else None
    
    total_units = units.count()
    available_units = units.filter(status='available').count()
    sold_units = units.filter(status='sold').count()
    reserved_units = units.filter(status='reserved').count()
    repair_units = units.filter(status='repair').count()
    
    # 👇 FETCH BRANCHES FOR THE DROPDOWN
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    
    context = {
        'units': units,
        'branches': branches,       # 👈 Added
        'unit_type': 'Phone',
        'unit_label': 'IMEI',
        'total_units': total_units,
        'available_units': available_units,
        'sold_units': sold_units,
        'reserved_units': reserved_units,
        'repair_units': repair_units,
        'is_agent': is_agent(request.user) and not is_viewing_company,
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
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    units = Unit.objects.filter(
        electronic__company=company,
        electronic__is_active=True
    ).select_related('electronic', 'branch').order_by('-created_at')
    
    if not is_viewing_company:
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner, status='available')
            else:
                units = units.none()
        else:
            units = filter_units_by_user_access(units, request.user)
    
    for unit in units:
        if unit.updated_at:
            delta = timezone.now() - unit.updated_at
            unit.days_since_update = delta.days
        else:
            unit.days_since_update = 0

        # Attach sale data
        sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
        unit.sale = sale_item.sale if sale_item else None
    
    total_units = units.count()
    available_units = units.filter(status='available').count()
    sold_units = units.filter(status='sold').count()
    reserved_units = units.filter(status='reserved').count()
    repair_units = units.filter(status='repair').count()
    
    # 👇 FETCH BRANCHES FOR THE DROPDOWN
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    
    context = {
        'units': units,
        'branches': branches,       # 👈 Added
        'unit_type': 'Electronic',
        'unit_label': 'Serial',
        'total_units': total_units,
        'available_units': available_units,
        'sold_units': sold_units,
        'reserved_units': reserved_units,
        'repair_units': repair_units,
        'is_agent': is_agent(request.user) and not is_viewing_company,
        'page_title': 'Electronic Units (Serial)',
        'page_subtitle': 'All serial numbers across all electronic products',
    }
    return render(request, 'epa/all_units.html', context)


# ============================================
# UNIT DELETE
# ============================================

@login_required
def unit_delete(request, product_code, identifier):
    """Delete a specific IMEI/Serial unit using product code"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    unit = get_object_or_404(Unit, identifier=identifier)
    
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
    
    if not is_viewing_company:
        if is_agent(request.user):
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
    
    if product.product_code != product_code:
        messages.error(request, 'Product code mismatch.')
        return redirect('/epa_shop/products/')
    
    if request.method == 'POST':
        identifier_value = unit.identifier
        product_code_value = product.product_code
        product_type_value = product_type
        
        unit.delete()
        
        if product.total_quantity_in_stock > 0:
            product.total_quantity_in_stock -= 1
            product.save()
        
        messages.success(request, f'Unit "{identifier_value}" removed successfully!')
        
        if product_type_value == 'Phone':
            return redirect('/epa_shop/units/phones/')
        elif product_type_value == 'Electronic':
            return redirect('/epa_shop/units/electronics/')
        else:
            return redirect(f'/epa_shop/products/{product_code_value}/')
    
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
# SCANNER LOOKUP - Find product by IMEI/Serial/Barcode
# ============================================

@login_required
def scanner_lookup(request):
    """
    AJAX endpoint for barcode scanner.
    Accepts: ?q=<scanned_value>
    Returns JSON with product info if found.
    
    Search priority:
      1. Exact match on Unit.identifier (IMEI/Serial)
      2. Exact match on product barcode
      3. Exact match on product_code
      4. Fallback: name/brand/model contains
    """
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({
            'success': False,
            'error': 'No active company selected.'
        }, status=400)
    
    query = (request.GET.get('q') or '').strip()
    if not query:
        return JsonResponse({
            'success': False,
            'error': 'No search value provided.'
        }, status=400)
    
    # ---------- 1. Look up as a Unit (IMEI/Serial) ----------
    unit = Unit.objects.filter(identifier__iexact=query).select_related(
        'phone', 'electronic', 'owner'
    ).first()
    
    if unit:
        product = unit.phone or unit.electronic
        if product and product.company_id == company.id:
            # Permission check (skip in support mode)
            if not is_viewing_company:
                if is_agent(request.user):
                    owner = Owner.objects.filter(
                        company=company, phone=request.user.phone
                    ).first()
                    if not owner or unit.owner != owner:
                        return JsonResponse({
                            'success': False,
                            'error': 'You do not have permission to view this unit.'
                        }, status=403)
            
            product_type = 'Phone' if unit.phone else 'Electronic'
            
            # Find any sale this unit belongs to
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            
            return JsonResponse({
                'success': True,
                'match_type': 'unit',
                'unit': {
                    'id': unit.id,
                    'identifier': unit.identifier,
                    'unit_type': unit.unit_type,
                    'status': unit.status,
                    'owner_name': unit.owner_name or (unit.owner.name if unit.owner else ''),
                    'owner_phone': unit.owner_phone or (unit.owner.phone if unit.owner else ''),
                },
                'product': {
                    'id': product.id,
                    'pk': product.id,                        # 👈 ADD
                    'kind': 'phone' if unit.phone else 'electronic',   # 👈 ADD
                    'product_code': product.product_code,
                    'name': product.name,
                    'brand': getattr(product, 'brand', ''),
                    'model': getattr(product, 'model', None) or getattr(product, 'model_number', ''),
                    'type': product_type,
                    'stock': product.total_quantity_in_stock,
                    'selling_price': float(product.selling_price),
                    'best_price': float(product.best_price) if product.best_price else 0,
                    'purchase_price': float(product.purchase_price),
                    'image': product.image_url,
                    'detail_url': f'/epa_shop/products/{product.product_code}/',
                    'units_url': f'/epa_shop/products/{product.product_code}/units/',
                },
                'sale': {
                    'id': sale_item.sale.id,
                    'company_sale_id': sale_item.sale.company_sale_id,
                    'sale_date': sale_item.sale.sale_date.isoformat(),
                } if sale_item else None,
            })
    
    # ---------- 2. Look up as a product barcode / product_code ----------
    product = None
    product_type = None
    
    # Try barcode first (if field exists)
    for model_cls, type_label in [
        (Phone, 'Phone'),
        (Electronic, 'Electronic'),
        (Accessory, 'Accessory'),
    ]:
        # Check barcode field exists before querying
        if hasattr(model_cls, 'barcode'):
            obj = model_cls.objects.filter(
                company=company, barcode__iexact=query
            ).first()
            if obj:
                product = obj
                product_type = type_label
                break
    
    # Fall back to product_code
    if not product:
        product, product_type = get_product_by_code(company, query)
    
    if product:
        # Permission check
        if not is_viewing_company:
            if is_agent(request.user):
                owner = Owner.objects.filter(
                    company=company, phone=request.user.phone
                ).first()
                if not owner or getattr(product, 'owner', None) != owner:
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have permission to view this product.'
                    }, status=403)
            elif not is_admin_or_manager(request.user):
                user_branch = get_user_branch(request.user)
                product_branch = getattr(product, 'branch', None)
                if user_branch and product_branch and product_branch.id != user_branch.id:
                    return JsonResponse({
                        'success': False,
                        'error': 'Product belongs to a different branch.'
                    }, status=403)
        
        return JsonResponse({
            'success': True,
            'match_type': 'product',
            'product': {
                'id': product.id,
                'pk': product.id,                        # 👈 ADD
                'kind': product_type.lower(),            # 👈 ADD ('phone' / 'electronic' / 'accessory')
                'product_code': product.product_code,
                'name': product.name,
                'brand': getattr(product, 'brand', ''),
                'model': getattr(product, 'model', None) or getattr(product, 'model_number', ''),
                'type': product_type,
                'stock': product.total_quantity_in_stock,
                'selling_price': float(product.selling_price),
                'best_price': float(product.best_price) if product.best_price else 0,
                'purchase_price': float(product.purchase_price),
                'image': product.image_url, # 👈 ADD THIS LINE
                'detail_url': f'/epa_shop/products/{product.product_code}/',
                'units_url': f'/epa_shop/products/{product.product_code}/units/',
            },
            'unit': None,
            'sale': None,
        })
    
    # ---------- 3. Not found ----------
    return JsonResponse({
        'success': False,
        'error': f'No product or unit found for "{query}".',
        'query': query,
    }, status=404)


# ============================================
# PRODUCT LIST WITH PAGINATION
# ============================================

@login_required
def product_list(request):
    """List all products with proper data from database."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # ---------- Role flags ----------
    is_admin = is_admin_or_manager(request.user) or is_viewing_company
    user_branch = get_user_branch(request.user)

    # ---------- Branch Filter Logic ----------
    branch_id = request.GET.get('branch', '').strip()
    selected_branch = None
    if branch_id and branch_id.isdigit():
        selected_branch = Branch.objects.filter(id=int(branch_id), company=company).first()

    # If no specific branch selected, but user is restricted (cashier/staff), force their branch
    if not selected_branch and not is_admin and user_branch:
        selected_branch = user_branch

    all_products = []

    # Helper to get AVAILABLE stock for the selected branch (or company-wide if none)
    def get_stock(product, product_type):
        if selected_branch:
            if product_type in ['Phone', 'Electronic']:
                if product_type == 'Phone':
                    return Unit.objects.filter(
                        phone=product, branch=selected_branch, status='available'
                    ).count()
                else:
                    return Unit.objects.filter(
                        electronic=product, branch=selected_branch, status='available'
                    ).count()
            else:
                stock_obj = product.stock_at(selected_branch)
                return stock_obj.quantity_in_stock if stock_obj else 0
        else:
            if product_type in ['Phone', 'Electronic']:
                if product_type == 'Phone':
                    return Unit.objects.filter(phone=product, status='available').count()
                else:
                    return Unit.objects.filter(electronic=product, status='available').count()
            else:
                return product.total_quantity_in_stock

    # ---------- Electronics ----------
    electronics = Electronic.objects.filter(company=company)
    for item in electronics:
        stock = get_stock(item, 'Electronic')
        total_units = Unit.objects.filter(electronic=item).count()

        all_products.append({
            'id': item.id,
            'pk': item.id,
            'kind': 'electronic',
            'product_code': item.product_code or '-',
            'display_id': item.product_code or f"E{item.id}",
            'name': item.name,
            'type': 'Electronic',
            'brand': item.brand or '-',
            'model': item.model_number or '-',
            'specs': f"{item.ram} {item.storage}".strip() or '-',
            'stock': stock,
            'all_units': total_units,
            'purchase_price': float(item.purchase_price),
            'selling_price': float(item.selling_price),
            'best_price': float(item.best_price) if item.best_price else 0,
            'is_active': item.is_active,
            'created_at': item.created_at.isoformat() if item.created_at else None,
        })

    # ---------- Phones ----------
    phones = Phone.objects.filter(company=company)
    for item in phones:
        stock = get_stock(item, 'Phone')
        
        phone_type = 'Smartphone'
        if hasattr(item, 'phone_type'):
            phone_type = 'Feature Phone' if item.phone_type == 'feature' else 'Smartphone'
        else:
            ram_empty = not item.ram or item.ram in ('N/A', '')
            rom_empty = not item.storage_capacity or item.storage_capacity in ('N/A', '')
            phone_type = 'Feature Phone' if (ram_empty and rom_empty) else 'Smartphone'

        total_units = Unit.objects.filter(phone=item).count()

        all_products.append({
            'id': item.id,
            'pk': item.id,
            'kind': 'phone',
            'product_code': item.product_code or '-',
            'display_id': item.product_code or f"P{item.id}",
            'name': item.name,
            'type': phone_type,
            'brand': item.brand or '-',
            'model': item.model or '-',
            'specs': f"{item.ram} {item.storage_capacity}".strip() or '-',
            'stock': stock,
            'all_units': total_units,
            'purchase_price': float(item.purchase_price),
            'selling_price': float(item.selling_price),
            'best_price': float(item.best_price) if item.best_price else 0,
            'is_active': item.is_active,
            'created_at': item.created_at.isoformat() if item.created_at else None,
        })

    # ---------- Accessories ----------
    accessories = Accessory.objects.filter(company=company)
    for item in accessories:
        stock = get_stock(item, 'Accessory')

        all_products.append({
            'id': item.id,
            'pk': item.id,
            'kind': 'accessory',
            'product_code': item.product_code or '-',
            'display_id': item.product_code or f"A{item.id}",
            'name': item.name,
            'type': 'Accessory',
            'brand': item.brand or '-',
            'model': item.model or '-',
            'specs': item.accessory_type or '-',
            'stock': stock,
            'all_units': stock,
            'purchase_price': float(item.purchase_price),
            'selling_price': float(item.selling_price),
            'best_price': float(item.best_price) if item.best_price else 0,
            'is_active': item.is_active,
            'created_at': item.created_at.isoformat() if item.created_at else None,
        })

    # Sort by created_at descending (newest first)
    all_products.sort(key=lambda x: x['created_at'] or '', reverse=True)

    # ============================================================
    # STATS
    # ============================================================
    total_products = len(all_products)

    phone_ids = [p['id'] for p in all_products if p['type'] in ('Smartphone', 'Feature Phone')]
    electronic_ids = [p['id'] for p in all_products if p['type'] == 'Electronic']

    total_unit_items = 0
    if phone_ids:
        total_unit_items += Unit.objects.filter(phone_id__in=phone_ids, status='available').count()
    if electronic_ids:
        total_unit_items += Unit.objects.filter(electronic_id__in=electronic_ids, status='available').count()

    total_stock_items = sum(int(p.get('stock') or 0) for p in all_products)
    total_products_value = sum(
        (float(p.get('selling_price') or 0) * int(p.get('stock') or 0))
        for p in all_products
    )

    stats = {
        'total_products':       total_products,
        'total_unit_items':     total_unit_items,
        'total_stock_items':    total_stock_items,
        'total_products_value': total_products_value,
    }

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    context = {
        'all_products_json':  all_products,
        'total_count':        len(all_products),
        'stats':              stats,
        'is_admin':           is_admin,
        'user_role':          request.user.role,
        'is_viewing_company': is_viewing_company,
        'branches':           branches,
        'selected_branch':    selected_branch,
        'branch_id':          str(selected_branch.id) if selected_branch else '',
        'page_title':         'Products',
        'page_subtitle':      'Manage your products',
    }
    return render(request, 'epa/products.html', context)

    
@login_required
@require_POST
def update_product_prices(request, product_code):
    """AJAX endpoint to update prices directly from the product detail page."""
    company, is_viewing_company = get_active_company(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No active company'})

    product, _ = get_product_by_code(company, product_code)
    if not product:
        return JsonResponse({'success': False, 'error': 'Product not found'})

    try:
        purchase_price = request.POST.get('purchase_price')
        selling_price = request.POST.get('selling_price')
        best_price = request.POST.get('best_price')

        if purchase_price:
            product.purchase_price = Decimal(purchase_price)
        if selling_price:
            product.selling_price = Decimal(selling_price)
        if best_price:
            product.best_price = Decimal(best_price)
        elif best_price == '':
            product.best_price = None

        product.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# ============================================
# PRODUCT DETAIL
# ============================================

@login_required
def product_detail(request, product_code):
    """View product details using product code"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    product, product_type = get_product_by_code(company, product_code)

    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')

    if not is_viewing_company:
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if not owner or getattr(product, 'owner', None) != owner:
                messages.error(request, 'You do not have permission to view this product.')
                return redirect('/epa_shop/products/')
        elif not is_admin_or_manager(request.user):
            user_branch = get_user_branch(request.user)
            if user_branch:
                if not product.branch_stocks.filter(branch=user_branch).exists():
                    messages.error(request, 'You do not have permission to view products from other branches.')
                    return redirect('/epa_shop/products/')

    # 1. Determine the selected branch
    all_branches_qs = Branch.objects.filter(company=company, is_active=True)
    branch_id = request.GET.get('branch')
    selected_branch = None
    if branch_id and branch_id.isdigit():
        selected_branch = all_branches_qs.filter(id=int(branch_id)).first()
    if not selected_branch and all_branches_qs.exists():
        selected_branch = all_branches_qs.first()

    # 2. Load units for the selected branch
    units = []
    total_units = 0
    available_count = 0
    reserved_count = 0
    repair_count = 0
    sold_count = 0

    if selected_branch and product_type in ['Phone', 'Electronic']:
        if product_type == 'Phone':
            units = Unit.objects.filter(phone=product, branch=selected_branch).order_by('-created_at')
        else:
            units = Unit.objects.filter(electronic=product, branch=selected_branch).order_by('-created_at')

        if is_agent(request.user) and not is_viewing_company:
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner)
            else:
                units = units.none()

        # Counts for the summary cards at the top
        total_units = units.count()
        available_count = units.filter(status='available').count()
        reserved_count = units.filter(status='reserved').count()
        repair_count = units.filter(status='repair').count()
        sold_count = units.filter(status='sold').count()

        for unit in units:
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            unit.sale = sale_item.sale if sale_item else None

    # Accessories use the BranchStock record for the count
    if product_type == 'Accessory' and selected_branch:
        stock_obj = product.stock_at(selected_branch)
        total_units = stock_obj.quantity_in_stock if stock_obj else 0

    # 3. Branch stock data — always compute live for phones/electronics
    branches = all_branches_qs
    if is_agent(request.user) and not is_viewing_company:
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)
    elif not is_admin_or_manager(request.user) and not is_viewing_company:
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)

    branch_stock_data = []
    actual_total_stock = 0

    for branch in branches:
        if product_type in ['Phone', 'Electronic']:
            # ✅ Count live available units per branch — not the cached total
            if product_type == 'Phone':
                live_count = Unit.objects.filter(
                    phone=product, branch=branch, status='available'
                ).count()
            else:
                live_count = Unit.objects.filter(
                    electronic=product, branch=branch, status='available'
                ).count()
        else:
            # Accessories still use BranchStock
            stock_obj = product.stock_at(branch)
            live_count = stock_obj.quantity_in_stock if stock_obj else 0

        actual_total_stock += live_count

        branch_stock_data.append({
            'id': branch.id,
            'name': branch.name,
            'code': branch.code,
            'unit_count': live_count,
            'address': branch.address,
            'phone': branch.phone,
            'has_units': live_count > 0,
            'is_primary': live_count > 0,
        })

    branch_stock_data.sort(key=lambda x: (not x['is_primary'], -x['unit_count']))

    # Current branch stock — pull from the live branch data
    current_branch_stock = 0
    if selected_branch:
        for b in branch_stock_data:
            if b['id'] == selected_branch.id:
                current_branch_stock = b['unit_count']
                break

    context = {
        'product': product,
        'product_type': product_type,
        'units': units,
        'unit_count': total_units,
        'available_count': available_count,
        'reserved_count': reserved_count,
        'repair_count': repair_count,
        'sold_count': sold_count,
        'branches': branch_stock_data,
        'total_available_units': actual_total_stock,
        'actual_total_stock': actual_total_stock,
        'current_branch_stock': current_branch_stock,
        'product_code': product.product_code,
        'is_viewing_company': is_viewing_company,
        'selected_branch_id': selected_branch.id if selected_branch else None,
        'page_title': f'Product: {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
    }
    return render(request, 'epa/product_detail.html', context)


# ============================================
# PRODUCT CREATE
# ============================================

@login_required
def product_create(request):
    """Create a new product - checks for duplicates first"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # Only super admin, company admin, and stock controllers can create products
    if not is_admin_or_manager(request.user) and not is_viewing_company:
        messages.error(request, 'You do not have permission to create products. Only administrators and stock controllers can manage products.')
        return redirect('/epa_shop/products/')

    # Filter branches
    branches = Branch.objects.filter(company=company, is_active=True)
    if not is_viewing_company and not request.user.is_super_admin and not request.user.is_company_admin:
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)

    form_data = {}
    category_value = ''
    units_json = '[]'
    units = []

    if request.method == 'POST':
        try:
            category_type = request.POST.get('category', '').strip()
            branch_id = request.POST.get('branch')  # Now read from Section 4
            name = request.POST.get('name', '').strip()
            brand = request.POST.get('brand', '').strip()
            model = request.POST.get('model', '').strip()

            # --- Handle list fields safely (RAM, ROM, etc.) ---
            ram_list = request.POST.getlist('ram')
            ram = next((val.strip() for val in ram_list if val and val.strip()), '')

            rom_list = request.POST.getlist('rom')
            rom = next((val.strip() for val in rom_list if val and val.strip()), '')

            storage_list = request.POST.getlist('storage')
            storage = next((val.strip() for val in storage_list if val and val.strip()), '')

            if category_type == 'electronics' and not storage:
                for val in rom_list:
                    if val and val.strip():
                        storage = val.strip()
                        break

            screen_size = next((val.strip() for val in request.POST.getlist('screen_size') if val and val.strip()), '')
            color = next((val.strip() for val in request.POST.getlist('color') if val and val.strip()), '')
            battery_capacity = next((val.strip() for val in request.POST.getlist('battery_capacity') if val and val.strip()), '')

            condition = request.POST.get('condition', 'new')
            network_type = request.POST.get('network_type', '').strip()
            memory_card = request.POST.get('memory_card', 'no')
            features = request.POST.get('features', '').strip()
            device_type = request.POST.get('device_type', 'other')
            processor = request.POST.get('processor', '').strip()
            accessory_type = request.POST.get('accessory_type', 'other')
            
            barcode = request.POST.get('barcode', '').strip() or None

            image = request.FILES.get('product_image')

            # --- Upload to Cloudinary ---
            if category_type in ('smartphone', 'feature_phone'):
                _folder_root = 'epa/phones'
            elif category_type == 'electronics':
                _folder_root = 'epa/electronics'
            elif category_type == 'accessory':
                _folder_root = 'epa/accessories'
            else:
                _folder_root = 'epa/products'

            image_public_id = _upload_product_image_to_cloudinary(
                image,
                folder=f"{_folder_root}/{timezone.now().strftime('%Y/%m')}",
            )

            if image and not image_public_id:
                messages.error(request, 'Image upload failed. Please try again or check Cloudinary credentials.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches,
                    'form_data': request.POST,
                    'category_value': request.POST.get('category', ''),
                    'units': [],
                    'units_json': '[]',
                    'is_edit': False,
                    'page_title': 'Add Product',
                    'page_subtitle': 'Create a new product',
                })

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

            # ------------------------------------------------------------
            # VALIDATIONS
            # ------------------------------------------------------------
            if not category_type:
                messages.error(request, 'Please select a category.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            if not brand:
                messages.error(request, 'Brand is required.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            if not model:
                messages.error(request, 'Model is required.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            if not branch_id:
                messages.error(request, 'Please select a branch in the Stock section to assign this inventory.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            try:
                branch = Branch.objects.get(id=branch_id, company=company, is_active=True)
            except Branch.DoesNotExist:
                messages.error(request, 'Selected branch is invalid or inactive.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            if purchase_price <= 0:
                messages.error(request, 'Buying price must be greater than 0.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            if selling_price <= 0:
                messages.error(request, 'Selling price must be greater than 0.')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            # Category-specific validations
            if category_type == 'smartphone':
                if not ram:
                    messages.error(request, 'RAM is required for smartphones.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})
                if not rom:
                    messages.error(request, 'Storage (ROM) is required for smartphones.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})

            elif category_type == 'electronics':
                if not ram:
                    messages.error(request, 'RAM is required for electronics.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})
                if not storage:
                    messages.error(request, 'Storage is required for electronics.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})
                if not processor:
                    messages.error(request, 'Processor is required for electronics.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})

            elif category_type == 'accessory':
                if not accessory_type or accessory_type == '':
                    messages.error(request, 'Accessory type is required.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})
                if quantity <= 0:
                    messages.error(request, 'Quantity must be greater than 0 for accessories.')
                    return render(request, 'epa/product_form.html', {'branches': branches, 'form_data': request.POST, 'category_value': category_type, 'units': units, 'units_json': '[]', 'is_edit': False, 'page_title': 'Add Product', 'page_subtitle': 'Create a new product'})

            units_data = request.POST.get('units', '[]')
            try:
                units = json.loads(units_data)
            except:
                units = []

            # ------------------------------------------------------------
            # Check for existing product (duplicate detection)
            # ------------------------------------------------------------
            existing_product = None
            existing_product_type = None

            if category_type in ['smartphone', 'feature_phone']:
                existing_phones = Phone.objects.filter(
                    company=company, brand__iexact=brand, model__iexact=model,
                    ram=ram, storage_capacity=rom, is_active=True
                )
                if existing_phones.exists():
                    existing_product = existing_phones.first()
                    existing_product_type = 'Phone'

            elif category_type == 'electronics':
                existing_electronics = Electronic.objects.filter(
                    company=company, brand__iexact=brand, model_number__iexact=model,
                    ram=ram, storage=storage, processor=processor, is_active=True
                )
                if existing_electronics.exists():
                    existing_product = existing_electronics.first()
                    existing_product_type = 'Electronic'

            elif category_type == 'accessory':
                existing_accessories = Accessory.objects.filter(
                    company=company, brand__iexact=brand, model__iexact=model,
                    accessory_type=accessory_type, is_active=True
                )
                if existing_accessories.exists():
                    existing_product = existing_accessories.first()
                    existing_product_type = 'Accessory'

            # If existing, add stock to this specific branch via services
            if existing_product and existing_product_type:
                from apps.epa_shop.services.stock import receive_stock
                
                added_count = 0
                skipped_count = 0

                if existing_product_type in ['Phone', 'Electronic']:
                    for unit_data in units:
                        identifier = unit_data.get('identifier', '').strip()
                        status = unit_data.get('status', 'available')
                        if not identifier:
                            continue
                        if Unit.objects.filter(identifier=identifier).exists():
                            skipped_count += 1
                            continue
                        
                        if existing_product_type == 'Phone':
                            Unit.objects.create(phone=existing_product, identifier=identifier, unit_type='imei', status=status, branch=branch)
                        else:
                            Unit.objects.create(electronic=existing_product, identifier=identifier, unit_type='serial', status=status, branch=branch)
                        added_count += 1

                    if added_count > 0:
                        receive_stock(existing_product, branch, added_count, request.user, notes="Added via Product Form")

                elif existing_product_type == 'Accessory':
                    if quantity > 0:
                        receive_stock(existing_product, branch, quantity, request.user, notes="Added via Product Form")
                    added_count = quantity

                if added_count > 0:
                    msg = f'✅ Product "{existing_product.name}" already exists (Code: {existing_product.product_code}). '
                    msg += f'Added {added_count} new unit(s) to {branch.name} branch.'
                    if skipped_count > 0:
                        msg += f' {skipped_count} identifier(s) already existed and were skipped.'
                    messages.success(request, msg)
                else:
                    if skipped_count > 0:
                        messages.warning(request, f'All {skipped_count} identifier(s) already exist. No new units added.')
                    else:
                        messages.info(request, 'No new units to add. The product already exists.')

                return redirect('/epa_shop/products/')

            # ------------------------------------------------------------
            # Create NEW product
            # ------------------------------------------------------------
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

            category_map = {
                'smartphone': 'phones',
                'feature_phone': 'phones',
                'electronics': 'electronics',
                'accessory': 'accessories'
            }
            category_type_db = category_map.get(category_type, 'other')

            category = Category.objects.filter(company=company, category_type=category_type_db).first()
            if not category:
                category = Category.objects.create(
                    company=company,
                    name=category_type.replace('_', ' ').title(),
                    category_type=category_type_db,
                    is_active=True
                )

            owner = get_or_create_owner_from_user(request.user, company=company)
            
            # Import here to avoid circular issues
            from apps.epa_shop.services.stock import receive_stock

            if category_type in ['smartphone', 'feature_phone']:
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

                product = Phone.objects.create(
                    company=company, category=category,
                    name=name, brand=brand, model=model, imei=None,
                    barcode=barcode,
                    color=color or '', storage_capacity=rom_value, ram=ram_value,
                    screen_size=screen_size or '', battery_capacity=battery_capacity or '',
                    condition=condition, purchase_price=purchase_price,
                    selling_price=selling_price, best_price=best_price,
                    image=image_public_id, owner=owner,
                    phone_type=phone_type_value, network_type=network_type_value,
                    memory_card=memory_card_value, features=features_value
                )

                for unit_data in units:
                    Unit.objects.create(
                        phone=product, identifier=unit_data['identifier'],
                        unit_type='imei', status=unit_data.get('status', 'available'),
                        owner=owner, branch=branch
                    )
                
                if len(units) > 0:
                    receive_stock(product, branch, len(units), request.user, notes="Initial Stock")

                product_type_label = "Feature Phone" if category_type == 'feature_phone' else "Smartphone"
                messages.success(request, f'✅ New {product_type_label} "{product.name}" created in {branch.name}! Code: {product.product_code}')

            elif category_type == 'electronics':
                product = Electronic.objects.create(
                    company=company, category=category,
                    name=name, brand=brand, model_number=model, serial_number=None,
                    barcode=barcode, device_type=device_type, processor=processor, ram=ram, storage=storage,
                    screen_size=screen_size or '', color=color or '',
                    purchase_price=purchase_price, selling_price=selling_price,
                    best_price=best_price, image=image_public_id, owner=owner
                )

                for unit_data in units:
                    Unit.objects.create(
                        electronic=product, identifier=unit_data['identifier'],
                        unit_type='serial', status=unit_data.get('status', 'available'),
                        owner=owner, branch=branch
                    )

                if len(units) > 0:
                    receive_stock(product, branch, len(units), request.user, notes="Initial Stock")

                messages.success(request, f'✅ New Electronics "{product.name}" created in {branch.name}! Code: {product.product_code}')

            elif category_type == 'accessory':
                product = Accessory.objects.create(
                    company=company, category=category,
                    name=name, brand=brand, accessory_type=accessory_type,
                    model=model or '', compatible_phone_models='', barcode=barcode,
                    purchase_price=purchase_price, selling_price=selling_price,
                    best_price=best_price, image=image_public_id, owner=owner
                )

                if quantity > 0:
                    receive_stock(product, branch, quantity, request.user, notes="Initial Stock")

                messages.success(request, f'✅ New Accessory "{product.name}" created in {branch.name}! Code: {product.product_code}')

            else:
                messages.error(request, f'Unknown category: {category_type}')
                return render(request, 'epa/product_form.html', {
                    'branches': branches, 'form_data': request.POST,
                    'category_value': category_type, 'units': units,
                    'units_json': '[]', 'is_edit': False,
                    'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
                })

            return redirect('/epa_shop/products/')

        except Exception as e:
            messages.error(request, f'Error creating product: {str(e)}')
            import traceback
            traceback.print_exc()

            units_data = request.POST.get('units', '[]')
            try:
                units = json.loads(units_data)
            except:
                units = []
            units_json = json.dumps(units)

            return render(request, 'epa/product_form.html', {
                'branches': branches, 'form_data': request.POST,
                'category_value': request.POST.get('category', ''), 'units': units,
                'units_json': units_json, 'is_edit': False,
                'page_title': 'Add Product', 'page_subtitle': 'Create a new product',
            })

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
# PRODUCT EDIT
# ============================================

@login_required
def product_edit(request, product_code):
    """Edit product details using product code"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_admin_or_manager(request.user) and not is_viewing_company:
        messages.error(request, 'You do not have permission to edit products. Only administrators and stock controllers can manage products.')
        return redirect('/epa_shop/products/')

    product, product_type = get_product_by_code(company, product_code)

    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')

    branches = Branch.objects.filter(company=company, is_active=True)
    if not is_viewing_company and not request.user.is_super_admin and not request.user.is_company_admin:
        user_branch = get_user_branch(request.user)
        if user_branch:
            branches = branches.filter(id=user_branch.id)

    # 1. Determine which branch we are editing
    branch_id = request.GET.get('branch')
    if not branch_id and branches.exists():
        branch_id = str(branches.first().id)
    
    current_branch = None
    if branch_id:
        current_branch = branches.filter(id=branch_id).first()

    # 2. Load stock specific to the current branch
    units = []
    units_json = '[]'
    current_quantity = 0

    if current_branch:
        stock_record = product.stock_at(current_branch)
        current_quantity = stock_record.quantity_in_stock if stock_record else 0

        if product_type == 'Phone':
            units = Unit.objects.filter(phone=product, branch=current_branch).order_by('-created_at')
        elif product_type == 'Electronic':
            units = Unit.objects.filter(electronic=product, branch=current_branch).order_by('-created_at')
        
        units_json = json.dumps([{'identifier': u.identifier, 'status': u.status} for u in units])

    # 3. Determine category_value based on product type
    if product_type == 'Phone':
        if hasattr(product, 'phone_type') and product.phone_type == 'feature':
            category_value = 'feature_phone'
        else:
            ram_empty = not product.ram or product.ram in ('N/A', '')
            rom_empty = not product.storage_capacity or product.storage_capacity in ('N/A', '')
            category_value = 'feature_phone' if (ram_empty and rom_empty) else 'smartphone'
    elif product_type == 'Electronic':
        category_value = 'electronics'
    elif product_type == 'Accessory':
        category_value = 'accessory'
    else:
        category_value = ''

    if request.method == 'POST':
        try:
            category_type = request.POST.get('category', '').strip()
            name = request.POST.get('name', '').strip()
            brand = request.POST.get('brand', '').strip()
            model = request.POST.get('model', '').strip()

            ram = request.POST.get('ram', '').strip()
            rom = request.POST.get('rom', '').strip()
            screen_size = request.POST.get('screen_size', '').strip()
            color = request.POST.get('color', '').strip()
            battery_capacity = request.POST.get('battery_capacity', '').strip()
            condition = request.POST.get('condition', 'new')
            network_type = request.POST.get('network_type', '').strip()
            memory_card = request.POST.get('memory_card', 'no')
            features = request.POST.get('features', '').strip()
            device_type = request.POST.get('device_type', 'other')
            processor = request.POST.get('processor', '').strip()
            storage = request.POST.get('storage', '').strip()
            accessory_type = request.POST.get('accessory_type', 'other')
            barcode = request.POST.get('barcode', '').strip() or None

            image = request.FILES.get('product_image')

            # --- Cloudinary Image Handling ---
            if image:
                new_public_id = _upload_product_image_to_cloudinary(
                    image, folder=f"epa/{product_type.lower()}s/{timezone.now().strftime('%Y/%m')}",
                )
                if not new_public_id:
                    messages.error(request, 'Image upload failed. Keeping the previous image.')
                else:
                    if product.image:
                        try:
                            _cloudinary_configure()
                            cloudinary.uploader.destroy(str(product.image.name))
                        except Exception as e:
                            print(f"⚠️ Could not delete old Cloudinary asset: {e}")
                    product.image = new_public_id

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

            # --- VALIDATIONS ---
            if not brand:
                messages.error(request, 'Brand is required.')
                return redirect(request.path + f'?branch={branch_id}')
            if not model:
                messages.error(request, 'Model is required.')
                return redirect(request.path + f'?branch={branch_id}')
            if purchase_price <= 0:
                messages.error(request, 'Buying price must be greater than 0.')
                return redirect(request.path + f'?branch={branch_id}')
            if selling_price <= 0:
                messages.error(request, 'Selling price must be greater than 0.')
                return redirect(request.path + f'?branch={branch_id}')

            if not name:
                if product_type == 'Phone':
                    name = f"{brand} {model} {rom} {ram}".strip()
                elif product_type == 'Electronic':
                    name = f"{brand} {model} {ram} {storage}".strip()
                else:
                    name = f"{brand} {model} {accessory_type}".strip()

            owner = get_or_create_owner_from_user(request.user, company=company)

            # --- Update Basic Product Fields (Branch independent) ---
            product.name = name
            product.brand = brand
            product.purchase_price = purchase_price
            product.selling_price = selling_price

            if hasattr(product, 'best_price'):
                product.best_price = best_price
            if hasattr(product, 'barcode'):
                product.barcode = barcode

            if product_type == 'Phone':
                product.model = model
                product.ram = ram or ''
                product.storage_capacity = rom or ''
                product.screen_size = screen_size or ''
                product.color = color or ''
                product.battery_capacity = battery_capacity or ''
                product.condition = condition

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

            elif product_type == 'Electronic':
                product.model_number = model
                product.device_type = device_type
                product.processor = processor or ''
                product.ram = ram or ''
                product.storage = storage or ''
                product.screen_size = screen_size or ''
                product.color = color or ''
                product.save()

            elif product_type == 'Accessory':
                product.model = model or ''
                product.accessory_type = accessory_type
                product.save()

            # --- Update Branch Specific Stock ---
            if current_branch:
                from apps.epa_shop.services.stock import adjust_stock

                if product_type in ['Phone', 'Electronic']:
                    units_data = request.POST.get('units', '[]')
                    try:
                        new_units = json.loads(units_data)
                    except:
                        new_units = []

                    if product_type == 'Phone':
                        existing_units = Unit.objects.filter(phone=product, branch=current_branch)
                    else:
                        existing_units = Unit.objects.filter(electronic=product, branch=current_branch)

                    existing_identifiers = set(existing_units.values_list('identifier', flat=True))
                    new_identifiers = set([u.get('identifier') for u in new_units if u.get('identifier')])

                    # Delete removed units
                    units_to_delete = existing_identifiers - new_identifiers
                    if units_to_delete:
                        units_to_delete_qs = existing_units.filter(identifier__in=units_to_delete)
                        deleted_count = units_to_delete_qs.count()
                        units_to_delete_qs.delete()
                        # Adjust stock down
                        if deleted_count > 0:
                            adjust_stock(product, current_branch, -deleted_count, request.user, movement_type='adjustment', notes="Removed via Edit Form")

                    # Add or update new units
                    added_count = 0
                    for unit_data in new_units:
                        identifier = unit_data.get('identifier')
                        status = unit_data.get('status', 'available')

                        if not identifier: continue

                        existing_unit = existing_units.filter(identifier=identifier).first()
                        if existing_unit:
                            existing_unit.status = status
                            existing_unit.save()
                        else:
                            if product_type == 'Phone':
                                Unit.objects.create(phone=product, identifier=identifier, unit_type='imei', status=status, owner=owner, branch=current_branch)
                            else:
                                Unit.objects.create(electronic=product, identifier=identifier, unit_type='serial', status=status, owner=owner, branch=current_branch)
                            added_count += 1
                    
                    # Adjust stock up
                    if added_count > 0:
                        adjust_stock(product, current_branch, added_count, request.user, movement_type='adjustment', notes="Added via Edit Form")

                elif product_type == 'Accessory':
                    # Adjust accessory stock difference
                    diff = quantity - current_quantity
                    if diff != 0:
                        adjust_stock(product, current_branch, diff, request.user, movement_type='adjustment', notes="Adjusted via Edit Form", min_level=min_stock)

            messages.success(request, f'Product "{product.name}" updated successfully for {current_branch.name}!')
            return redirect(f'/epa_shop/products/?branch={current_branch.id}')

        except Exception as e:
            messages.error(request, f'Error updating product: {str(e)}')
            import traceback
            traceback.print_exc()
            return redirect(request.path + f'?branch={branch_id}')

    context = {
        'branches': branches,
        'product': product,
        'product_type': product_type,
        'units': units,
        'units_json': units_json,
        'category_value': category_value,
        'is_edit': True,
        'current_branch_id': int(branch_id) if branch_id else None,
        'current_quantity': current_quantity,
        'page_title': f'Edit {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
        'form_data': {
            'network_type': getattr(product, 'network_type', ''),
            'features': getattr(product, 'features', ''),
            'memory_card': getattr(product, 'memory_card', 'no'),
            'phone_type': getattr(product, 'phone_type', 'smartphone'),
        }
    }
    return render(request, 'epa/product_form.html', context)

    
# ============================================
# PRODUCT DELETE
# ============================================

@login_required
def product_delete(request, product_code):
    """Delete a product using product code"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    if not is_admin_or_manager(request.user) and not is_viewing_company:
        messages.error(request, 'You do not have permission to delete products. Only administrators and stock controllers can manage products.')
        return redirect('/epa_shop/products/')
    
    product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    if not is_admin_or_manager(request.user) and not is_viewing_company:
        user_branch = get_user_branch(request.user)
        product_branch = product.branch if product else None
        if user_branch and product_branch and product_branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to delete products from other branches.')
            return redirect('/epa_shop/products/')
    
    if request.method == 'POST':
        try:
            product_name = product.name
            
            if product_type == 'Phone':
                Unit.objects.filter(phone=product).delete()
            elif product_type == 'Electronic':
                Unit.objects.filter(electronic=product).delete()
            
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
# PRODUCT TRANSFER
# ============================================

@login_required
def product_transfer(request, product_code):
    """Transfer stock of a specific product between branches"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if not is_admin_or_manager(request.user) and not is_viewing_company:
        messages.error(request, 'You do not have permission to transfer stock.')
        return redirect('/epa_shop/products/')

    product, product_type = get_product_by_code(company, product_code)
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')

    # ───────────────────────────────────────────────────────
    # Compute branch stock from Unit records
    # (phones/electronics) or BranchStock (accessories)
    # ───────────────────────────────────────────────────────
    branches_with_stock = []
    all_branches = Branch.objects.filter(company=company, is_active=True)

    for b in all_branches:
        if product_type == 'Phone':
            available_qty = Unit.objects.filter(
                phone=product, branch=b, status='available'
            ).count()
        elif product_type == 'Electronic':
            available_qty = Unit.objects.filter(
                electronic=product, branch=b, status='available'
            ).count()
        else:  # Accessory
            stock_record = product.stock_at(b)
            available_qty = stock_record.quantity_in_stock if stock_record else 0

        if available_qty > 0:
            branches_with_stock.append({
                'branch': b,
                'quantity': available_qty,
            })

    # 👇 Compute total AFTER the list has been populated
    total_branch_stock = sum(item['quantity'] for item in branches_with_stock)

    if request.method == 'POST':
        from_branch_id = request.POST.get('from_branch')
        to_branch_id = request.POST.get('to_branch')

        if not from_branch_id or not to_branch_id:
            messages.error(request, 'Please select both source and destination branches.')
        elif from_branch_id == to_branch_id:
            messages.error(request, 'Source and destination branches cannot be the same.')
        else:
            from_branch = Branch.objects.filter(id=from_branch_id, company=company).first()
            to_branch = Branch.objects.filter(id=to_branch_id, company=company).first()

            if not from_branch or not to_branch:
                messages.error(request, 'Invalid branch selected.')
            else:
                from apps.epa_shop.services.stock import initiate_transfer

                if product_type == 'Accessory':
                    try:
                        qty = int(request.POST.get('quantity', 0))
                        if qty <= 0:
                            raise ValueError("Quantity must be greater than 0.")

                        initiate_transfer(
                            product=product, from_branch=from_branch, to_branch=to_branch,
                            quantity=qty, user=request.user, notes="Initiated via Product Actions"
                        )
                        messages.success(request, f'Transfer of {qty} unit(s) initiated.')
                        return redirect(f'/epa_shop/products/{product_code}/')
                    except ValueError as e:
                        messages.error(request, str(e))
                else:
                    # Handle IMEI/Serial scanning
                    units_json = request.POST.get('selected_units', '[]')
                    try:
                        unit_identifiers = json.loads(units_json)
                    except:
                        unit_identifiers = []

                    if not unit_identifiers:
                        messages.error(request, 'Please scan at least one IMEI/Serial to transfer.')
                    else:
                        success_count = 0
                        for ident in unit_identifiers:
                            # Only query the correct FK field for this product type
                            if product_type == 'Phone':
                                unit = Unit.objects.filter(
                                    phone=product,
                                    identifier=ident,
                                ).first()
                            else:  # Electronic
                                unit = Unit.objects.filter(
                                    electronic=product,
                                    identifier=ident,
                                ).first()

                            if not unit:
                                messages.warning(request, f'Unit {ident} not found.')
                                continue

                            # Ensure it's in the source branch
                            if unit.branch != from_branch:
                                messages.warning(request, f'Unit {ident} is not in {from_branch.name}.')
                                continue

                            # Move the unit to the destination branch
                            unit.branch = to_branch
                            unit.save(update_fields=['branch', 'updated_at'])
                            success_count += 1

                        if success_count > 0:
                            # Deduct from source and mark as in-transit
                            initiate_transfer(
                                product=product, from_branch=from_branch, to_branch=to_branch,
                                quantity=success_count, user=request.user, notes="Transferred via Product Actions"
                            )
                            messages.success(request, f'Successfully transferred {success_count} unit(s) to {to_branch.name}.')
                            return redirect(f'/epa_shop/products/{product_code}/')
                        else:
                            messages.error(request, 'No valid units were transferred.')

    context = {
        'product': product,
        'product_type': product_type,
        'branches_with_stock': branches_with_stock,
        'total_branch_stock': total_branch_stock,
        'all_branches': all_branches,
        'page_title': f'Transfer Stock - {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
    }
    return render(request, 'epa/product_transfer.html', context)

    
# ============================================
# SEARCH UNITS FOR TRANSFER
# ============================================

@login_required
def product_search_units(request):
    """Search for available units (IMEI/Serial) in a specific branch for transfers."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)

    query = request.GET.get('q', '').strip()
    product_id = request.GET.get('product_id')
    branch_id = request.GET.get('branch_id')

    # 👇 CHANGED THIS LINE FROM 2 TO 1
    if len(query) < 1 or not branch_id:
        return JsonResponse({'units': []})

    results = []

    # Find available units for this product in this specific branch
    units = Unit.objects.filter(
        status='available',
        identifier__icontains=query,
        branch_id=branch_id
    ).select_related('phone', 'electronic', 'branch')

    if product_id:
        units = units.filter(Q(phone_id=product_id) | Q(electronic_id=product_id))

    units = units.filter(
        Q(phone__company=company) | Q(electronic__company=company)
    )

    for unit in units[:20]:
        product = unit.phone or unit.electronic
        if not product:
            continue

        results.append({
            'identifier': unit.identifier,
            'status': unit.status,
        })

    return JsonResponse({'units': results})



# ============================================
# STOCK RESTOCK SCANNER (landing page)
# ============================================

@login_required
def stock_restock_scanner(request):
    """
    Scanner landing page for restocking.
    - User scans a barcode / types a product code / types a name
    - On match, redirect straight to the product_restock page
    """
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # Only admins / managers / stock controllers can restock
    if not is_admin_or_manager(request.user) and not is_viewing_company \
            and not is_cashier(request.user):
        messages.error(request, 'You do not have permission to restock products.')
        return redirect('/epa_shop/products/')

    query = (request.GET.get('q') or '').strip()
    results = []
    direct_product = None

    if query:
        # ---------- 1. Exact match on barcode ----------
        for model_cls in (Phone, Electronic, Accessory):
            if hasattr(model_cls, 'barcode'):
                obj = model_cls.objects.filter(
                    company=company, barcode__iexact=query
                ).first()
                if obj:
                    direct_product = obj
                    break

        # ---------- 2. Exact match on product_code ----------
        if not direct_product:
            prod, _ = get_product_by_code(company, query)
            if prod:
                direct_product = prod

        # 1 & 2 → single hit, redirect straight to restock
        if direct_product:
            return redirect(f'/epa_shop/products/{direct_product.product_code}/restock/')

        # ---------- 3. Fallback: fuzzy search on name / brand / model ----------
        phone_qs = (
            Phone.objects
            .filter(company=company, is_active=True)
            .filter(
                Q(name__icontains=query) |
                Q(brand__icontains=query) |
                Q(model__icontains=query) |
                Q(product_code__icontains=query)
            )[:15]
        )
        for p in phone_qs:
            results.append({
                'pk': p.pk,
                'kind': 'phone',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model,
                'type_label': 'Smartphone' if getattr(p, 'phone_type', '') != 'feature' else 'Feature Phone',
                'stock': p.total_quantity_in_stock,
                'branch': p.branch.name if p.branch else '-',
            })

        elec_qs = (
            Electronic.objects
            .filter(company=company, is_active=True)
            .filter(
                Q(name__icontains=query) |
                Q(brand__icontains=query) |
                Q(model_number__icontains=query) |
                Q(product_code__icontains=query)
            )[:15]
        )
        for p in elec_qs:
            results.append({
                'pk': p.pk,
                'kind': 'electronic',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model_number,
                'type_label': 'Electronic',
                'stock': p.total_quantity_in_stock,
                'branch': p.branch.name if p.branch else '-',
            })

        acc_qs = (
            Accessory.objects
            .filter(company=company, is_active=True)
            .filter(
                Q(name__icontains=query) |
                Q(brand__icontains=query) |
                Q(model__icontains=query) |
                Q(product_code__icontains=query)
            )[:15]
        )
        for p in acc_qs:
            results.append({
                'pk': p.pk,
                'kind': 'accessory',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model,
                'type_label': 'Accessory',
                'stock': p.total_quantity_in_stock,
                'branch': p.branch.name if p.branch else '-',
            })

    context = {
        'query': query,
        'results': results,
        'result_count': len(results),
        'page_title': 'Stock Restock',
        'page_subtitle': 'Scan a barcode or search for a product to restock',
    }
    return render(request, 'epa/stock_restock_scanner.html', context)


# ============================================
# LIVE SEARCH SUGGESTIONS (JSON API)
# ============================================

@login_required
def stock_restock_suggestions(request):
    """AJAX endpoint for live product suggestions."""
    company, _ = get_active_company(request)
    if not company:
        return JsonResponse({'results': []})

    query = (request.GET.get('q') or '').strip()
    if not query:
        return JsonResponse({'results': []})

    results = []

    # 1. Phones
    phones = (
        Phone.objects
        .filter(company=company, is_active=True)
        .filter(
            Q(name__icontains=query) |
            Q(brand__icontains=query) |
            Q(model__icontains=query) |
            Q(product_code__icontains=query) |
            Q(barcode__icontains=query)
        )[:5]
    )
    for p in phones:
        results.append({
            'kind': 'phone',
            'type_label': 'Smartphone' if getattr(p, 'phone_type', '') != 'feature' else 'Feature Phone',
            'name': p.name,
            'brand': p.brand,
            'model': p.model or '',
            'product_code': p.product_code,
            'stock': p.total_quantity_in_stock,
            'restock_url': f'/epa_shop/products/{p.product_code}/restock/'
        })

    # 2. Electronics
    electronics = (
        Electronic.objects
        .filter(company=company, is_active=True)
        .filter(
            Q(name__icontains=query) |
            Q(brand__icontains=query) |
            Q(model_number__icontains=query) |
            Q(product_code__icontains=query) |
            Q(barcode__icontains=query)
        )[:5]
    )
    for p in electronics:
        results.append({
            'kind': 'electronic',
            'type_label': 'Electronic',
            'name': p.name,
            'brand': p.brand,
            'model': p.model_number or '',
            'product_code': p.product_code,
            'stock': p.total_quantity_in_stock,
            'restock_url': f'/epa_shop/products/{p.product_code}/restock/'
        })

    # 3. Accessories
    accessories = (
        Accessory.objects
        .filter(company=company, is_active=True)
        .filter(
            Q(name__icontains=query) |
            Q(brand__icontains=query) |
            Q(model__icontains=query) |
            Q(product_code__icontains=query) |
            Q(barcode__icontains=query)
        )[:5]
    )
    for p in accessories:
        results.append({
            'kind': 'accessory',
            'type_label': 'Accessory',
            'name': p.name,
            'brand': p.brand,
            'model': p.model or '',
            'product_code': p.product_code,
            'stock': p.total_quantity_in_stock,
            'restock_url': f'/epa_shop/products/{p.product_code}/restock/'
        })

    # Sort and limit to top 5 overall
    results = results[:5]

    return JsonResponse({'results': results})


# ============================================
# PRODUCT RESTOCK
# ============================================

@login_required
def product_restock(request, product_code):
    """Restock a product using product code"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    product, product_type = get_product_by_code(company, product_code)
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')

    existing_units = []
    if product_type in ['Phone', 'Electronic']:
        if product_type == 'Phone':
            existing_units = Unit.objects.filter(phone=product).order_by('-created_at')
        else:
            existing_units = Unit.objects.filter(electronic=product).order_by('-created_at')

    form_units = []
    form_units_json = '[]'
    submitted_quantity = 0

    # ── Helper to parse optional decimal ──
    def _parse_optional_decimal(raw):
        """Return Decimal if a value was provided, else None (meaning 'no change')."""
        raw = (raw or '').strip()
        if raw == '':
            return None
        try:
            value = Decimal(raw)
        except (ValueError, TypeError, Exception):
            return None
        if value <= 0:
            return None
        return value

    if request.method == 'POST':
        try:
            # ── Read optional price inputs (blank = leave unchanged) ──
            new_purchase_price = _parse_optional_decimal(request.POST.get('purchase_price'))
            new_selling_price  = _parse_optional_decimal(request.POST.get('selling_price'))
            new_best_price     = _parse_optional_decimal(request.POST.get('best_price'))
            best_price_cleared = request.POST.get('best_price_cleared') == '1'

            price_changes = []

            if product_type in ['Phone', 'Electronic']:
                units_data = request.POST.get('units', '[]')
                try:
                    new_units = json.loads(units_data)
                except:
                    new_units = []

                form_units = new_units
                form_units_json = units_data

                if not new_units:
                    messages.error(request, 'Please add at least one IMEI/Serial number.')
                    return render(request, 'epa/product_restock.html', {
                        'product': product, 'product_type': product_type,
                        'existing_units': existing_units, 'form_units': form_units,
                        'form_units_json': form_units_json,
                        'page_title': f'Restock - {product.name}',
                        'page_subtitle': f'Code: {product.product_code}',
                        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
                    })

                owner = get_or_create_owner_from_user(request.user, company=company)
                added_count = 0
                skipped_count = 0
                duplicate_identifiers = []

                for unit_data in new_units:
                    identifier = unit_data.get('identifier', '').strip()
                    status = unit_data.get('status', 'available')

                    if not identifier:
                        continue

                    if Unit.objects.filter(identifier=identifier).exists():
                        skipped_count += 1
                        duplicate_identifiers.append(identifier)
                        continue

                    if product_type == 'Phone':
                        Unit.objects.create(phone=product, identifier=identifier, unit_type='imei', status=status, owner=owner)
                    else:
                        Unit.objects.create(electronic=product, identifier=identifier, unit_type='serial', status=status, owner=owner)
                    added_count += 1

                if added_count == 0:
                    error_msg = 'No new units were added. '
                    if duplicate_identifiers:
                        error_msg += f'Already exist: {", ".join(duplicate_identifiers[:5])}'
                    else:
                        error_msg += 'All identifiers were invalid.'

                    messages.error(request, error_msg)
                    return render(request, 'epa/product_restock.html', {
                        'product': product, 'product_type': product_type,
                        'existing_units': existing_units, 'form_units': form_units,
                        'form_units_json': form_units_json,
                        'page_title': f'Restock - {product.name}',
                        'page_subtitle': f'Code: {product.product_code}',
                        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
                    })

                # ── Apply price changes (only when provided) ──
                if new_purchase_price is not None:
                    product.purchase_price = new_purchase_price
                    price_changes.append(f'buying → {new_purchase_price}')
                if new_selling_price is not None:
                    product.selling_price = new_selling_price
                    price_changes.append(f'selling → {new_selling_price}')
                if new_best_price is not None:
                    product.best_price = new_best_price
                    price_changes.append(f'best → {new_best_price}')
                elif best_price_cleared:
                    product.best_price = None
                    price_changes.append('best cleared')

                if product_type == 'Phone':
                    total_units = Unit.objects.filter(phone=product).count()
                else:
                    total_units = Unit.objects.filter(electronic=product).count()

                product.total_quantity_in_stock = total_units
                product.save()

                msg = f'✅ Added {added_count} unit(s) to {product.name}. New stock: {total_units}.'
                if skipped_count > 0:
                    msg += f' {skipped_count} skipped (duplicate identifier).'
                if price_changes:
                    msg += ' Prices updated: ' + ', '.join(price_changes) + '.'
                messages.success(request, msg)

                # 🚀 REDIRECT TO SCANNER FOR NEXT ITEM
                return redirect('/epa_shop/inventory/stock-restock/')

            elif product_type == 'Accessory':
                quantity = int(request.POST.get('quantity', 0))
                submitted_quantity = quantity

                if quantity <= 0:
                    messages.error(request, 'Quantity must be greater than 0.')
                    return render(request, 'epa/product_restock.html', {
                        'product': product, 'product_type': product_type,
                        'existing_units': existing_units,
                        'submitted_quantity': submitted_quantity,
                        'page_title': f'Restock - {product.name}',
                        'page_subtitle': f'Code: {product.product_code}',
                        'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
                    })

                product.total_quantity_in_stock += quantity

                # ── Apply price changes (only when provided) ──
                if new_purchase_price is not None:
                    product.purchase_price = new_purchase_price
                    price_changes.append(f'buying → {new_purchase_price}')
                if new_selling_price is not None:
                    product.selling_price = new_selling_price
                    price_changes.append(f'selling → {new_selling_price}')
                if new_best_price is not None:
                    product.best_price = new_best_price
                    price_changes.append(f'best → {new_best_price}')
                elif best_price_cleared:
                    product.best_price = None
                    price_changes.append('best cleared')

                product.save()

                msg = f'✅ Added {quantity} unit(s) to {product.name}. New stock: {product.total_quantity_in_stock}.'
                if price_changes:
                    msg += ' Prices updated: ' + ', '.join(price_changes) + '.'
                messages.success(request, msg)
                
                # 🚀 REDIRECT TO SCANNER FOR NEXT ITEM
                return redirect('/epa_shop/inventory/stock-restock/')

            else:
                messages.error(request, 'Unknown product type.')
                return redirect('/epa_shop/products/')

        except Exception as e:
            messages.error(request, f'Error restocking product: {str(e)}')
            import traceback
            traceback.print_exc()
            return render(request, 'epa/product_restock.html', {
                'product': product, 'product_type': product_type,
                'existing_units': existing_units, 'form_units': form_units,
                'form_units_json': form_units_json,
                'page_title': f'Restock - {product.name}',
                'page_subtitle': f'Code: {product.product_code}',
                'unit_label': 'IMEI' if product_type == 'Phone' else 'Serial',
            })

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
# PRODUCT UNIT
# ============================================

@login_required
def product_units(request, product_code):
    """View all units (IMEI/Serial) for a product with days since update"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, f'Product with code "{product_code}" not found.')
        return redirect('/epa_shop/products/')
    
    if not is_viewing_company:
        if is_agent(request.user):
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if not owner or product.owner != owner:
                messages.error(request, 'You do not have permission to view units for this product.')
                return redirect('/epa_shop/products/')
        elif not is_admin_or_manager(request.user):
            user_branch = get_user_branch(request.user)
            if user_branch:
                # Option B: Check if this product exists in the user's branch
                if not product.branch_stocks.filter(branch=user_branch).exists():
                    messages.error(request, 'You do not have permission to view units from other branches.')
                    return redirect('/epa_shop/products/')
    
    units = []
    unit_count = 0
    available_count = 0
    sold_count = 0
    reserved_count = 0
    repair_count = 0
    
    if product_type == 'Phone':
        # 👇 CHANGED: select_related('branch') instead of 'phone__branch'
        units = Unit.objects.filter(phone=product).select_related('branch').order_by('-created_at')
        
        if is_agent(request.user) and not is_viewing_company:
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner).exclude(status='sold')
            else:
                units = units.none()
        
        unit_count = units.count()
        
        for unit in units:
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            unit.sale = sale_item.sale if sale_item else None
            
            if unit.updated_at:
                delta = timezone.now() - unit.updated_at
                unit.days_since_update = delta.days
            else:
                unit.days_since_update = 0
            
        available_count = units.filter(status='available').count()
        sold_count = units.filter(status='sold').count()
        reserved_count = units.filter(status='reserved').count()
        repair_count = units.filter(status='repair').count()
        
    elif product_type == 'Electronic':
        # 👇 CHANGED: select_related('branch') instead of 'electronic__branch'
        units = Unit.objects.filter(electronic=product).select_related('branch').order_by('-created_at')
        
        if is_agent(request.user) and not is_viewing_company:
            owner = Owner.objects.filter(company=company, phone=request.user.phone).first()
            if owner:
                units = units.filter(owner=owner).exclude(status='sold')
            else:
                units = units.none()
        
        unit_count = units.count()
        
        for unit in units:
            sale_item = SaleItem.objects.filter(unit=unit).select_related('sale').first()
            unit.sale = sale_item.sale if sale_item else None
            
            if unit.updated_at:
                delta = timezone.now() - unit.updated_at
                unit.days_since_update = delta.days
            else:
                unit.days_since_update = 0
            
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
        'is_agent': is_agent(request.user) and not is_viewing_company,
        'page_title': f'Units - {product.name}',
        'page_subtitle': f'Code: {product.product_code}',
    }
    return render(request, 'epa/product_units.html', context)

# ============================================
# ACCESSORY LIST
# ============================================

@login_required
def accessory_list(request):
    """List only accessories with pagination"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    accessories = Accessory.objects.filter(company=company, is_active=True)
    
    if not is_viewing_company:
        accessories = filter_by_user_access(accessories, request.user, 'product')
    
    accessories = accessories.order_by('-created_at')
    
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
    
    category_filter = request.GET.get('category', '')
    if category_filter:
        accessories = accessories.filter(accessory_type=category_filter)
    
    accessory_types = Accessory.objects.filter(company=company, is_active=True).values_list('accessory_type', flat=True).distinct()
    accessory_types = [{'value': t, 'label': t.replace('_', ' ').title()} for t in accessory_types]
    
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



# ============================================
# EXCELL LIST
# ============================================


@login_required
def product_export_excel(request):
    """Export the product list to a true Excel (.xlsx) file."""
    company, is_viewing_company = get_active_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('/dashboard/')

    # Create an in-memory workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"

    # Check if user is allowed to see buying price
    can_see_buying = (
        is_viewing_company or
        request.user.is_company_admin or
        request.user.is_super_admin or
        request.user.role == 'stock_controller'
    )

    # Define Headers (Buying Price added)
    headers = [
        'SKU', 'Name', 'Category', 'Brand', 'Model', 'Specs', 
        'Quantity', 'Buying Price', 'Selling Price', 'Best Price', 'Status'
    ]
    ws.append(headers)

    # Style the header row (Bold, Light Blue Background)
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="87CEEB", end_color="87CEEB", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill

    # Helper to get purchase price safely
    def get_buying_price(item):
        if not can_see_buying:
            return "N/A"
        return float(item.purchase_price) if item.purchase_price else 0

    # --- Fetch Electronics ---
    electronics = Electronic.objects.filter(company=company)
    if not is_viewing_company:
        electronics = filter_by_user_access(electronics, request.user, 'product')
    for item in electronics:
        ws.append([
            item.product_code, item.name, 'Electronic', item.brand, item.model_number,
            f"{item.ram} {item.storage}".strip(), item.total_quantity_in_stock,
            get_buying_price(item),  # <--- Added here
            float(item.selling_price), float(item.best_price) if item.best_price else 0, 
            'Active' if item.is_active else 'Inactive'
        ])

    # --- Fetch Phones ---
    phones = Phone.objects.filter(company=company)
    if not is_viewing_company:
        phones = filter_by_user_access(phones, request.user, 'product')
    for item in phones:
        phone_type = 'Feature Phone' if getattr(item, 'phone_type', '') == 'feature' else 'Smartphone'
        ws.append([
            item.product_code, item.name, phone_type, item.brand, item.model,
            f"{item.ram} {item.storage_capacity}".strip(), item.total_quantity_in_stock,
            get_buying_price(item),  # <--- Added here
            float(item.selling_price), float(item.best_price) if item.best_price else 0, 
            'Active' if item.is_active else 'Inactive'
        ])

    # --- Fetch Accessories ---
    accessories = Accessory.objects.filter(company=company)
    if not is_viewing_company:
        accessories = filter_by_user_access(accessories, request.user, 'product')
    for item in accessories:
        ws.append([
            item.product_code, item.name, 'Accessory', item.brand, item.model,
            item.accessory_type, item.total_quantity_in_stock,
            get_buying_price(item),  # <--- Added here
            float(item.selling_price), float(item.best_price) if item.best_price else 0, 
            'Active' if item.is_active else 'Inactive'
        ])

    # Auto-adjust column widths for a clean look
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[column].width = max_length + 2

    # Setup response headers
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Products_Export_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    
    wb.save(response)
    return response


# ============================================
# BARCODE / LABEL VIEWS
# ============================================

@login_required
def barcode_png(request, kind, pk):
    """
    Return a Code128 barcode PNG for the product's product_code.
    Used as: <img src="/epa_shop/barcode/accessory/5.png">
    """
    company, _ = get_active_company(request)
    if not company:
        raise Http404("No active company")

    model = PRODUCT_KIND_MODELS.get(kind)
    if not model:
        raise Http404(f"Unknown product kind: {kind}")

    product = get_object_or_404(model, pk=pk, company=company)

    if not product.product_code:
        raise Http404("Product has no product_code")

    buffer = generate_barcode_image(product.product_code)
    return FileResponse(
        buffer,
        content_type='image/png',
        filename=f"{product.product_code}.png",
    )


@login_required
def label_single_pdf(request, kind, pk, size='medium'):
    """Single-label PDF (one page, one label) for roll printers."""
    company, _ = get_active_company(request)
    if not company:
        raise Http404("No active company")

    model = PRODUCT_KIND_MODELS.get(kind)
    if not model:
        raise Http404(f"Unknown product kind: {kind}")

    product = get_object_or_404(model, pk=pk, company=company)

    pdf = build_label_pdf([product], size=size)
    return FileResponse(
        pdf,
        content_type='application/pdf',
        filename=f"label-{product.product_code}.pdf",
    )


@login_required
def labels_mixed_pdf(request):
    """
    Bulk labels across mixed product kinds in a SINGLE PDF,
    with per-product quantities.

    URL: /epa_shop/labels-mixed.pdf?items=phone:1:10,accessory:5:3,electronic:3:1
         &size=medium&sheet=0

    Each item is "kind:pk:qty" (qty optional, defaults to 1).
    """
    company, _ = get_active_company(request)
    if not company:
        raise Http404("No active company")

    items_param = request.GET.get('items', '').strip()
    if not items_param:
        raise Http404("No items supplied")

    products = []  # expanded list — same product repeated qty times

    for chunk in items_param.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue

        parts = chunk.split(':')
        if len(parts) < 2:
            continue

        kind = parts[0].strip()
        pk_str = parts[1].strip()
        qty_str = parts[2].strip() if len(parts) >= 3 else '1'

        if not pk_str.isdigit():
            continue
        pk = int(pk_str)

        try:
            qty = int(qty_str)
        except (ValueError, TypeError):
            qty = 1

        # Sanity cap so someone can't request 1 million pages
        qty = max(1, min(qty, 500))

        model = PRODUCT_KIND_MODELS.get(kind)
        if not model:
            continue

        product = model.objects.filter(pk=pk, company=company).first()
        if not product:
            continue

        # Repeat this product qty times in the label list
        for _ in range(qty):
            products.append(product)

    if not products:
        raise Http404("No matching products")

    size = request.GET.get('size', 'medium')
    use_sheet = request.GET.get('sheet', '0') == '1'

    if use_sheet:
        pdf = build_label_sheet_pdf(products, size=size)
        filename = "labels-mixed-sheet.pdf"
    else:
        pdf = build_label_pdf(products, size=size)
        filename = "labels-mixed.pdf"

    return FileResponse(pdf, content_type='application/pdf', filename=filename)


@login_required
def labels_bulk_pdf(request, kind):
    """
    Bulk label PDF.
    Query params: ids=1,2,3   size=medium   sheet=1
    """
    company, _ = get_active_company(request)
    if not company:
        raise Http404("No active company")

    model = PRODUCT_KIND_MODELS.get(kind)
    if not model:
        raise Http404(f"Unknown product kind: {kind}")

    ids_param = request.GET.get('ids', '')
    ids = [int(i) for i in ids_param.split(',') if i.strip().isdigit()]
    if not ids:
        raise Http404("No product ids supplied")

    products = list(model.objects.filter(pk__in=ids, company=company))

    size = request.GET.get('size', 'medium')
    use_sheet = request.GET.get('sheet', '0') == '1'

    if use_sheet:
        pdf = build_label_sheet_pdf(products, size=size)
        filename = f"labels-{kind}-sheet.pdf"
    else:
        pdf = build_label_pdf(products, size=size)
        filename = f"labels-{kind}.pdf"

    return FileResponse(pdf, content_type='application/pdf', filename=filename)


@login_required
def labels_print_page(request):
    """
    Dedicated page for managing and printing barcode labels.
    Restricted to company_admin, super_admin, stock_controller.
    """
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # Role gate
    allowed_roles = ('company_admin', 'super_admin', 'stock_controller')
    if not is_viewing_company and request.user.role not in allowed_roles:
        messages.error(request, 'You do not have permission to print labels.')
        return redirect('/epa_shop/products/')

    # Build product list (same shape as product_list, minimal fields)
    all_products = []

    electronics = Electronic.objects.filter(company=company, is_active=True)
    for item in electronics:
        all_products.append({
            'pk': item.id,
            'kind': 'electronic',
            'product_code': item.product_code or '-',
            'name': item.name,
            'type': 'Electronic',
            'brand': item.brand or '-',
            'model': item.model_number or '-',
        })

    phones = Phone.objects.filter(company=company, is_active=True)
    for item in phones:
        phone_type = 'Smartphone'
        if hasattr(item, 'phone_type'):
            phone_type = 'Feature Phone' if item.phone_type == 'feature' else 'Smartphone'
        else:
            ram_empty = not item.ram or item.ram in ('N/A', '')
            rom_empty = not item.storage_capacity or item.storage_capacity in ('N/A', '')
            phone_type = 'Feature Phone' if (ram_empty and rom_empty) else 'Smartphone'

        all_products.append({
            'pk': item.id,
            'kind': 'phone',
            'product_code': item.product_code or '-',
            'name': item.name,
            'type': phone_type,
            'brand': item.brand or '-',
            'model': item.model or '-',
        })

    accessories = Accessory.objects.filter(company=company, is_active=True)
    for item in accessories:
        all_products.append({
            'pk': item.id,
            'kind': 'accessory',
            'product_code': item.product_code or '-',
            'name': item.name,
            'type': 'Accessory',
            'brand': item.brand or '-',
            'model': item.model or '-',
        })

    all_products.sort(key=lambda x: x['product_code'])

    context = {
        'all_products_json': all_products,
        'total_count': len(all_products),
        'page_title': 'Print Labels',
        'page_subtitle': 'Select products and print barcode labels',
    }
    return render(request, 'epa/labels_print.html', context)