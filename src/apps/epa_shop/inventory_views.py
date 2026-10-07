from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from .models import (
    Electronic, Phone, Accessory, Category, 
    Sale, SaleItem, Customer, StockMovement, Supplier
)
from .models import (
    Electronic, Phone, Accessory, Category,
    Sale, SaleItem, Customer, StockMovement, Supplier, Unit,   # ← add Unit
)
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)

from apps.company.models import Branch
from django.contrib.auth import get_user_model
from .product_views import get_or_create_owner_from_user
from django.db import transaction


from django.http import JsonResponse
from django.views.decorators.http import require_POST
from collections import Counter
import json


User = get_user_model()


@login_required
def inventory_list(request):
    """Main inventory page showing all products"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
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
    
    # ============================================
    # UNIT COUNTS (IMEI / Serial)
    # ============================================
    # For phones & electronics, units live in the Unit model.
    # Accessories don't have units — their quantity_in_stock is the count.

    electronics_unit_count = Unit.objects.filter(
        electronic__company=company,
        electronic__is_active=True,
    ).count()

    phones_unit_count = Unit.objects.filter(
        phone__company=company,
        phone__is_active=True,
    ).count()

    # Accessories: sum of quantity_in_stock (no per-unit IMEI tracking)
    accessories_unit_count = accessories_stock

    total_products = electronics_count + phones_count + accessories_count
    total_stock = electronics_stock + phones_stock + accessories_stock
    
    # ============================================
    # FINANCIAL STATISTICS
    # ============================================
    
    # Calculate Purchase Value (Total cost of all inventory in stock)
    electronics_purchase = electronics.aggregate(
        total=Sum('purchase_price', default=0)
    )['total'] or 0
    phones_purchase = phones.aggregate(
        total=Sum('purchase_price', default=0)
    )['total'] or 0
    accessories_purchase = accessories.aggregate(
        total=Sum('purchase_price', default=0)
    )['total'] or 0
    
    # Better: Calculate purchase value * quantity for each item
    electronics_purchase_value = sum(
        item.purchase_price * item.quantity_in_stock 
        for item in electronics
    )
    phones_purchase_value = sum(
        item.purchase_price * item.quantity_in_stock 
        for item in phones
    )
    accessories_purchase_value = sum(
        item.purchase_price * item.quantity_in_stock 
        for item in accessories
    )
    total_purchase_value = (
        electronics_purchase_value + 
        phones_purchase_value + 
        accessories_purchase_value
    )
    
    # Calculate Expected Selling Value (Total potential revenue at selling price)
    electronics_selling_value = sum(
        item.selling_price * item.quantity_in_stock 
        for item in electronics
    )
    phones_selling_value = sum(
        item.selling_price * item.quantity_in_stock 
        for item in phones
    )
    accessories_selling_value = sum(
        item.selling_price * item.quantity_in_stock 
        for item in accessories
    )
    total_selling_value = (
        electronics_selling_value + 
        phones_selling_value + 
        accessories_selling_value
    )
    
    # Calculate Expected Profit (Selling Value - Purchase Value)
    expected_profit = total_selling_value - total_purchase_value
    expected_profit_margin = (
        (expected_profit / total_purchase_value * 100) 
        if total_purchase_value > 0 else 0
    )
    
    # Calculate Best Price Value (Total potential revenue at best price)
    # Best price is the minimum acceptable price - use selling_price if best_price is null
    electronics_best_value = sum(
        (item.best_price if item.best_price else item.selling_price) * item.quantity_in_stock 
        for item in electronics
    )
    phones_best_value = sum(
        (item.best_price if item.best_price else item.selling_price) * item.quantity_in_stock 
        for item in phones
    )
    accessories_best_value = sum(
        (item.best_price if item.best_price else item.selling_price) * item.quantity_in_stock 
        for item in accessories
    )
    total_best_value = (
        electronics_best_value + 
        phones_best_value + 
        accessories_best_value
    )
    
    # Best price profit
    best_price_profit = total_best_value - total_purchase_value
    
    # Low stock items
    low_stock_items = []
    
    # Electronics with low stock
    for item in electronics.filter(quantity_in_stock__lte=5):
        low_stock_items.append({
            'id': item.id,
            'name': f"{item.name}",
            'brand': f"{item.brand}",
            'specs': f"{item.ram} {item.storage}".strip() or '-',
            'model': f"{item.model_number}",
            'type': 'Electronic',
            'quantity': item.quantity_in_stock,
            'min_stock': item.minimum_stock_level,
            'price': item.selling_price,
            'purchase_price': item.purchase_price,
            'product_code': item.product_code or '-'
        })
    
    # Phones with low stock
    for item in phones.filter(quantity_in_stock__lte=5):
        low_stock_items.append({
            'id': item.id,
            'name': f"{item.name}",
            'brand': f"{item.brand}",
            'model': f"{item.model}",
            'specs': f"{item.ram} {item.storage_capacity}".strip() or '-',
            'type': 'Phone',
            'quantity': item.quantity_in_stock,
            'min_stock': item.minimum_stock_level,
            'price': item.selling_price,
            'purchase_price': item.purchase_price,
            'product_code': item.product_code or '-'
        })
    
    # Accessories with low stock (threshold 10 for accessories)
    for item in accessories.filter(quantity_in_stock__lte=10):
        low_stock_items.append({
            'id': item.id,
            'name': f"{item.name}",
            'brand': f"{item.brand}",
            'model': f"{item.model}",
            'specs': item.accessory_type or '-',
            'type': 'Accessory',
            'quantity': item.quantity_in_stock,
            'min_stock': item.minimum_stock_level,
            'price': item.selling_price,
            'purchase_price': item.purchase_price,
            'product_code': item.product_code or '-'
        })
    
    # Sort low stock items by quantity (lowest first)
    low_stock_items.sort(key=lambda x: x['quantity'])
    
    context = {
        'company': company,
        'total_products': total_products,
        'total_stock': total_stock,
        'electronics_count': electronics_count,
        'phones_count': phones_count,
        'accessories_count': accessories_count,
        'low_stock_count': len(low_stock_items),
        'low_stock_items': low_stock_items[:10],
        'is_viewing_company': is_viewing_company,
        'electronics_unit_count': electronics_unit_count,
        'phones_unit_count': phones_unit_count,
        'accessories_unit_count': accessories_unit_count,
        # Financial stats
        'total_purchase_value': total_purchase_value,
        'total_selling_value': total_selling_value,
        'total_best_value': total_best_value,
        'expected_profit': expected_profit,
        'expected_profit_margin': expected_profit_margin,
        'best_price_profit': best_price_profit,
        
        'page_title': 'Inventory',
        'page_subtitle': 'Manage your stock',
    }
    return render(request, 'epa/inventory.html', context)


@login_required
def low_stock(request):
    """View all low stock items with filters and pagination"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
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
        'company': company,
        'page_obj': page_obj,
        'total_count': len(low_stock_items),
        'search_query': search_query,
        'category_filter': category_filter,
        'stock_filter': stock_filter,
        'per_page': per_page,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Low Stock Items',
        'page_subtitle': 'Items that need restocking',
    }
    return render(request, 'epa/low_stock.html', context)


