from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.company.models import Branch
from .models import Phone, Electronic, Accessory, Unit
from django.db.models import Q
from django.http import JsonResponse
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)
import json


# ============================================
# TAX HELPER — reads Payment Settings
# ============================================

def get_pos_tax_config(company):
    """
    Return (enable_tax: bool, tax_rate: float) from the company's
    Payment Settings. Used by the POS UI to display tax live.

    Falls back to (False, 0.0) on any error so the POS never breaks.
    """
    try:
        from apps.company.settings_views import get_company_settings
        company_settings = get_company_settings(company)
        payment = company_settings.get('payment', {})
        enable_tax = bool(payment.get('enable_tax', False))
        try:
            tax_rate = float(payment.get('default_tax_rate', 0) or 0)
        except (ValueError, TypeError):
            tax_rate = 0.0
        return enable_tax, tax_rate
    except Exception:
        return False, 0.0


@login_required
def pos_dashboard(request):
    """Point of Sale Dashboard"""

    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            messages.info(request, 'Please select a company to view.')
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # ============================================
    # Filter branches based on user role
    # ============================================
    # In support mode, super admin sees all branches
    # Cashiers only see their assigned branch
    if is_viewing_company:
        # Support mode: Show all branches of the viewed company
        branches = Branch.objects.filter(company=company, is_active=True)
        user_branch = None
    elif request.user.role == 'company_cashier':
        # Cashiers only see their assigned branch
        if request.user.branch:
            branches = Branch.objects.filter(
                company=company,
                is_active=True,
                id=request.user.branch.id
            )
            user_branch = request.user.branch
        else:
            messages.warning(request, 'You are not assigned to any branch. Please contact admin.')
            return redirect('/dashboard/')
    else:
        # Admins/Managers see all branches
        branches = Branch.objects.filter(company=company, is_active=True)
        user_branch = None

    # ============================================
    # Load tax config from Payment Settings
    # ============================================
    enable_tax, tax_rate = get_pos_tax_config(company)

    context = {
        'company': company,
        'branches': branches,
        'page_title': 'Point of Sale',
        'page_subtitle': 'Process customer sales',
        'user_role': request.user.role,
        'user_branch': user_branch,
        'is_viewing_company': is_viewing_company,
        'support_mode': is_viewing_company,

        # ---- Tax settings (used by the POS cart JS) ----
        'enable_tax': enable_tax,
        'tax_rate': tax_rate,
    }
    return render(request, 'epa/pos.html', context)


