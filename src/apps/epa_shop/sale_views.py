# apps/epa_shop/sale_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction
from apps.company.models import Branch
from .models import Phone, Electronic, Accessory, Category, Unit, Sale, SaleItem, Customer, Owner, ReturnItem
from django.contrib.contenttypes.models import ContentType
from django.db import models
from .utils import record_stock_movement
from decimal import Decimal
from decimal import Decimal, ROUND_HALF_UP
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.company.settings_views import get_company_settings
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)
import json
from datetime import timedelta
from django.db.models import Sum, Q
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST
from apps.mpesa.models import MpesaTransaction




# ============================================
# HELPER FUNCTION - User Role Checks
# ============================================

def is_admin_or_manager(user):
    """Check if user is admin, manager, or super admin"""
    return user.role in ['super_admin', 'company_admin', 'company_manager']


def get_user_branch(user):
    """Get the user's branch"""
    return user.branch if user else None

def calculate_tax(company, subtotal):
    """
    Return (tax_amount, net_amount) based on the company's Payment Settings.

    TAX-INCLUSIVE model (Kenyan retail):
        The subtotal IS the price the customer pays.
        Tax is extracted from it, not added on top.

        VAT = subtotal × rate / (100 + rate)
        net = subtotal   (unchanged — customer pays exactly the shelf price)

    If tax is disabled or rate is 0, returns (Decimal('0'), subtotal).
    """
    from apps.company.settings_views import get_company_settings

    try:
        company_settings = get_company_settings(company)
        payment = company_settings.get('payment', {})
    except Exception:
        return Decimal('0'), Decimal(str(subtotal))

    enable_tax = payment.get('enable_tax', False)
    try:
        rate = Decimal(str(payment.get('default_tax_rate', 0) or 0))
    except Exception:
        rate = Decimal('0')

    subtotal = Decimal(str(subtotal))

    if not enable_tax or rate <= 0:
        return Decimal('0'), subtotal

    # Tax-INCLUSIVE extraction:  tax = subtotal × rate / (100 + rate)
    tax = (subtotal * rate / (Decimal('100') + rate)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    net = subtotal   # ← customer pays exactly what's on the shelf
    return tax, net

# ============================================
# PROCESS SALE
# ============================================

class SaleError(Exception):
    """Raised to abort a sale cleanly inside transaction.atomic()."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _resolve_product(company, product_code):
    """
    Look up a product across the three models by product_code.
    Returns (product, category_type, sku) or (None, None, None).
    """
    # Phone
    p = Phone.objects.filter(company=company, product_code=product_code).first()
    if p:
        return p, 'Phone', (p.model or '')

    # Electronic
    p = Electronic.objects.filter(company=company, product_code=product_code).first()
    if p:
        return p, 'Electronic', (p.model_number or '')

    # Accessory
    p = Accessory.objects.filter(company=company, product_code=product_code).first()
    if p:
        return p, 'Accessory', (p.model or '')

    return None, None, None


def _content_type_for(product):
    if isinstance(product, Phone):
        return ContentType.objects.get_for_model(Phone)
    if isinstance(product, Electronic):
        return ContentType.objects.get_for_model(Electronic)
    if isinstance(product, Accessory):
        return ContentType.objects.get_for_model(Accessory)
    return None


@login_required
def process_sale(request):
    """Process a sale from the POS using product_code."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return JsonResponse(
                {'error': 'Please select a company in support mode'},
                status=400,
            )
        return JsonResponse({'error': 'No company assigned'}, status=400)

    # ============================================
    # Parse JSON
    # ============================================
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)

    branch_id        = data.get('branch_id')
    customer_name    = (data.get('customer_name') or 'Walk-in Customer').strip()
    customer_phone   = (data.get('customer_phone') or '').strip()
    customer_email   = (data.get('customer_email') or '').strip()
    items            = data.get('items', []) or []
    payment_method   = data.get('payment_method', 'cash')
    payment_status   = data.get('payment_status', 'paid')
    payment_reference = (data.get('payment_reference') or '').strip() or None

    # ============================================
    # Basic top-level validation (cheap, no DB writes)
    # ============================================
    if not branch_id:
        return JsonResponse({'error': 'Branch is required'}, status=400)

    if not items:
        return JsonResponse({'error': 'No items in cart'}, status=400)

    if payment_status not in ('paid', 'pending'):
        return JsonResponse({'error': 'Invalid payment status'}, status=400)

    branch = Branch.objects.filter(id=branch_id, company=company).first()
    if not branch:
        return JsonResponse({'error': 'Branch not found'}, status=404)

    # ============================================
    # PHASE 1 + PHASE 2 inside one atomic block
    # ============================================
    try:
        with transaction.atomic():

            # ------------------------------------------------
            # PHASE 1 — VALIDATE EVERY LINE (no writes yet)
            # ------------------------------------------------
            subtotal = 0
            sale_items_data = []

            for idx, item in enumerate(items, start=1):
                product_code    = (item.get('product_code') or '').strip()
                quantity        = int(item.get('quantity', 1) or 1)
                price           = Decimal(str(item.get('price', 0) or 0))
                unit_identifier = item.get('unit_identifier') or None

                if not product_code:
                    raise SaleError(f'Row {idx}: product code is required.')

                if quantity <= 0:
                    raise SaleError(f'Row {idx}: quantity must be greater than 0.')

                if price < 0:
                    raise SaleError(f'Row {idx}: price cannot be negative.')

                # Resolve product
                product, category_type, sku = _resolve_product(company, product_code)
                if not product:
                    raise SaleError(
                        f'Product with code "{product_code}" not found.',
                        status=404,
                    )

                # ---- Resolve & validate unit for tracked products ----
                unit = None
                if category_type == 'Phone':
                    if unit_identifier:
                        unit = Unit.objects.filter(
                            phone=product,
                            identifier=unit_identifier,
                            status='available',
                        ).first()
                        if not unit:
                            raise SaleError(
                                f'IMEI "{unit_identifier}" is not available.'
                            )
                    if product.quantity_in_stock < quantity:
                        raise SaleError(
                            f'Insufficient stock for "{product.name}". '
                            f'Available: {product.quantity_in_stock}'
                        )

                elif category_type == 'Electronic':
                    if unit_identifier:
                        unit = Unit.objects.filter(
                            electronic=product,
                            identifier=unit_identifier,
                            status='available',
                        ).first()
                        if not unit:
                            raise SaleError(
                                f'Serial "{unit_identifier}" is not available.'
                            )
                    if product.quantity_in_stock < quantity:
                        raise SaleError(
                            f'Insufficient stock for "{product.name}". '
                            f'Available: {product.quantity_in_stock}'
                        )

                elif category_type == 'Accessory':
                    if product.quantity_in_stock < quantity:
                        raise SaleError(
                            f'Insufficient stock for "{product.name}". '
                            f'Available: {product.quantity_in_stock}'
                        )

                subtotal += price * quantity
                sale_items_data.append({
                    'product':         product,
                    'product_code':    product_code,
                    'product_name':    product.name,
                    'sku':             sku,
                    'category_type':   category_type,
                    'quantity':        quantity,
                    'unit_price':      price,
                    'total_price':     price * quantity,
                    'unit':            unit,            # ← already resolved
                    'unit_identifier': unit_identifier,
                })

            # ------------------------------------------------
            # PHASE 2 — WRITE EVERYTHING (validation passed)
            # ------------------------------------------------

            # Tax
            tax_amount, net_amount = calculate_tax(company, subtotal)

            # Customer (create or reuse) — inside the atomic block
            customer = None
            if customer_phone:
                customer = Customer.objects.filter(
                    phone=customer_phone, company=company
                ).first()
                if not customer:
                    customer = Customer.objects.create(
                        company=company,
                        name=customer_name,
                        phone=customer_phone,
                        email=customer_email,
                        is_active=True,
                    )

            # Sale
            sale = Sale.objects.create(
                company=company,
                branch=branch,
                customer=customer,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                total_amount=subtotal,       # pre-tax subtotal
                discount=0,
                tax=tax_amount,
                net_amount=net_amount,       # what customer pays
                payment_status=payment_status,
                payment_method=payment_method,
                sold_by=request.user,
                sale_date=timezone.now(),
            )

            # 👇 NEW — link the M-Pesa transaction to this sale
            if payment_method == 'm-pesa' and payment_reference:
                MpesaTransaction.objects.filter(
                    company=company,
                    mpesa_code__iexact=payment_reference,
                ).update(sale=sale)


            # Sale items + unit/stock mutations
            for item_data in sale_items_data:
                product = item_data['product']
                unit    = item_data['unit']
                qty     = item_data['quantity']

                previous_quantity = product.quantity_in_stock

                # Mark unit as sold (Phone / Electronic)
                if unit is not None:
                    unit.status = 'sold'
                    unit.sold_date = timezone.now()
                    unit.owner_name = customer_name
                    unit.owner_phone = customer_phone
                    unit.save()

                # Decrement stock
                product.quantity_in_stock -= qty
                product.save()

                # Create SaleItem
                SaleItem.objects.create(
                    sale=sale,
                    content_type=_content_type_for(product),
                    object_id=product.id,
                    item=product,
                    item_name=item_data['product_name'],
                    item_sku=item_data['product_code'],
                    quantity=qty,
                    unit_price=item_data['unit_price'],
                    total_price=item_data['total_price'],
                    unit=unit,
                )

                # Stock movement
                record_stock_movement(
                    product=product,
                    movement_type='sale',
                    quantity=-qty,
                    previous_quantity=previous_quantity,
                    new_quantity=product.quantity_in_stock,
                    branch=branch,
                    unit=unit,
                    notes=f"Sale ({payment_status}) - {customer_name}",
                    performed_by=request.user,
                )

            # Customer stats — only count PAID sales toward purchases
            if customer and payment_status == 'paid':
                customer.total_purchases += net_amount
                customer.visit_count += 1
                customer.last_visit = timezone.now()
                customer.save()

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------
            return JsonResponse({
                'success': True,
                'message': (
                    'Sale completed successfully!'
                    if payment_status == 'paid'
                    else 'Sale saved as PENDING.'
                ),
                'sale_id': sale.id,
                'sale_number': sale.company_sale_id,
                'payment_status': payment_status,
                'subtotal': float(subtotal),
                'tax': float(tax_amount),
                'total': float(net_amount),
                'items_count': len(sale_items_data),
                'customer': customer_name,
            })

    except SaleError as e:
        # Expected validation failure — atomic block already rolled back
        return JsonResponse({'error': e.message}, status=e.status)

    except Exception as e:
        # Unexpected — print and return 500
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


