from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.company.models import Branch
from .models import Phone, Electronic, Accessory, Unit, BranchStock
from django.db.models import Q
from django.http import JsonResponse
from apps.company.settings_views import get_company_settings
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
    try:
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
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            messages.info(request, 'Please select a company to view.')
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if is_viewing_company:
        branches = Branch.objects.filter(company=company, is_active=True)
        user_branch = None
    elif request.user.role == 'company_cashier':
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
        branches = Branch.objects.filter(company=company, is_active=True)
        user_branch = None

    enable_tax, tax_rate = get_pos_tax_config(company)
    company_settings = get_company_settings(company)
    receipt_settings = company_settings.get('receipt', {})

    context = {
        'company': company,
        'branches': branches,
        'page_title': 'Point of Sale',
        'page_subtitle': 'Process customer sales',
        'user_role': request.user.role,
        'user_branch': user_branch,
        'is_viewing_company': is_viewing_company,
        'support_mode': is_viewing_company,
        'enable_tax': enable_tax,
        'tax_rate': tax_rate,
        'auto_print': receipt_settings.get('auto_print', False),
    }
    return render(request, 'epa/pos.html', context)


@login_required
def pos_search_products(request):
    """Search products for POS - Cashiers see only their own branch stock."""
    try:
        company, is_viewing_company = get_active_company(request)
        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        search_term = request.GET.get('q', '').strip()
        category_filter = request.GET.get('category', 'all').strip()
        products = []

        # ============================================
        # BRANCH SCOPE
        # Cashiers only see their own branch.
        # Admins / super admins / support mode see all.
        # ============================================
        if is_viewing_company:
            cashier_branch = None
        elif request.user.role == 'company_cashier':
            cashier_branch = request.user.branch
            if not cashier_branch:
                return JsonResponse({'products': []})  # no branch = nothing to sell
        else:
            cashier_branch = None

        # ============================================
        # 1. SEARCH PHONES
        # ============================================
        phones = Phone.objects.filter(company=company, is_active=True)

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
            # 👇 Only count available units in the cashier's branch
            units_qs = Unit.objects.filter(phone=phone, status='available')
            if cashier_branch:
                units_qs = units_qs.filter(branch=cashier_branch)

            units_list = list(units_qs)

            # Cashiers should only see products they can actually sell
            if cashier_branch and not units_list:
                continue

            products.append({
                'product_code': phone.product_code,
                'name': phone.name,
                'brand': phone.brand,
                'model': phone.model,
                'category': 'Phone',
                'price': float(phone.selling_price),
                'stock': len(units_list),
                'units': [{'identifier': u.identifier, 'status': u.status} for u in units_list],
                'image': phone.image_url,
                'ram': phone.ram or '',
                'storage_capacity': phone.storage_capacity or '',
                'screen_size': phone.screen_size or '',
                'color': phone.color or '',
                'condition': phone.condition or 'new',
                'battery_capacity': phone.battery_capacity or '',
            })

        # ============================================
        # 2. SEARCH ELECTRONICS
        # ============================================
        electronics = Electronic.objects.filter(company=company, is_active=True)

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
            units_qs = Unit.objects.filter(electronic=item, status='available')
            if cashier_branch:
                units_qs = units_qs.filter(branch=cashier_branch)

            units_list = list(units_qs)

            if cashier_branch and not units_list:
                continue

            products.append({
                'product_code': item.product_code,
                'name': item.name,
                'brand': item.brand,
                'model': item.model_number,
                'category': 'Electronics',
                'price': float(item.selling_price),
                'stock': len(units_list),
                'units': [{'identifier': u.identifier, 'status': u.status} for u in units_list],
                'image': item.image_url,
                'ram': item.ram or '',
                'storage': item.storage or '',
                'processor': item.processor or '',
                'device_type': item.device_type or 'other',
                'screen_size': item.screen_size or '',
                'color': item.color or '',
            })

        # ============================================
        # 3. SEARCH ACCESSORIES
        # Accessories don't have Units — use BranchStock.
        # ============================================
        accessories = Accessory.objects.filter(company=company, is_active=True)

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
            if cashier_branch:
                # 👇 Only show the cashier's branch stock count
                stock_obj = item.stock_at(cashier_branch)
                branch_qty = stock_obj.quantity_in_stock if stock_obj else 0

                # Hide accessories the cashier's branch has none of
                if branch_qty <= 0:
                    continue

                display_stock = branch_qty
            else:
                display_stock = item.total_quantity_in_stock

            products.append({
                'product_code': item.product_code,
                'name': item.name,
                'brand': item.brand,
                'model': item.model,
                'category': 'Accessories',
                'price': float(item.selling_price),
                'stock': display_stock,
                'units': [],
                'image': item.image_url,
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
    Unified barcode / IMEI / serial / product_code lookup for POS.
    Cashiers can only match units in their own branch.
    """
    try:
        company, is_viewing_company = get_active_company(request)
        if not company:
            return JsonResponse(
                {'error': 'No company assigned', 'match': None, 'units': []},
                status=400,
            )

        q = request.GET.get('q', '').strip()
        if len(q) < 3:
            return JsonResponse({'match': None, 'units': []})

        # 👇 Branch scope
        if is_viewing_company:
            cashier_branch = None
        elif request.user.role == 'company_cashier':
            cashier_branch = request.user.branch
            if not cashier_branch:
                return JsonResponse({'match': None, 'units': []})
        else:
            cashier_branch = None

        units_payload = []

        # ============================================================
        # 1. PHONES
        # ============================================================
        phones_qs = Phone.objects.filter(company=company, is_active=True)
        seen_phone_codes = set()

        # (a) Exact match on Unit.identifier — only in cashier's branch
        phone_units = (
            Unit.objects
            .filter(
                phone__company=company,
                status='available',
                identifier__iexact=q,
            )
            .select_related('phone')
        )
        if cashier_branch:
            phone_units = phone_units.filter(branch=cashier_branch)

        for u in phone_units:
            p = u.phone
            seen_phone_codes.add(p.product_code)
            stock_qs = Unit.objects.filter(phone=p, status='available')
            if cashier_branch:
                stock_qs = stock_qs.filter(branch=cashier_branch)
            units_payload.append({
                'identifier': u.identifier,
                'unit_type': 'IMEI',
                'category': 'Phone',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model,
                'price': float(p.selling_price),
                'best_price': float(p.best_price) if p.best_price else None,
                'stock': stock_qs.count(),
                'branch_id': u.branch_id,
                'specs': {
                    'ram': p.ram or '',
                    'storage_capacity': p.storage_capacity or '',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                    'condition': p.condition or 'new',
                    'battery_capacity': p.battery_capacity or '',
                },
                'image': p.image_url,
            })

        # (b) Match on Phone.barcode
        phone_barcode_matches = phones_qs.filter(barcode__iexact=q)
        for p in phone_barcode_matches:
            if p.product_code in seen_phone_codes:
                continue
            stock_qs = Unit.objects.filter(phone=p, status='available')
            if cashier_branch:
                stock_qs = stock_qs.filter(branch=cashier_branch)
            branch_stock = stock_qs.count()
            if cashier_branch and branch_stock == 0:
                continue  # skip barcode for products not stocked here
            seen_phone_codes.add(p.product_code)
            units_payload.append({
                'identifier': p.barcode,
                'unit_type': 'Barcode',
                'category': 'Phone',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model,
                'price': float(p.selling_price),
                'best_price': float(p.best_price) if p.best_price else None,
                'stock': branch_stock,
                'branch_id': None,
                'specs': {
                    'ram': p.ram or '',
                    'storage_capacity': p.storage_capacity or '',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                    'condition': p.condition or 'new',
                    'battery_capacity': p.battery_capacity or '',
                },
                'image': p.image_url,
            })

        # (c) Fallback: partial match on Phone.product_code
        phone_code_matches = phones_qs.filter(product_code__icontains=q)
        for p in phone_code_matches:
            if p.product_code in seen_phone_codes:
                continue
            stock_qs = Unit.objects.filter(phone=p, status='available')
            if cashier_branch:
                stock_qs = stock_qs.filter(branch=cashier_branch)
            branch_stock = stock_qs.count()
            if cashier_branch and branch_stock == 0:
                continue
            seen_phone_codes.add(p.product_code)
            units_payload.append({
                'identifier': p.product_code,
                'unit_type': 'SKU',
                'category': 'Phone',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model,
                'price': float(p.selling_price),
                'best_price': float(p.best_price) if p.best_price else None,
                'stock': branch_stock,
                'branch_id': None,
                'specs': {
                    'ram': p.ram or '',
                    'storage_capacity': p.storage_capacity or '',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                    'condition': p.condition or 'new',
                    'battery_capacity': p.battery_capacity or '',
                },
                'image': p.image_url,
            })

        # ============================================================
        # 2. ELECTRONICS
        # ============================================================
        electronics_qs = Electronic.objects.filter(company=company, is_active=True)
        seen_elec_codes = set()

        electronic_units = (
            Unit.objects
            .filter(
                electronic__company=company,
                status='available',
                identifier__iexact=q,
            )
            .select_related('electronic')
        )
        if cashier_branch:
            electronic_units = electronic_units.filter(branch=cashier_branch)

        for u in electronic_units:
            p = u.electronic
            seen_elec_codes.add(p.product_code)
            stock_qs = Unit.objects.filter(electronic=p, status='available')
            if cashier_branch:
                stock_qs = stock_qs.filter(branch=cashier_branch)
            units_payload.append({
                'identifier': u.identifier,
                'unit_type': 'Serial',
                'category': 'Electronics',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model_number,
                'price': float(p.selling_price),
                'best_price': float(p.best_price) if p.best_price else None,
                'stock': stock_qs.count(),
                'branch_id': u.branch_id,
                'specs': {
                    'ram': p.ram or '',
                    'storage': p.storage or '',
                    'processor': p.processor or '',
                    'device_type': p.device_type or 'other',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                },
                'image': p.image_url,
            })

        elec_barcode_matches = electronics_qs.filter(barcode__iexact=q)
        for p in elec_barcode_matches:
            if p.product_code in seen_elec_codes:
                continue
            stock_qs = Unit.objects.filter(electronic=p, status='available')
            if cashier_branch:
                stock_qs = stock_qs.filter(branch=cashier_branch)
            branch_stock = stock_qs.count()
            if cashier_branch and branch_stock == 0:
                continue
            seen_elec_codes.add(p.product_code)
            units_payload.append({
                'identifier': p.barcode,
                'unit_type': 'Barcode',
                'category': 'Electronics',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model_number,
                'price': float(p.selling_price),
                'best_price': float(p.best_price) if p.best_price else None,
                'stock': branch_stock,
                'branch_id': None,
                'specs': {
                    'ram': p.ram or '',
                    'storage': p.storage or '',
                    'processor': p.processor or '',
                    'device_type': p.device_type or 'other',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                },
                'image': p.image_url,
            })

        elec_code_matches = electronics_qs.filter(product_code__icontains=q)
        for p in elec_code_matches:
            if p.product_code in seen_elec_codes:
                continue
            stock_qs = Unit.objects.filter(electronic=p, status='available')
            if cashier_branch:
                stock_qs = stock_qs.filter(branch=cashier_branch)
            branch_stock = stock_qs.count()
            if cashier_branch and branch_stock == 0:
                continue
            seen_elec_codes.add(p.product_code)
            units_payload.append({
                'identifier': p.product_code,
                'unit_type': 'SKU',
                'category': 'Electronics',
                'product_code': p.product_code,
                'name': p.name,
                'brand': p.brand,
                'model': p.model_number,
                'price': float(p.selling_price),
                'best_price': float(p.best_price) if p.best_price else None,
                'stock': branch_stock,
                'branch_id': None,
                'specs': {
                    'ram': p.ram or '',
                    'storage': p.storage or '',
                    'processor': p.processor or '',
                    'device_type': p.device_type or 'other',
                    'screen_size': p.screen_size or '',
                    'color': p.color or '',
                },
                'image': p.image_url,
            })

        # ============================================================
        # 3. ACCESSORIES — branch-aware via BranchStock
        # ============================================================
        accessories_qs = Accessory.objects.filter(company=company, is_active=True)

        acc_barcode_matches = accessories_qs.filter(barcode__iexact=q)
        acc_code_matches = accessories_qs.filter(product_code__iexact=q)
        acc_partial_matches = accessories_qs.filter(product_code__icontains=q)

        acc_seen = set()
        acc_combined = []
        for a in list(acc_barcode_matches) + list(acc_code_matches) + list(acc_partial_matches):
            if a.id in acc_seen:
                continue
            acc_seen.add(a.id)
            acc_combined.append(a)

        for a in acc_combined:
            if cashier_branch:
                stock_obj = a.stock_at(cashier_branch)
                branch_qty = stock_obj.quantity_in_stock if stock_obj else 0
                if branch_qty <= 0:
                    continue
                display_stock = branch_qty
            else:
                display_stock = a.total_quantity_in_stock

            if a.barcode and a.barcode.lower() == q.lower():
                identifier = a.barcode
                unit_type_label = 'Barcode'
            else:
                identifier = a.product_code
                unit_type_label = 'SKU'

            units_payload.append({
                'identifier': identifier,
                'unit_type': unit_type_label,
                'category': 'Accessories',
                'product_code': a.product_code,
                'name': a.name,
                'brand': a.brand,
                'model': a.model,
                'price': float(a.selling_price),
                'best_price': float(a.best_price) if a.best_price else None,
                'stock': display_stock,
                'branch_id': None,
                'specs': {
                    'accessory_type': a.accessory_type or 'other',
                    'compatible_phone_models': a.compatible_phone_models or '',
                },
                'image': a.image_url,
            })

        def _match_rank(u):
            ident = (u.get('identifier') or '').lower()
            code  = (u.get('product_code') or '').lower()
            qt    = q.lower()
            if ident == qt: return (0, ident)
            if code == qt: return (1, ident)
            if qt in ident or qt in code: return (2, ident)
            return (3, ident)

        units_payload.sort(key=_match_rank)
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
    """Search IMEI/Serial for POS — cashiers only see their branch."""
    try:
        company, is_viewing_company = get_active_company(request)
        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        search_term = request.GET.get('q', '').strip()
        if len(search_term) < 3:
            return JsonResponse({'units': []})

        # Branch scope
        if is_viewing_company:
            cashier_branch = None
        elif request.user.role == 'company_cashier':
            cashier_branch = request.user.branch
            if not cashier_branch:
                return JsonResponse({'units': []})
        else:
            cashier_branch = None

        results = []

        phone_units = Unit.objects.filter(
            phone__company=company,
            identifier__icontains=search_term,
            status='available'
        ).select_related('phone')
        if cashier_branch:
            phone_units = phone_units.filter(branch=cashier_branch)

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

        electronic_units = Unit.objects.filter(
            electronic__company=company,
            identifier__icontains=search_term,
            status='available'
        ).select_related('electronic')
        if cashier_branch:
            electronic_units = electronic_units.filter(branch=cashier_branch)

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
        company, is_viewing_company = get_active_company(request)
        if not company:
            return JsonResponse({'error': 'No company assigned'}, status=400)

        if is_viewing_company:
            branches = Branch.objects.filter(company=company, is_active=True)
        elif request.user.role == 'company_cashier':
            if request.user.branch:
                branches = Branch.objects.filter(
                    company=company,
                    is_active=True,
                    id=request.user.branch.id
                )
            else:
                branches = Branch.objects.none()
        else:
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


@login_required
def pos_tax_preview(request):
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