@login_required
def stock_movement(request):
    """View stock movement history with pagination and filters"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
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
        'company': company,
        'page_obj': page_obj,
        'movements': page_obj.object_list,
        'total_count': movements.count(),
        'search_query': search_query,
        'movement_type': movement_type,
        'per_page': per_page,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Stock Movements',
        'page_subtitle': 'Inventory transaction history',
    }
    return render(request, 'epa/stock_movement.html', context)


@login_required
def customer_list(request):
    """List all customers"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    customers = Customer.objects.filter(company=company).order_by('-created_at')[:50]
    
    context = {
        'company': company,
        'customers': customers,
        'total_count': customers.count(),
        'is_viewing_company': is_viewing_company,
        'page_title': 'Customers',
        'page_subtitle': 'Customer management',
    }
    return render(request, 'epa/customers.html', context)


@login_required
def customer_create(request):
    """Create a new customer"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    # Placeholder
    messages.info(request, 'Customer creation coming soon.')
    return redirect('/epa/customers/')



# ============================================
# BULK UNIT TRANSFER
# ============================================

@login_required
def bulk_transfer(request):
    """
    Bulk-transfer units (IMEI / Serial) between:
      - Branch A  →  Branch B
      - User X    →  User Y

    The user pastes one identifier per line (IMEI or Serial).
    Each identifier is matched against the Unit model; only units
    belonging to the active company are affected.
    """
    from apps.epa_shop.product_views import get_or_create_owner_from_user

    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # ---------- Permission gate ----------
    is_authorized = (
        is_viewing_company or
        request.user.role in ('super_admin', 'company_admin', 'company_manager', 'stock_controller')
    )
    if not is_authorized:
        messages.error(request, 'You do not have permission to perform bulk transfers.')
        return redirect('/epa_shop/inventory/')

    # ---------- Dropdown data ----------
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    users = (
        User.objects
        .filter(company=company, is_active=True)
        .exclude(role='super_admin')
        .order_by('first_name', 'last_name', 'username')
    )

    # ---------- Result summary (populated on POST) ----------
    summary = None

    if request.method == 'POST':
        transfer_type = request.POST.get('transfer_type', 'branch')

        # from_mode: 'specific' (use the dropdown) | 'anywhere' (no source filter)
        from_mode = request.POST.get('from_mode', 'specific')

        # ----- Branch transfer inputs -----
        from_branch_id = request.POST.get('from_branch', '').strip()
        to_branch_id   = request.POST.get('to_branch', '').strip()

        # ----- User transfer inputs -----
        from_user_id = request.POST.get('from_user', '').strip()
        to_user_id   = request.POST.get('to_user', '').strip()

        # ----- Identifiers ----------
        raw = request.POST.get('identifiers', '')
        identifiers = [
            line.strip()
            for line in raw.replace(',', '\n').splitlines()
            if line.strip()
        ]
        seen = set()
        identifiers = [x for x in identifiers if not (x in seen or seen.add(x))]

        # ---------- Validate ----------
        errors = []
        if not identifiers:
            errors.append('Please enter at least one IMEI / Serial number.')

        if transfer_type == 'branch':
            if not to_branch_id:
                errors.append('"To Branch" is required.')
            if from_mode == 'specific' and not from_branch_id:
                errors.append('"From Branch" is required when using a specific source.')
            if from_mode == 'specific' and from_branch_id == to_branch_id:
                errors.append('Source and destination branches must be different.')
        elif transfer_type == 'user':
            if not to_user_id:
                errors.append('"To User" is required.')
            if from_mode == 'specific' and not from_user_id:
                errors.append('"From User" is required when using a specific source.')
            if from_mode == 'specific' and from_user_id == to_user_id:
                errors.append('Source and destination users must be different.')
        else:
            errors.append('Invalid transfer type.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            # ---------- Resolve targets ----------
            from_branch = to_branch = None
            from_user   = to_user   = None
            to_owner                = None

            if transfer_type == 'branch':
                to_branch = Branch.objects.filter(id=to_branch_id, company=company).first()
                if not to_branch:
                    messages.error(request, 'Invalid destination branch.')
                    return redirect('bulk-transfer')

                if from_mode == 'specific':
                    from_branch = Branch.objects.filter(id=from_branch_id, company=company).first()
                    if not from_branch:
                        messages.error(request, 'Invalid source branch.')
                        return redirect('bulk-transfer')
            else:
                to_user = User.objects.filter(id=to_user_id, company=company).first()
                if not to_user:
                    messages.error(request, 'Invalid destination user.')
                    return redirect('bulk-transfer')

                if from_mode == 'specific':
                    from_user = User.objects.filter(id=from_user_id, company=company).first()
                    if not from_user:
                        messages.error(request, 'Invalid source user.')
                        return redirect('bulk-transfer')

                to_owner = get_or_create_owner_from_user(to_user, company=company)

            # ---------- Process ----------
            moved     = []
            skipped   = []
            not_found = []

            with transaction.atomic():
                for ident in identifiers:
                    unit = (
                        Unit.objects
                        .filter(identifier=ident)
                        .select_related(
                            'phone', 'phone__branch',
                            'electronic', 'electronic__branch',
                            'owner',
                        )
                        .first()
                    )

                    if not unit:
                        not_found.append(ident)
                        continue

                    product = unit.phone or unit.electronic
                    if not product or product.company_id != company.id:
                        skipped.append((ident, 'Belongs to a different company'))
                        continue

                    # ============================================
                    # SOLD GUARD — sold units are not transferable
                    # ============================================
                    if unit.status == 'sold':
                        skipped.append((
                            ident,
                            'Unit is Already SOLD and cannot be transferred'
                        ))
                        continue

                    # ============ BRANCH TRANSFER ============
                    if transfer_type == 'branch':
                        current_branch = product.branch

                        if from_mode == 'specific' and current_branch:
                            if current_branch.id != from_branch.id:
                                skipped.append((
                                    ident,
                                    f'Currently in "{current_branch.name}", not "{from_branch.name}"'
                                ))
                                continue

                        # Move the parent product to the destination branch
                        product.branch = to_branch
                        product.save(update_fields=['branch'])

                        # ✅ Touch the unit so its updated_at advances,
                        #    making the "Last Updated / Days" columns reflect
                        #    this transfer on the units page.
                        unit.save(update_fields=['updated_at'])

                        moved.append({
                            'identifier': ident,
                            'from': current_branch.name if current_branch else '-',
                            'to':   to_branch.name,
                        })

                    # ============ USER TRANSFER ============
                    else:
                        current_owner_name = ''
                        current_phone = ''
                        if unit.owner:
                            current_owner_name = unit.owner.name
                            current_phone = (unit.owner.phone or '').strip()
                        elif unit.owner_name:
                            current_owner_name = unit.owner_name
                            current_phone = (unit.owner_phone or '').strip()

                        if from_mode == 'specific' and from_user:
                            expected_phone = (from_user.phone or '').strip()

                            # Case A: source user has a phone — match by phone
                            if expected_phone:
                                if current_phone != expected_phone:
                                    skipped.append((
                                        ident,
                                        f'Assigned to "{current_owner_name or "nobody"}", '
                                        f'not "{from_user.get_full_name() or from_user.username}"'
                                    ))
                                    continue
                            # Case B: source user has no phone — match by name
                            else:
                                expected_name = (
                                    from_user.get_full_name() or from_user.username
                                ).strip().lower()
                                actual_name = (current_owner_name or '').strip().lower()
                                if actual_name != expected_name:
                                    skipped.append((
                                        ident,
                                        f'Assigned to "{current_owner_name or "nobody"}", '
                                        f'not "{from_user.get_full_name() or from_user.username}"'
                                    ))
                                    continue

                        # Apply — reassign owner.
                        # ✅ Include 'updated_at' in update_fields so auto_now
                        #    actually fires. Without it Django skips the
                        #    auto-update and the "Last Updated" column stays stale.
                        unit.owner = to_owner
                        unit.owner_name = to_owner.name if to_owner else ''
                        unit.owner_phone = to_owner.phone if to_owner else ''
                        unit.save(update_fields=[
                            'owner', 'owner_name', 'owner_phone', 'updated_at',
                        ])

                        moved.append({
                            'identifier': ident,
                            'from': current_owner_name or 'unassigned',
                            'to':   to_owner.name if to_owner else '-',
                        })

            summary = {
                'transfer_type': transfer_type,
                'from_mode': from_mode,
                'from_label': (
                    (from_branch.name if from_branch else 'Anywhere')
                    if transfer_type == 'branch'
                    else (from_user.get_full_name() or from_user.username
                          if from_user else 'Anywhere')
                ),
                'to_label': (
                    to_branch.name if transfer_type == 'branch'
                    else (to_user.get_full_name() or to_user.username)
                ),
                'moved':     moved,
                'skipped':   skipped,
                'not_found': not_found,
                'total':     len(identifiers),
            }

            if moved:
                messages.success(
                    request,
                    f'Successfully transferred {len(moved)} of {len(identifiers)} unit(s).'
                )
            if skipped or not_found:
                messages.warning(
                    request,
                    f'{len(skipped)} skipped, {len(not_found)} not found.'
                )

    context = {
        'company': company,
        'branches': branches,
        'users': users,
        'summary': summary,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Bulk Unit Transfer',
        'page_subtitle': 'Move many IMEI / Serial units at once',
    }
    return render(request, 'epa/bulk_transfer.html', context)

# ============================================
# BULK TRANSFER — STOCK CHECK (AJAX)
# ============================================

@login_required
@require_POST
def bulk_transfer_check(request):
    """
    JSON endpoint: given a list of identifiers, return the status of each.

    Status values:
      found           – exists in this company, ready to transfer
      duplicate       – appears more than once in the submitted list
      another_company – exists but belongs to a different company
      not_found       – doesn't exist anywhere anywhere in the DB
    """
    company, is_viewing_company = get_active_company(request)
    if not company:
        return JsonResponse({'error': 'No company'}, status=400)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    identifiers = payload.get('identifiers', []) or []

    # Count occurrences to detect duplicates within this submission
    counts = Counter(identifiers)

    # Track which identifiers we've already emitted a non-duplicate row for
    seen_in_results = set()

    results = []
    for ident in identifiers:
        # Flag 2nd+ occurrence as duplicate
        if counts[ident] > 1 and ident in seen_in_results:
            results.append({
                'identifier': ident,
                'status': 'duplicate',
                'product_code': '',
                'product_name': '',
                'branch': '',
                'owner': '',
            })
            continue

        unit = (
            Unit.objects
            .filter(identifier=ident)
            .select_related(
                'phone', 'phone__branch', 'phone__company',
                'electronic', 'electronic__branch', 'electronic__company',
                'owner',
            )
            .first()
        )

        if not unit:
            results.append({
                'identifier': ident,
                'status': 'not_found',
                'product_code': '',
                'product_name': '',
                'branch': '',
                'owner': '',
            })
            seen_in_results.add(ident)
            continue

        product = unit.phone or unit.electronic
        if not product:
            results.append({
                'identifier': ident,
                'status': 'not_found',
                'product_code': '',
                'product_name': '',
                'branch': '',
                'owner': '',
            })
            seen_in_results.add(ident)
            continue

        if product.company_id != company.id:
            results.append({
                'identifier': ident,
                'status': 'another_company',
                'product_code': product.product_code or '',
                'product_name': getattr(product, 'name', '') or '',
                'branch': product.branch.name if product.branch else '',
                'owner': '',
            })
            seen_in_results.add(ident)
            continue

        # Sold units — flag them in the preview as "sold" rather than "found"
        if unit.status == 'sold':
            results.append({
                'identifier': ident,
                'status': 'sold',
                'product_code': product.product_code or '',
                'product_name': getattr(product, 'name', '') or '',
                'branch': product.branch.name if product.branch else '',
                'owner': unit.owner.name if unit.owner else (unit.owner_name or ''),
            })
            seen_in_results.add(ident)
            continue

        owner_label = ''
        if unit.owner:
            owner_label = unit.owner.name
        elif unit.owner_name:
            owner_label = unit.owner_name

        results.append({
            'identifier': ident,
            'status': 'found',
            'product_code': product.product_code or '',
            'product_name': getattr(product, 'name', '') or '',
            'branch': product.branch.name if product.branch else '',
            'owner': owner_label,
        })
        seen_in_results.add(ident)

    return JsonResponse({'results': results})
    
    