# ============================================
# SINGLE ITEM SALE - Create Page
# ============================================

@login_required
def sale_create_single(request):
    """Create a single item sale page"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branches = Branch.objects.filter(company=company, is_active=True)
    customers = Customer.objects.filter(company=company, is_active=True).order_by('name')[:50]
    
    context = {
        'company': company,
        'branches': branches,
        'customers': customers,
        'is_viewing_company': is_viewing_company,
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
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # In support mode, super admin sees all branches
    is_admin = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    results = []
    
    base_filter = {
        'identifier__icontains': query,
        'status': 'available'
    }
    
    # Filter by branch only if not admin AND not in support mode
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
        
        electronic_units = Unit.objects.filter(
            **base_filter,
            electronic__company=company
        ).select_related(
            'electronic', 'electronic__branch'
        )[:20]
        
        units = list(units) + list(electronic_units)
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
def sale_process_single(request):
    """Process a single item sale."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # ============================================================
    # PHASE 0 — READ + VALIDATE FORM INPUT (no DB writes)
    # ============================================================
    unit_id              = (request.POST.get('unit_id') or '').strip()
    customer_name        = (request.POST.get('customer_name') or '').strip()
    customer_phone       = (request.POST.get('customer_phone') or '').strip()
    customer_id_number   = (request.POST.get('customer_id_number') or '').strip()
    customer_email       = (request.POST.get('customer_email') or '').strip()
    next_of_keen_name    = (request.POST.get('next_of_keen_name') or '').strip()
    next_of_keen_phone   = (request.POST.get('next_of_keen_phone') or '').strip()
    sale_price_raw       = request.POST.get('sale_price', '0')
    sale_type            = (request.POST.get('sale_type') or 'cash').strip()
    branch_id            = (request.POST.get('branch_id') or '').strip()
    payment_reference    = (request.POST.get('payment_reference') or '').strip() or None 

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
        sale_price = Decimal(str(sale_price_raw))
        if sale_price <= 0:
            return JsonResponse({'error': 'Sale price must be greater than 0'}, status=400)
    except (ValueError, TypeError, ArithmeticError):
        return JsonResponse({'error': 'Invalid sale price'}, status=400)

    # ============================================================
    # PHASE 1 — VALIDATE EVERYTHING AGAINST THE DB (no writes)
    # ============================================================
    try:
        with transaction.atomic():

            # --- Resolve + validate unit ---
            unit = Unit.objects.filter(id=unit_id).select_related(
                'phone', 'phone__branch',
                'electronic', 'electronic__branch',
            ).first()

            if not unit:
                raise SaleError(f'Unit "{unit_id}" not found.', status=404)

            if unit.status != 'available':
                raise SaleError(f'Unit "{unit.identifier}" is not available.')

            # --- Resolve product ---
            if unit.phone:
                product = unit.phone
            elif unit.electronic:
                product = unit.electronic
            else:
                raise SaleError('Invalid product attached to this unit.')

            # --- Verify product belongs to the active company ---
            if product.company_id != company.id:
                raise SaleError('Product does not belong to this company.', status=403)

            # --- Resolve branch ---
            branch = None
            if branch_id:
                branch = Branch.objects.filter(id=branch_id, company=company).first()
                if not branch:
                    raise SaleError('Branch not found.', status=404)
            if not branch:
                branch = product.branch
            if not branch:
                raise SaleError('No branch assigned to this product.')

            # --- Tax ---
            tax_amount, net_amount = calculate_tax(company, sale_price)

            # ============================================================
            # PHASE 2 — WRITE EVERYTHING (all validation passed)
            # ============================================================

            # --- Create or reuse customer ---
            customer = Customer.objects.filter(
                phone=customer_phone, company=company
            ).first()

            if not customer:
                customer = Customer.objects.create(
                    company=company,
                    branch=branch,
                    name=customer_name,
                    phone=customer_phone,
                    email=customer_email,
                    id_number=customer_id_number,
                    next_of_keen_name=next_of_keen_name,
                    next_of_keen_phone=next_of_keen_phone,
                    address=(
                        f"ID: {customer_id_number} | "
                        f"Next of Keen: {next_of_keen_name} | "
                        f"NOK Phone: {next_of_keen_phone}"
                    ),
                    is_active=True,
                )
            else:
                # Merge any newly-provided fields
                if customer_name and customer.name != customer_name:
                    customer.name = customer_name
                if customer_email and not customer.email:
                    customer.email = customer_email
                if customer_id_number and customer.id_number != customer_id_number:
                    customer.id_number = customer_id_number
                if next_of_keen_name and customer.next_of_keen_name != next_of_keen_name:
                    customer.next_of_keen_name = next_of_keen_name
                if next_of_keen_phone and customer.next_of_keen_phone != next_of_keen_phone:
                    customer.next_of_keen_phone = next_of_keen_phone
                customer.address = (
                    f"ID: {customer_id_number} | "
                    f"Next of Keen: {next_of_keen_name} | "
                    f"NOK Phone: {next_of_keen_phone}"
                )
                customer.save()

            # --- Create or reuse owner ---
            owner = Owner.objects.filter(
                phone=customer_phone, company=company
            ).first()

            if not owner:
                owner = Owner.objects.create(
                    company=company,
                    branch=branch,
                    name=customer_name,
                    phone=customer_phone,
                    email=customer_email,
                    id_number=customer_id_number,
                    address=(
                        f"ID: {customer_id_number} | "
                        f"Next of Keen: {next_of_keen_name} | "
                        f"NOK Phone: {next_of_keen_phone}"
                    ),
                    is_active=True,
                )

            # --- Determine payment status ---
            paid_methods = {'cash', 'm-pesa', 'mpesa', 'bank_transfer', 'card'}
            payment_status = 'paid' if sale_type in paid_methods else 'pending'

            # --- Create Sale ---
            sale = Sale.objects.create(
                company=company,
                branch=branch,
                customer=customer,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                total_amount=sale_price,       # pre-tax subtotal
                discount=Decimal('0'),
                tax=tax_amount,
                net_amount=net_amount,         # what customer pays
                payment_status=payment_status,
                payment_method=sale_type,
                sold_by=request.user,
                sale_date=timezone.now(),
            )


            # 👇 NEW — link the M-Pesa transaction to this sale
            if sale_type in ('m-pesa', 'mpesa') and payment_reference:
                MpesaTransaction.objects.filter(
                    company=company,
                    mpesa_code__iexact=payment_reference,
                ).update(sale=sale)

            # --- Create SaleItem ---
            content_type = ContentType.objects.get_for_model(product)
            SaleItem.objects.create(
                sale=sale,
                content_type=content_type,
                object_id=product.id,
                item=product,
                item_name=f"{product.brand} {product.name}",
                item_sku=product.product_code,
                quantity=1,
                unit_price=sale_price,
                total_price=sale_price,
                unit=unit,
            )

            # --- Mark unit as sold ---
            unit.status = 'sold'
            unit.owner = owner
            unit.owner_name = customer_name
            unit.owner_phone = customer_phone
            unit.sold_date = timezone.now()
            unit.save()

            # --- Decrement product stock ---
            previous_quantity = product.quantity_in_stock
            if product.quantity_in_stock > 0:
                product.quantity_in_stock -= 1
                product.save()

            # --- Customer stats (only for PAID) ---
            if payment_status == 'paid':
                customer.total_purchases += net_amount
                customer.visit_count += 1
                customer.last_visit = timezone.now()
                customer.save()

                owner.total_purchases += net_amount
                owner.purchase_count += 1
                owner.last_purchase_date = timezone.now()
                owner.save()

            # --- Stock movement ---
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
                notes=f"Sale #{sale.id} ({payment_status}) - {customer_name} ({customer_phone})",
                performed_by=request.user,
            )

            # ============================================================
            # SUCCESS
            # ============================================================
            return JsonResponse({
                'success': True,
                'sale_id': sale.id,
                'payment_status': payment_status,
                'message': (
                    f'Sale completed successfully! Receipt #{sale.company_sale_id}'
                    if payment_status == 'paid'
                    else f'Sale saved as PENDING. Ref #{sale.company_sale_id}'
                ),
                'redirect_url': f'/epa_shop/sale/receipt/{sale.id}/',
            })

    except SaleError as e:
        # Expected validation failure — atomic block already rolled back
        return JsonResponse({'error': e.message}, status=e.status)

    except Exception as e:
        # Unexpected — print traceback and return 500
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)