@login_required
def pos_search_products(request):
    """Search products for POS - Returns all product details including specs"""
    try:
        # ============================================
        # SUPPORT MODE: Get active company
        # ============================================
        company, is_viewing_company = get_active_company(request)

        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        search_term = request.GET.get('q', '').strip()
        category_filter = request.GET.get('category', 'all').strip()
        products = []

        # ============================================
        # Branch filter (skip in support mode & for admins)
        # ============================================
        if is_viewing_company:
            user_branch = None
        elif request.user.role == 'company_cashier':
            user_branch = request.user.branch
        else:
            user_branch = None

        # ============================================
        # 1. SEARCH PHONES - FILTER BY BRANCH FOR CASHIERS
        # ============================================
        phones = Phone.objects.filter(company=company, is_active=True)

        # Apply branch filter for cashiers
        if user_branch:
            phones = phones.filter(branch=user_branch)

        if search_term:
            phones = phones.filter(
                Q(name__icontains=search_term) |
                Q(brand__icontains=search_term) |
                Q(model__icontains=search_term) |
                Q(product_code__icontains=search_term)
            )
        if category_filter != 'all' and category_filter != 'phones':
            phones = phones.none()

        for phone in phones:
            units = Unit.objects.filter(phone=phone, status='available')
            products.append({
                'product_code': phone.product_code,
                'name': phone.name,
                'brand': phone.brand,
                'model': phone.model,
                'category': 'Phone',
                'price': float(phone.selling_price),
                'stock': units.count(),
                'units': [{'identifier': u.identifier, 'status': u.status} for u in units],
                'image': phone.image.url if phone.image else None,
                'ram': phone.ram or '',
                'storage_capacity': phone.storage_capacity or '',
                'screen_size': phone.screen_size or '',
                'color': phone.color or '',
                'condition': phone.condition or 'new',
                'battery_capacity': phone.battery_capacity or '',
            })

        # ============================================
        # 2. SEARCH ELECTRONICS - FILTER BY BRANCH FOR CASHIERS
        # ============================================
        electronics = Electronic.objects.filter(company=company, is_active=True)

        # Apply branch filter for cashiers
        if user_branch:
            electronics = electronics.filter(branch=user_branch)

        if search_term:
            electronics = electronics.filter(
                Q(name__icontains=search_term) |
                Q(brand__icontains=search_term) |
                Q(model_number__icontains=search_term) |
                Q(product_code__icontains=search_term)
            )
        if category_filter != 'all' and category_filter != 'electronics':
            electronics = electronics.none()

        for item in electronics:
            units = Unit.objects.filter(electronic=item, status='available')
            products.append({
                'product_code': item.product_code,
                'name': item.name,
                'brand': item.brand,
                'model': item.model_number,
                'category': 'Electronics',
                'price': float(item.selling_price),
                'stock': units.count(),
                'units': [{'identifier': u.identifier, 'status': u.status} for u in units],
                'image': item.image.url if item.image else None,
                'ram': item.ram or '',
                'storage': item.storage or '',
                'processor': item.processor or '',
                'device_type': item.device_type or 'other',
                'screen_size': item.screen_size or '',
                'color': item.color or '',
            })

        # ============================================
        # 3. SEARCH ACCESSORIES - FILTER BY BRANCH FOR CASHIERS
        # ============================================
        accessories = Accessory.objects.filter(company=company, is_active=True)

        # Apply branch filter for cashiers
        if user_branch:
            accessories = accessories.filter(branch=user_branch)

        if search_term:
            accessories = accessories.filter(
                Q(name__icontains=search_term) |
                Q(brand__icontains=search_term) |
                Q(model__icontains=search_term) |
                Q(product_code__icontains=search_term)
            )
        if category_filter != 'all' and category_filter != 'accessories':
            accessories = accessories.none()

        for item in accessories:
            products.append({
                'product_code': item.product_code,
                'name': item.name,
                'brand': item.brand,
                'model': item.model,
                'category': 'Accessories',
                'price': float(item.selling_price),
                'stock': item.quantity_in_stock,
                'units': [],
                'image': item.image.url if item.image else None,
                'accessory_type': item.accessory_type or 'other',
                'compatible_phone_models': item.compatible_phone_models or '',
            })

        products.sort(key=lambda x: x['name'])
        return JsonResponse({'products': products})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'error': str(e), 'products': []}, status=500)