# ============================================
# SALE RECEIPT 
# ============================================     
@login_required
@xframe_options_sameorigin
def sale_receipt(request, pk):
    """Generate and return sale receipt HTML page"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    try:
        if isinstance(pk, str) and not pk.isdigit():
            sale = get_object_or_404(Sale, company_sale_id=pk, company=company)
        else:
            sale = get_object_or_404(Sale, pk=int(pk), company=company)
    except (ValueError, TypeError):
        sale = get_object_or_404(Sale, company_sale_id=str(pk), company=company)

    # Check branch access (skip in support mode)
    if not is_viewing_company and not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch and sale.branch and sale.branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view receipts from other branches.')
            return redirect('/epa_shop/sales/')

    items = sale.items.all()

    # ------------------------------------------------------------
    # Load receipt settings (merged with defaults) so the template
    # can honour every toggle from the Receipt Settings page.
    # ------------------------------------------------------------
    from apps.company.settings_views import get_company_settings
    company_settings = get_company_settings(company)
    receipt_settings = company_settings.get('receipt', {})

    context = {
        'company': company,
        'sale': sale,
        'items': items,
        'is_viewing_company': is_viewing_company,
        'receipt_settings': receipt_settings,   # ✅ NEW
        'page_title': f'Receipt #{sale.company_sale_id}',
        'page_subtitle': 'Sale receipt',
        'is_embed': request.GET.get('embed') == '1', 
        'is_receipt': True,
    }
    return render(request, 'epa/sale_receipt.html', context)


# ============================================
# SALE RECEIPT BY  ID
# ============================================

@login_required
@xframe_options_sameorigin
def sale_receipt_by_id(request, company_sale_id):
    """Generate and return sale receipt data using company_sale_id"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    sale = get_object_or_404(Sale, company_sale_id=company_sale_id, company=company)

    # Check branch access (skip in support mode)
    if not is_viewing_company and not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch and sale.branch and sale.branch.id != user_branch.id:
            messages.error(request, 'You do not have permission to view receipts from other branches.')
            return redirect('/epa_shop/sales/')

    items = sale.items.all()

    # ------------------------------------------------------------
    # Load receipt settings (merged with defaults) so the template
    # can honour every toggle from the Receipt Settings page.
    # ------------------------------------------------------------
    from apps.company.settings_views import get_company_settings
    company_settings = get_company_settings(company)
    receipt_settings = company_settings.get('receipt', {})

    context = {
        'company': company,
        'sale': sale,
        'items': items,
        'is_viewing_company': is_viewing_company,
        'receipt_settings': receipt_settings,   # ✅ NEW
        'page_title': f'Receipt #{sale.company_sale_id}',
        'page_subtitle': 'Sale receipt',
        'is_embed': request.GET.get('embed') == '1',
        'is_receipt': True,
    }
    return render(request, 'epa/sale_receipt.html', context)


# ============================================
# GET BRANCHES FOR POS
# ============================================

@login_required
def get_branches(request):
    """Get branches for POS dropdown"""
    company, is_viewing_company = get_active_company(request)
    
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
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
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
    """List all sales with pagination + branch filter + live stats"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # ---------- Role flags ----------
    can_view_all = (
        is_viewing_company or
        request.user.is_super_admin or
        request.user.is_company_admin or
        request.user.is_superuser or
        request.user.is_staff
    )

    is_admin = (
        is_viewing_company or
        request.user.is_company_admin or
        request.user.is_company_manager or
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )

    # ---------- Base queryset ----------
    sales_queryset = Sale.objects.filter(company=company)

    # Non-admins default to their own branch
    if not is_admin and request.user.branch:
        sales_queryset = sales_queryset.filter(branch=request.user.branch)

    # Non-privileged users see only TODAY
    if not can_view_all:
        today = timezone.localdate()
        sales_queryset = sales_queryset.filter(sale_date__date=today)

    # ---------- Branch filter (from querystring) ----------
    branch_id = request.GET.get('branch', '').strip()
    selected_branch = None
    if branch_id and branch_id.isdigit():
        selected_branch = Branch.objects.filter(id=int(branch_id), company=company).first()
        if selected_branch:
            sales_queryset = sales_queryset.filter(branch=selected_branch)

    # ---------- Date-range filter (optional) ----------
    date_from = request.GET.get('from', '').strip()
    date_to   = request.GET.get('to', '').strip()
    if date_from:
        sales_queryset = sales_queryset.filter(sale_date__date__gte=date_from)
    if date_to:
        sales_queryset = sales_queryset.filter(sale_date__date__lte=date_to)

    # ---------- Search ----------
    search_query = request.GET.get('search', '').strip()
    if search_query:
        sales_queryset = sales_queryset.filter(
            Q(customer_name__icontains=search_query) |
            Q(company_sale_id__icontains=search_query) |
            Q(payment_method__icontains=search_query) |
            Q(payment_status__icontains=search_query)
        )

    # ---------- Stats (computed on filtered queryset) ----------
    # ---------- Stats (computed on filtered queryset) ----------
    # IMPORTANT: use timezone.localdate() so "today" matches the
    # company's local calendar day — timezone.now().date() returns
    # the UTC date which is one day behind in EAT (UTC+3).
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())          # Monday
    month_start = today.replace(day=1)

    stats = {
        'total_revenue': sales_queryset.aggregate(s=Sum('net_amount'))['s'] or 0,
        'today_revenue': sales_queryset.filter(
            sale_date__date=today
        ).aggregate(s=Sum('net_amount'))['s'] or 0,
        'week_revenue': sales_queryset.filter(
            sale_date__date__gte=week_start
        ).aggregate(s=Sum('net_amount'))['s'] or 0,
        'month_revenue': sales_queryset.filter(
            sale_date__date__gte=month_start
        ).aggregate(s=Sum('net_amount'))['s'] or 0,
        'total_sales_count': sales_queryset.count(),
    }

    # ---------- Order & count ----------
    sales_queryset = sales_queryset.order_by('-sale_date')
    total_count = sales_queryset.count()

    # ---------- Pagination ----------
    per_page = request.GET.get('per_page', '10')
    if per_page == 'all':
        per_page = total_count or 10
    else:
        try:
            per_page = int(per_page)
        except ValueError:
            per_page = 10

    paginator = Paginator(sales_queryset, per_page)
    page = request.GET.get('page', 1)
    try:
        sales = paginator.page(page)
    except PageNotAnInteger:
        sales = paginator.page(1)
    except EmptyPage:
        sales = paginator.page(paginator.num_pages)

    # ---------- Branch dropdown options ----------
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    # ---------- Preserve query params for pagination links ----------
    qs = request.GET.copy()
    qs.pop('page', None)
    querystring = qs.urlencode()

    context = {
        'sales': sales,
        'page_obj': sales,
        'total_count': total_count,
        'per_page': per_page,
        'search_query': search_query,
        'is_admin_or_manager': is_admin,
        'is_viewing_company': is_viewing_company,
        'can_view_all_sales': can_view_all,
        'stats': stats,                        # ✅ NEW
        'branches': branches,                  # ✅ NEW
        'selected_branch': selected_branch,    # ✅ NEW
        'branch_id': branch_id,                # ✅ NEW
        'date_from': date_from,                # ✅ NEW
        'date_to': date_to,                    # ✅ NEW
        'querystring': querystring,            # ✅ NEW
        'page_title': 'Sales',
        'page_subtitle': 'Sales history',
    }
    return render(request, 'epa/sales.html', context)


@login_required
def sale_lookup_by_barcode(request):
    """Look up a sale by its scannable barcode number."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        return JsonResponse({'success': False, 'error': 'No active company.'}, status=400)

    code = (request.GET.get('q') or '').strip()
    if not code:
        return JsonResponse({'success': False, 'error': 'No code provided.'}, status=400)

    sale = Sale.objects.filter(
        company=company,
        barcode_number__iexact=code,
    ).select_related('branch', 'customer').first()

    if not sale:
        return JsonResponse({
            'success': False,
            'error': f'No sale found for barcode "{code}".',
        }, status=404)

    # Branch access check
    if not is_viewing_company and not is_admin_or_manager(request.user):
        user_branch = get_user_branch(request.user)
        if user_branch and sale.branch and sale.branch.id != user_branch.id:
            return JsonResponse({
                'success': False,
                'error': 'This sale belongs to a different branch.',
            }, status=403)

    return JsonResponse({
        'success': True,
        'sale': {
            'id': sale.id,
            'company_sale_id': sale.company_sale_id,
            'barcode_number': sale.barcode_number,
            'customer_name': sale.customer_name,
            'customer_phone': sale.customer_phone,
            'net_amount': float(sale.net_amount),
            'payment_method': sale.payment_method,
            'payment_status': sale.payment_status,
            'sale_date': sale.sale_date.isoformat(),
            'branch_name': sale.branch.name if sale.branch else '',
            'receipt_url': f'/epa_shop/sale/receipt/{sale.id}/',
        },
    })