@login_required
def pos_search_barcode(request):
    """
    Unified barcode / IMEI / serial lookup for the POS search bar.

    Query params:
        q        — the scanned/typed code (required, min length 3)
        add      — '1' to only return the first exact/partial match
                   (used by the auto-add-on-Enter flow)

    Returns:
        {
          "match": { ...product payload... } | null,
          "units": [ ...all matching units... ]
        }
    """
    try:
        company, is_viewing_company = get_active_company(request)
        if not company:
            return JsonResponse({'error': 'No company assigned', 'match': None, 'units': []}, status=400)

        q = request.GET.get('q', '').strip()
        if len(q) < 3:
            return JsonResponse({'match': None, 'units': []})

        # Branch scoping (same rule as pos_search_products)
        if is_viewing_company:
            user_branch = None
        elif request.user.role == 'company_cashier':
            user_branch = request.user.branch
        else:
            user_branch = None

        units_payload = []

        # ---------- Phone units ----------
        phone_units = (
            Unit.objects
            .filter(
                phone__company=company,
                identifier__icontains=q,
                status='available',
            )
            .select_related('phone', 'phone__branch')
        )
        if user_branch:
            phone_units = phone_units.filter(phone__branch=user_branch)

        for u in phone_units:
            p = u.phone
            units_payload.append({
                'identifier': u.identifier,
                'unit_type': 'IMEI',
                'category': 'Phone',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model,
                'price': float(p.selling_price),
                'stock': Unit.objects.filter(phone=p, status='available').count(),
                'branch_id': p.branch_id,
                'specs': {
                    'ram': p.ram or '',
                    'storage_capacity': p.storage_capacity or '',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                    'condition': p.condition or 'new',
                    'battery_capacity': p.battery_capacity or '',
                },
                'image': p.image.url if p.image else None,
            })

        # ---------- Electronic units ----------
        electronic_units = (
            Unit.objects
            .filter(
                electronic__company=company,
                identifier__icontains=q,
                status='available',
            )
            .select_related('electronic', 'electronic__branch')
        )
        if user_branch:
            electronic_units = electronic_units.filter(electronic__branch=user_branch)

        for u in electronic_units:
            p = u.electronic
            units_payload.append({
                'identifier': u.identifier,
                'unit_type': 'Serial',
                'category': 'Electronics',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model_number,
                'price': float(p.selling_price),
                'stock': Unit.objects.filter(electronic=p, status='available').count(),
                'branch_id': p.branch_id,
                'specs': {
                    'ram': p.ram or '',
                    'storage': p.storage or '',
                    'processor': p.processor or '',
                    'device_type': p.device_type or 'other',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                },
                'image': p.image.url if p.image else None,
            })

        # ---------- Accessories (no Unit table — use product_code) ----------
        # Optional: barcode scanners on accessories usually scan the product_code.
        accessories = Accessory.objects.filter(
            company=company,
            is_active=True,
            product_code__icontains=q,
        )
        if user_branch:
            accessories = accessories.filter(branch=user_branch)

        for a in accessories:
            units_payload.append({
                'identifier': a.product_code,
                'unit_type': 'SKU',
                'category': 'Accessories',
                'product_code': a.product_code,
                'name': a.name,
                'brand': a.brand,
                'model': a.model,
                'price': float(a.selling_price),
                'stock': a.quantity_in_stock,
                'branch_id': a.branch_id,
                'specs': {
                    'accessory_type': a.accessory_type or 'other',
                    'compatible_phone_models': a.compatible_phone_models or '',
                },
                'image': a.image.url if a.image else None,
            })

        # Prefer exact matches first
        units_payload.sort(key=lambda x: (x['identifier'] != q, x['identifier']))

        match = units_payload[0] if units_payload else None

        return JsonResponse({
            'match': match,
            'units': units_payload,
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse(
            {'error': str(e), 'match': None, 'units': []},
            status=500,
        )


@login_required
def pos_search_imei(request):
    """Search IMEI/Serial for POS"""
    try:
        # ============================================
        # SUPPORT MODE: Get active company
        # ============================================
        company, is_viewing_company = get_active_company(request)

        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        search_term = request.GET.get('q', '').strip()

        if len(search_term) < 3:
            return JsonResponse({'units': []})

        results = []

        # ============================================
        # Branch filter (skip in support mode & for admins)
        # ============================================
        if is_viewing_company:
            user_branch = None
        elif request.user.role == 'company_cashier':
            user_branch = request.user.branch
        else:
            user_branch = None

        # Search phone units with branch filtering
        phone_units = Unit.objects.filter(
            phone__company=company,
            identifier__icontains=search_term,
            status='available'
        ).select_related('phone', 'phone__branch')

        # Apply branch filter for cashiers
        if user_branch:
            phone_units = phone_units.filter(phone__branch=user_branch)

        for unit in phone_units:
            results.append({
                'identifier': unit.identifier,
                'product_code': unit.phone.product_code,
                'product_name': unit.phone.name,
                'brand': unit.phone.brand,
                'model': unit.phone.model,
                'category': 'Phone',
                'price': float(unit.phone.selling_price),
                'unit_type': 'IMEI',
                'specs': f"RAM: {unit.phone.ram} | ROM: {unit.phone.storage_capacity}" if unit.phone.ram and unit.phone.storage_capacity else ''
            })

        # Search electronic units with branch filtering
        electronic_units = Unit.objects.filter(
            electronic__company=company,
            identifier__icontains=search_term,
            status='available'
        ).select_related('electronic', 'electronic__branch')

        # Apply branch filter for cashiers
        if user_branch:
            electronic_units = electronic_units.filter(electronic__branch=user_branch)

        for unit in electronic_units:
            results.append({
                'identifier': unit.identifier,
                'product_code': unit.electronic.product_code,
                'product_name': unit.electronic.name,
                'brand': unit.electronic.brand,
                'model': unit.electronic.model_number,
                'category': 'Electronics',
                'price': float(unit.electronic.selling_price),
                'unit_type': 'Serial',
                'specs': f"RAM: {unit.electronic.ram} | Storage: {unit.electronic.storage}" if unit.electronic.ram and unit.electronic.storage else ''
            })

        return JsonResponse({'units': results})

    except Exception as e:
        print(f"Error in pos_search_imei: {str(e)}")
        return JsonResponse({'error': str(e), 'units': []}, status=500)


@login_required
def pos_get_branches(request):
    """Get branches for POS - filtered by user role"""
    try:
        # ============================================
        # SUPPORT MODE: Get active company
        # ============================================
        company, is_viewing_company = get_active_company(request)

        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        # ============================================
        # Filter branches based on user role
        # ============================================
        if is_viewing_company:
            # Support mode: Show all branches
            branches = Branch.objects.filter(company=company, is_active=True)
        elif request.user.role == 'company_cashier':
            # Cashiers only see their assigned branch
            if request.user.branch:
                branches = Branch.objects.filter(
                    company=company,
                    is_active=True,
                    id=request.user.branch.id
                )
            else:
                branches = Branch.objects.none()
        else:
            # Admins/Managers see all branches
            branches = Branch.objects.filter(company=company, is_active=True)

        branch_data = [{
            'id': branch.id,
            'name': branch.name,
            'code': branch.code,
            'currency_symbol': branch.currency_symbol,
        } for branch in branches]

        return JsonResponse({'branches': branch_data})

    except Exception as e:
        return JsonResponse({'error': str(e), 'branches': []}, status=500)


# ============================================
# TAX PREVIEW — live calculation for POS UI
# ============================================

@login_required
def pos_tax_preview(request):
    """
    Return the company's current tax configuration so the POS UI can
    recalculate on the fly.

    Query params:
        subtotal — optional. If provided, returns tax and total for that amount.

    Response:
        {
          "enable_tax": bool,
          "tax_rate": float,
          "subtotal": float | null,
          "tax": float | null,
          "total": float | null
        }
    """
    try:
        company, _ = get_active_company(request)
        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        enable_tax, tax_rate = get_pos_tax_config(company)

        payload = {
            'enable_tax': enable_tax,
            'tax_rate': tax_rate,
            'subtotal': None,
            'tax': None,
            'total': None,
        }

        subtotal_raw = request.GET.get('subtotal')
        if subtotal_raw is not None:
            try:
                from decimal import Decimal, ROUND_HALF_UP
                subtotal = Decimal(str(subtotal_raw))
                if enable_tax and tax_rate > 0:
                    tax = (subtotal * Decimal(str(tax_rate)) / Decimal('100')).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                else:
                    tax = Decimal('0')
                payload['subtotal'] = float(subtotal)
                payload['tax'] = float(tax)
                payload['total'] = float(subtotal + tax)
            except Exception:
                pass

        return JsonResponse(payload)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)