# ============================================
# SALE DETAIL
# ============================================

@login_required
def sale_detail(request, pk):
    """View sale details"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
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
# GET UNIT BY IDENTIFIER (Quick Scan) - Filtered
# ============================================

@login_required
def sale_get_unit_by_identifier(request):
    """Get unit details by identifier (IMEI/Serial) - Quick lookup"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    identifier = request.GET.get('identifier', '').strip()
    
    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    
    try:
        is_admin = (
            is_viewing_company or
            request.user.is_company_admin or 
            request.user.is_company_manager or 
            request.user.is_super_admin or
            request.user.is_superuser or
            request.user.is_staff
        )
        
        unit = Unit.objects.filter(
            identifier=identifier
        ).select_related(
            'phone', 'phone__branch', 'electronic', 'electronic__branch'
        ).first()
        
        if not unit:
            return JsonResponse({'error': f'Unit "{identifier}" not found'}, status=404)
        
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
        
        if not unit_company or unit_company.id != company.id:
            return JsonResponse({'error': 'Unit not found in your company'}, status=404)
        
        # Branch check (skip in support mode)
        if not is_admin:
            user_branch = request.user.branch
            if user_branch and unit_branch:
                if unit_branch.id != user_branch.id:
                    return JsonResponse({
                        'error': 'You do not have access to units from other branches'
                    }, status=403)
        
        if unit.status != 'available':
            return JsonResponse({
                'error': f'Unit "{identifier}" is already {unit.status}',
                'status': unit.status
            }, status=400)
        
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
# CREATE SALE FROM UNIT (Legacy)
# ============================================

@login_required
def sale_create(request):
    """Create a new sale from a unit (IMEI/Serial) - Legacy method"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    unit_id = request.GET.get('unit')
    product_code = request.GET.get('product')
    
    unit = None
    product = None
    product_type = None
    
    if unit_id:
        unit = get_object_or_404(Unit, id=unit_id)
        if unit.phone:
            product = unit.phone
            product_type = 'Phone'
        elif unit.electronic:
            product = unit.electronic
            product_type = 'Electronic'
    
    if not product and product_code:
        from .product_views import get_product_by_code
        product, product_type = get_product_by_code(company, product_code)
    
    if not product:
        messages.error(request, 'Product not found.')
        return redirect('/epa_shop/products/')
    
    branches = Branch.objects.filter(company=company, is_active=True)
    
    is_admin = (
        is_viewing_company or
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
            
            with transaction.atomic():
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
                
                unit_to_sell.status = 'sold'
                unit_to_sell.sold_date = timezone.now()
                unit_to_sell.owner_name = customer_name
                unit_to_sell.owner_phone = customer_phone
                unit_to_sell.save()
                
                previous_quantity = product.quantity_in_stock
                product.quantity_in_stock -= 1
                product.save()
                
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
                
                sale_item.unit = unit_to_sell
                sale_item.save()
                
                if customer:
                    customer.total_purchases += selling_price
                    customer.visit_count += 1
                    customer.last_visit = timezone.now()
                    customer.save()
                
                messages.success(request, f'Sale completed successfully! Receipt #{sale.company_sale_id}')
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
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    if not is_authorized:
        messages.error(request, 'You do not have permission to edit sales.')
        return redirect('epa-sales')
    
    sale = get_object_or_404(Sale, pk=pk, company=company)
    
    branches = Branch.objects.filter(company=company, is_active=True)
    
    if not is_authorized and request.user.branch:
        branches = branches.filter(id=request.user.branch.id)
    
    sale_items = sale.items.all()
    
    if request.method == 'POST':
        try:
            branch_id = request.POST.get('branch_id')
            customer_name = request.POST.get('customer_name', '').strip()
            customer_phone = request.POST.get('customer_phone', '').strip()
            customer_email = request.POST.get('customer_email', '').strip()
            payment_method = request.POST.get('payment_method', 'cash')
            payment_status = request.POST.get('payment_status', 'pending')
            selling_price = request.POST.get('selling_price', 0)
            
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
            
            branch = get_object_or_404(Branch, id=branch_id, company=company)
            
            sale.branch = branch
            sale.customer_name = customer_name
            sale.customer_phone = customer_phone
            sale.customer_email = customer_email
            sale.payment_method = payment_method
            sale.payment_status = payment_status
            sale.total_amount = Decimal(str(selling_price))
            sale.net_amount = Decimal(str(selling_price))
            sale.save()
            
            for item in sale_items:
                item.unit_price = Decimal(str(selling_price))
                item.total_price = Decimal(str(selling_price))
                item.save()
            
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
    """Mark a sale as completed — with payment method + amount tendered."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'No company assigned'}, status=400)
        messages.error(request, 'No company assigned.')
        return redirect('epa-dashboard')

    sale = get_object_or_404(Sale, id=sale_id, company=company)

    is_authorized = (
        is_viewing_company or
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
            payment_method      = (request.POST.get('payment_method') or '').strip().lower()
            amount_tendered_raw = (request.POST.get('amount_tendered') or '').strip()
            payment_reference   = (request.POST.get('payment_reference') or '').strip() or None 

            allowed_methods = {'cash', 'mpesa', 'card', 'bank_transfer'}
            if payment_method not in allowed_methods:
                messages.error(request, 'Please choose a valid payment method.')
                return render(request, 'epa/sale_verify.html', {
                    'sale': sale,
                    'page_title': 'Verify Sale',
                    'page_subtitle': f'Verify and complete sale #{sale.company_sale_id}',
                })

            try:
                amount_tendered = Decimal(amount_tendered_raw)
            except (ValueError, TypeError, ArithmeticError):
                messages.error(request, 'Invalid amount tendered.')
                return render(request, 'epa/sale_verify.html', {
                    'sale': sale,
                    'page_title': 'Verify Sale',
                    'page_subtitle': f'Verify and complete sale #{sale.company_sale_id}',
                })

            total_due = Decimal(str(sale.net_amount))

            if payment_method == 'cash':
                if amount_tendered < total_due:
                    messages.error(
                        request,
                        f'Amount tendered (KSh {amount_tendered}) is less than '
                        f'total due (KSh {total_due}).'
                    )
                    return render(request, 'epa/sale_verify.html', {
                        'sale': sale,
                        'page_title': 'Verify Sale',
                        'page_subtitle': f'Verify and complete sale #{sale.company_sale_id}',
                    })
            else:
                if amount_tendered != total_due:
                    messages.error(
                        request,
                        f'For {payment_method.replace("_", " ").title()}, the amount '
                        f'must equal the total due (KSh {total_due}).'
                    )
                    return render(request, 'epa/sale_verify.html', {
                        'sale': sale,
                        'page_title': 'Verify Sale',
                        'page_subtitle': f'Verify and complete sale #{sale.company_sale_id}',
                    })

            # ---- Apply ----
            sale.payment_status = 'paid'
            sale.payment_method = payment_method
            sale.save()

            if sale.customer:
                sale.customer.total_purchases += sale.net_amount
                sale.customer.visit_count += 1
                sale.customer.last_visit = timezone.now()
                sale.customer.save()

            for item in sale.items.all():
                if item.unit and item.unit.owner:
                    owner = item.unit.owner
                    owner.total_purchases += item.total_price
                    owner.purchase_count += 1
                    owner.last_purchase_date = timezone.now()
                    owner.save()

            messages.success(
                request,
                f'Sale #{sale.company_sale_id} marked as completed '
                f'({payment_method.replace("_", " ").title()}).'
            )

            if (request.headers.get('x-requested-with') == 'XMLHttpRequest'
                    or request.content_type == 'application/json'):
                return JsonResponse({
                    'success': True,
                    'message': f'Sale #{sale.company_sale_id} marked as completed.',
                    'sale_id': sale.id,
                    'redirect_url': f'/epa_shop/sale/receipt/{sale.id}/',
                })

            return redirect(f'/epa_shop/sale/receipt/{sale.id}/')

        except Exception as e:
            import traceback
            traceback.print_exc()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'error': str(e)}, status=500)
            messages.error(request, f'Error completing sale: {str(e)}')
            return redirect('epa-sales')

    context = {
        'sale': sale,
        'page_title': 'Verify Sale',
        'page_subtitle': f'Verify and complete sale #{sale.company_sale_id}',
    }
    return render(request, 'epa/sale_verify.html', context)


@login_required
def pos_pending_payments(request):
    """List pending sales for the POS Pending Payments tab."""
    company, _ = get_active_company(request)
    if not company:
        return JsonResponse({'pending': []})

    qs = Sale.objects.filter(
        company=company,
        payment_status='pending',
    ).select_related('branch').order_by('-sale_date')

    # Cashiers see only their own branch
    if request.user.role == 'company_cashier' and request.user.branch:
        qs = qs.filter(branch=request.user.branch)

    # Slice LAST, after all filters
    qs = qs[:50]

    return JsonResponse({'pending': [{
        'id': s.id,
        'company_sale_id': s.company_sale_id,
        'customer_name': s.customer_name,
        'customer_phone': s.customer_phone,
        'net_amount': float(s.net_amount),
        'sale_date': s.sale_date.isoformat(),
        'receipt_url': f'/epa_shop/sale/receipt/{s.id}/',
    } for s in qs]})

# ============================================
# PENDING SALES LIST
# ============================================

@login_required
def sale_pending_list(request):
    """List all pending sales"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    is_admin = (
        is_viewing_company or
        request.user.is_company_admin or 
        request.user.is_company_manager or 
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    
    pending_sales = Sale.objects.filter(
        company=company,
        payment_status='pending'
    ).select_related('customer', 'sold_by', 'branch').prefetch_related('items', 'items__unit')
    
    if not is_admin and request.user.branch:
        pending_sales = pending_sales.filter(branch=request.user.branch)
    
    pending_sales = pending_sales.order_by('-sale_date')
    
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
        'is_viewing_company': is_viewing_company,
        'page_title': 'Pending Sales',
        'page_subtitle': 'Sales awaiting completion verification',
    }
    return render(request, 'epa/sales_pending.html', context)


# ============================================
# SALE COMPLETE JSON
# ============================================
@login_required
@require_POST
def sale_complete_json(request, sale_id):
    """JSON version of sale_complete for POS pending-sales flow."""
    from django.views.decorators.http import require_POST  # if not already imported top-level
    company, is_viewing_company = get_active_company(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company assigned'}, status=400)

    sale = Sale.objects.filter(id=sale_id, company=company).first()
    if not sale:
        return JsonResponse({'success': False, 'error': 'Sale not found.'}, status=404)

    if sale.payment_status != 'pending':
        return JsonResponse({
            'success': False,
            'error': f'Sale is already {sale.payment_status}.',
        }, status=400)

    is_authorized = (
        is_viewing_company or
        request.user.is_company_admin or
        request.user.is_company_manager or
        request.user.is_super_admin or
        request.user.is_superuser or
        request.user.is_staff
    )
    if not is_authorized and request.user.role == 'company_cashier':
        if sale.branch_id == getattr(request.user.branch, 'id', None):
            is_authorized = True

    if not is_authorized:
        return JsonResponse({'success': False, 'error': 'Not authorized.'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

    method = (payload.get('payment_method') or '').strip().lower()
    amount_raw = payload.get('amount_tendered')

    allowed_methods = {'cash', 'mpesa', 'card', 'bank_transfer'}
    if method not in allowed_methods:
        return JsonResponse({'success': False, 'error': 'Invalid payment method.'}, status=400)

    try:
        amount_tendered = Decimal(str(amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return JsonResponse({'success': False, 'error': 'Invalid amount.'}, status=400)

    total_due = Decimal(str(sale.net_amount))

    if method == 'cash':
        if amount_tendered < total_due:
            return JsonResponse({
                'success': False,
                'error': f'Tendered KSh {amount_tendered} < total KSh {total_due}.',
            }, status=400)
    else:
        if amount_tendered != total_due:
            return JsonResponse({
                'success': False,
                'error': f'For {method}, amount must equal {total_due}.',
            }, status=400)

    with transaction.atomic():
        sale.payment_status = 'paid'
        sale.payment_method = method
        sale.save(update_fields=['payment_status', 'payment_method'])
        

        if sale.customer:
            sale.customer.total_purchases += sale.net_amount
            sale.customer.visit_count += 1
            sale.customer.last_visit = timezone.now()
            sale.customer.save()

        for item in sale.items.all():
            if item.unit and item.unit.owner:
                owner = item.unit.owner
                owner.total_purchases += item.total_price
                owner.purchase_count += 1
                owner.last_purchase_date = timezone.now()
                owner.save()

    return JsonResponse({
        'success': True,
        'message': f'Sale #{sale.company_sale_id} completed.',
        'sale_id': sale.id,
        'redirect_url': f'/epa_shop/sale/receipt/{sale.id}/',
    })


# ============================================
# UNIT REVERSE SALE - Return to Available
# ============================================

@login_required
def unit_reverse_sale(request, sale_id):
    """Reverse a sale and return unit to available"""
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    try:
        if str(sale_id).isdigit():
            sale = get_object_or_404(Sale, id=int(sale_id), company=company)
        else:
            sale = get_object_or_404(Sale, company_sale_id=sale_id, company=company)
    except (ValueError, TypeError):
        sale = get_object_or_404(Sale, company_sale_id=sale_id, company=company)
    
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
            sale_items = SaleItem.objects.filter(sale=sale)
            reversed_count = 0
            
            for sale_item in sale_items:
                if sale_item.unit:
                    unit = sale_item.unit
                    unit.status = 'available'
                    unit.owner_name = ''
                    unit.owner_phone = ''
                    unit.sold_date = None
                    unit.save()
                    
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
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    is_authorized = (
        is_viewing_company or
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


@login_required
def sale_return_data(request, sale_id):
    """Return a sale's items (with already-returned quantities) for the Return modal."""
    company, _ = get_active_company(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company assigned.'}, status=400)

    sale = Sale.objects.filter(id=sale_id, company=company).first()
    if not sale:
        return JsonResponse({'success': False, 'error': 'Sale not found.'}, status=404)

    # Build items with returned_qty
    items_out = []
    for item in sale.items.all():
        # Count how much of this item has already been returned
        returned_qty = ReturnItem.objects.filter(sale_item=item).aggregate(
            s=Sum('quantity')
        )['s'] or 0

        items_out.append({
            'id': item.id,
            'item_name': item.item_name,
            'item_sku': item.item_sku,
            'unit_price': float(item.unit_price),
            'quantity': item.quantity,
            'returned_qty': returned_qty,
            'unit_identifier': item.unit.identifier if item.unit else None,
        })

    return JsonResponse({
        'success': True,
        'sale': {
            'id': sale.id,
            'company_sale_id': sale.company_sale_id,
            'customer_name': sale.customer_name,
            'customer_phone': sale.customer_phone,
            'payment_method': sale.payment_method,
            'payment_status': sale.payment_status,
            'net_amount': float(sale.net_amount),
            'sale_date': sale.sale_date.isoformat(),
            'items': items_out,
        },
    })


@login_required
def sale_process_return(request):
    """Process a return against an existing sale."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    company, _ = get_active_company(request)
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    sale_id       = data.get('sale_id')
    refund_method = (data.get('refund_method') or 'cash').strip()
    reason        = (data.get('reason') or '').strip()
    items_in      = data.get('items') or []

    if not sale_id:
        return JsonResponse({'error': 'Sale ID is required.'}, status=400)
    if not items_in:
        return JsonResponse({'error': 'No items selected for return.'}, status=400)

    sale = Sale.objects.filter(id=sale_id, company=company).first()
    if not sale:
        return JsonResponse({'error': 'Sale not found.'}, status=404)

    try:
        with transaction.atomic():
            refund_total = Decimal('0')
            created_returns = []

            for entry in items_in:
                sale_item_id = entry.get('sale_item_id')
                qty          = int(entry.get('quantity') or 0)

                sale_item = SaleItem.objects.filter(id=sale_item_id, sale=sale).first()
                if not sale_item:
                    raise SaleError(f'Sale item {sale_item_id} not found on this sale.')
                if qty <= 0:
                    raise SaleError('Return quantity must be greater than 0.')

                already_returned = ReturnItem.objects.filter(
                    sale_item=sale_item
                ).aggregate(s=Sum('quantity'))['s'] or 0
                remaining = sale_item.quantity - already_returned

                if qty > remaining:
                    raise SaleError(
                        f'Cannot return {qty} of "{sale_item.item_name}" — '
                        f'only {remaining} remaining.'
                    )

                # Create ReturnItem
                r = ReturnItem.objects.create(
                    sale=sale,
                    sale_item=sale_item,
                    quantity=qty,
                    unit_price=sale_item.unit_price,
                    refund_method=refund_method,
                    reason=reason,
                    processed_by=request.user,
                )
                created_returns.append(r)

                # Unit goes back to available (only if fully returned AND it's a tracked unit)
                if sale_item.unit and (already_returned + qty >= sale_item.quantity):
                    unit = sale_item.unit
                    unit.status = 'available'
                    unit.owner_name = ''
                    unit.owner_phone = ''
                    unit.sold_date = None
                    unit.save()

                # Restock
                product = sale_item.item  # GFK: the actual Phone/Electronic/Accessory
                if product:
                    previous_qty = product.quantity_in_stock
                    product.quantity_in_stock += qty
                    product.save()

                    record_stock_movement(
                        product=product,
                        movement_type='return',
                        quantity=qty,
                        previous_quantity=previous_qty,
                        new_quantity=product.quantity_in_stock,
                        branch=sale.branch,
                        unit=sale_item.unit,
                        reference_id=f"RETURN-{r.id}",
                        reference_model='ReturnItem',
                        notes=f'Return for Sale #{sale.company_sale_id} — {reason or "no reason"}',
                        performed_by=request.user,
                    )

                refund_total += sale_item.unit_price * qty

            # If ALL items are now fully returned, mark the sale refunded
            all_fully_returned = True
            for item in sale.items.all():
                ret = ReturnItem.objects.filter(sale_item=item).aggregate(s=Sum('quantity'))['s'] or 0
                if ret < item.quantity:
                    all_fully_returned = False
                    break

            if all_fully_returned:
                sale.payment_status = 'refunded'
                sale.save()

            return JsonResponse({
                'success': True,
                'refund_total': float(refund_total),
                'refund_method': refund_method,
                'sale_fully_returned': all_fully_returned,
                'return_receipt_url': f'/epa_shop/sale/return-receipt/{created_returns[0].id}/',
            })

    except SaleError as e:
        return JsonResponse({'error': e.message}, status=e.status)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)