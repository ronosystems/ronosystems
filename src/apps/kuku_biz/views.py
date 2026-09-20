"""
Kuku Biz — Views

All views are company-scoped. A user only sees data for their own company.
Super admin in support mode sees the target company's data.
"""

from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_POST

from apps.companies.support_utils import get_active_company
from apps.epa_shop.models import Branch
from .models import (
    Flock, EggProduction, Customer, EggSale, EggSaleItem,
    FeedType, FeedRecord, HealthRecord, Mortality,
    Expense, InventoryItem, PriceHistory,
    INVENTORY_ITEM_TYPE_CHOICES,
    EGG_UNIT_CHOICES,
)


# ============================================================
# DECORATORS — Role Gating
# ============================================================

def kuku_write_access(view_func):
    """Only admins, managers, stock controllers can modify Kuku Biz data."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role not in [
            'super_admin', 'company_admin',
            'company_manager', 'stock_controller'
        ]:
            messages.error(request, 'You do not have permission to modify Kuku Biz records.')
            return redirect('kuku_biz:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def kuku_sales_access(view_func):
    """Cashiers and agents can record sales and customers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role not in [
            'super_admin', 'company_admin', 'company_manager',
            'stock_controller', 'company_cashier', 'company_agent'
        ]:
            messages.error(request, 'You do not have permission for this action.')
            return redirect('kuku_biz:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ============================================================
# HELPERS
# ============================================================

def _require_company(request):
    """
    Return (company, is_viewing_company) or (None, False).
    Uses the shared support_utils so support mode works consistently
    across all apps (EPA Shop, Kuku Biz, etc.).
    """
    company, is_viewing_company = get_active_company(request)
    if not company:
        if request.user.role == 'super_admin':
            pass
        else:
            messages.error(request, 'No company assigned to your account.')
    return company, is_viewing_company


def _redirect_if_no_company(request, company):
    """Return a redirect response if no company is active, else None."""
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        return redirect('/dashboard/')
    return None


def _to_decimal(value, default='0'):
    """Safely convert a POST value to Decimal."""
    if value is None or value == '':
        return Decimal(default)
    try:
        clean = str(value).strip().replace(',', '').replace('KES', '').strip()
        return Decimal(clean)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


# ============================================================
# DASHBOARD
# ============================================================

@login_required
def dashboard(request):
    """Kuku Biz main dashboard — company-wide or branch-scoped KPIs."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # ------------------------------------------------------------
    # Branch scoping
    # ------------------------------------------------------------
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    user_branch = request.user.branch
    can_see_all_branches = (
        request.user.role in ['super_admin', 'company_admin', 'company_manager']
        or is_viewing_company
    )

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all_branches and user_branch:
        # Force own branch
        selected_branch_id = str(user_branch.id)

    selected_branch = None
    if selected_branch_id:
        selected_branch = Branch.objects.filter(
            id=selected_branch_id, company=company
        ).first()

    # ------------------------------------------------------------
    # Base querysets — scoped by branch if needed
    # ------------------------------------------------------------
    def _scope(qs):
        """Apply branch filter if a branch is selected."""
        if selected_branch_id:
            return qs.filter(branch_id=selected_branch_id)
        return qs

    flocks_qs          = _scope(Flock.objects.filter(company=company, status='active'))
    egg_prod_qs        = _scope(EggProduction.objects.filter(company=company))
    sales_qs           = _scope(EggSale.objects.filter(company=company))
    feed_qs            = _scope(FeedRecord.objects.filter(company=company))
    health_qs          = _scope(HealthRecord.objects.filter(company=company))
    mortality_qs       = _scope(Mortality.objects.filter(company=company))
    expense_qs         = _scope(Expense.objects.filter(company=company))
    inventory_qs       = _scope(InventoryItem.objects.filter(company=company))

    # ------------------------------------------------------------
    # FLOCK KPIs
    # ------------------------------------------------------------
    active_flocks = flocks_qs
    total_birds = active_flocks.aggregate(total=Sum('current_count'))['total'] or 0
    layer_flocks = active_flocks.filter(flock_type='layer')
    broiler_flocks = active_flocks.filter(flock_type='broiler')

    # ------------------------------------------------------------
    # EGG PRODUCTION KPIs
    # ------------------------------------------------------------
    eggs_today = (
        egg_prod_qs.filter(date=today)
        .aggregate(total=Sum('eggs_collected'))['total'] or 0
    )
    eggs_this_week = (
        egg_prod_qs.filter(date__gte=week_ago)
        .aggregate(total=Sum('eggs_collected'))['total'] or 0
    )
    eggs_this_month = (
        egg_prod_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('eggs_collected'))['total'] or 0
    )

    # Layer count + lay rate
    layer_count = layer_flocks.aggregate(total=Sum('current_count'))['total'] or 0
    lay_rate = round((eggs_today / layer_count) * 100, 1) if layer_count else 0

    # ------------------------------------------------------------
    # SALES KPIs
    # ------------------------------------------------------------
    sales_today = (
        sales_qs.filter(sale_date=today)
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )
    sales_this_week = (
        sales_qs.filter(sale_date__gte=week_ago)
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )
    sales_this_month = (
        sales_qs.filter(sale_date__gte=month_ago)
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )
    sales_month_count = sales_qs.filter(sale_date__gte=month_ago).count()
    sales_outstanding_month = (
        sales_qs.filter(sale_date__gte=month_ago, status__in=['credit', 'partial'])
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )

    # ------------------------------------------------------------
    # EXPENSES
    # ------------------------------------------------------------
    feed_cost_month = (
        feed_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('cost'))['total'] or 0
    )
    health_cost_month = (
        health_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('cost'))['total'] or 0
    )
    other_expenses_month = (
        expense_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('amount'))['total'] or 0
    )
    total_expenses_month = feed_cost_month + health_cost_month + other_expenses_month
    profit_month = (sales_this_month or 0) - total_expenses_month

    # ------------------------------------------------------------
    # FEED / HEALTH / MORTALITY KPIs
    # ------------------------------------------------------------
    feed_kg_month = (
        feed_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('quantity_kg'))['total'] or 0
    )
    health_records_month = health_qs.filter(date__gte=month_ago).count()
    mortality_month = (
        mortality_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('count'))['total'] or 0
    )

    # ------------------------------------------------------------
    # INVENTORY KPIs
    # ------------------------------------------------------------
    inventory_count = inventory_qs.count()
    low_stock = (
        inventory_qs
        .filter(quantity__lte=F('reorder_level'))
        .select_related('branch')
        .order_by('branch__name', 'name')
    )
    low_stock_count = low_stock.count()

    # Total inventory value (qty × cost_per_unit) — best-effort
    inventory_value = 0
    for item in inventory_qs.only('quantity', 'cost_per_unit'):
        inventory_value += item.quantity * item.cost_per_unit

    # ------------------------------------------------------------
    # PER-BRANCH BREAKDOWN (only when viewing all branches)
    # ------------------------------------------------------------
    branch_breakdown = []
    if can_see_all_branches and not selected_branch_id:
        for b in branches:
            b_flocks = Flock.objects.filter(company=company, branch=b, status='active')
            b_birds = b_flocks.aggregate(total=Sum('current_count'))['total'] or 0
            b_eggs_today = (
                EggProduction.objects.filter(company=company, branch=b, date=today)
                .aggregate(total=Sum('eggs_collected'))['total'] or 0
            )
            b_sales_month = (
                EggSale.objects.filter(company=company, branch=b, sale_date__gte=month_ago)
                .aggregate(total=Sum('total_amount'))['total'] or 0
            )
            b_low_stock = (
                InventoryItem.objects.filter(
                    company=company, branch=b, quantity__lte=F('reorder_level')
                ).count()
            )
            branch_breakdown.append({
                'branch': b,
                'flocks': b_flocks.count(),
                'birds': b_birds,
                'eggs_today': b_eggs_today,
                'sales_month': b_sales_month,
                'low_stock': b_low_stock,
            })

    # ------------------------------------------------------------
    # Top flocks (by current count) — for the widget
    # ------------------------------------------------------------
    top_flocks = (
        active_flocks
        .select_related('branch')
        .order_by('-current_count')[:5]
    )

    # ------------------------------------------------------------
    # Recent sales (last 5) — scoped
    # ------------------------------------------------------------
    recent_sales = (
        sales_qs
        .select_related('customer', 'branch')
        .order_by('-sale_date', '-created_at')[:5]
    )

    # ------------------------------------------------------------
    # Recent egg production (last 5 records) — scoped
    # ------------------------------------------------------------
    recent_eggs = (
        egg_prod_qs
        .select_related('flock', 'branch')
        .order_by('-date', '-created_at')[:5]
    )

    # ------------------------------------------------------------
    # Context
    # ------------------------------------------------------------
    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,

        # Branch scope
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'selected_branch': selected_branch,
        'can_see_all_branches': can_see_all_branches,
        'user_branch': user_branch,

        # Flock KPIs
        'active_flocks': active_flocks,
        'total_flocks': active_flocks.count(),
        'layer_flocks_count': layer_flocks.count(),
        'broiler_flocks_count': broiler_flocks.count(),
        'total_birds': total_birds,

        # Egg KPIs
        'eggs_today': eggs_today,
        'eggs_this_week': eggs_this_week,
        'eggs_this_month': eggs_this_month,
        'lay_rate': lay_rate,

        # Sales KPIs
        'sales_today': sales_today,
        'sales_this_week': sales_this_week,
        'sales_this_month': sales_this_month,
        'sales_month_count': sales_month_count,
        'sales_outstanding_month': sales_outstanding_month,

        # Expense KPIs
        'feed_cost_month': feed_cost_month,
        'health_cost_month': health_cost_month,
        'other_expenses_month': other_expenses_month,
        'total_expenses_month': total_expenses_month,
        'profit_month': profit_month,

        # Feed / Health / Mortality KPIs
        'feed_kg_month': feed_kg_month,
        'health_records_month': health_records_month,
        'mortality_month': mortality_month,

        # Inventory KPIs
        'inventory_count': inventory_count,
        'low_stock': low_stock,
        'low_stock_count': low_stock_count,
        'inventory_value': inventory_value,

        # Per-branch + widgets
        'branch_breakdown': branch_breakdown,
        'top_flocks': top_flocks,
        'recent_sales': recent_sales,
        'recent_eggs': recent_eggs,

        'page_title': 'Kuku Biz Dashboard',
        'page_subtitle': selected_branch.name if selected_branch else company.name,
    }
    return render(request, 'kuku_biz/dashboard.html', context)


# ============================================================
# FLOCKS
# ============================================================

@login_required
def flock_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flocks = Flock.objects.filter(company=company).order_by('-date_acquired')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'flocks': flocks,
        'page_title': 'Flocks',
        'page_subtitle': f'{flocks.count()} total',
    }
    return render(request, 'kuku_biz/flocks.html', context)


@login_required
@kuku_write_access
def flock_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            Flock.objects.create(
                company=company,
                name=request.POST.get('name', '').strip(),
                flock_type=request.POST.get('flock_type', 'layer'),
                breed=request.POST.get('breed', '').strip(),
                date_acquired=request.POST.get('date_acquired') or timezone.now().date(),
                initial_count=int(request.POST.get('initial_count') or 0),
                current_count=int(request.POST.get('initial_count') or 0),
                notes=request.POST.get('notes', '').strip(),
                created_by=request.user,
            )
            messages.success(request, 'Flock created successfully.')
            return redirect('kuku_biz:flock_list')
        except Exception as e:
            messages.error(request, f'Error creating flock: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'page_title': 'New Flock',
    }
    return render(request, 'kuku_biz/flock_form.html', context)


@login_required
def flock_detail(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flock = get_object_or_404(Flock, pk=pk, company=company)

    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    egg_history = (
        EggProduction.objects
        .filter(flock=flock, date__gte=thirty_days_ago)
        .order_by('date')
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'flock': flock,
        'egg_history': egg_history,
        'page_title': flock.name,
        'page_subtitle': flock.get_flock_type_display(),
    }
    return render(request, 'kuku_biz/flock_detail.html', context)


# ============================================================
# EGG PRODUCTION
# ============================================================

@login_required
def egg_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    eggs = (
        EggProduction.objects
        .filter(company=company)
        .select_related('flock')
        .order_by('-date', 'flock__name')[:100]
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'eggs': eggs,
        'page_title': 'Egg Production',
    }
    return render(request, 'kuku_biz/eggs.html', context)


@login_required
@kuku_write_access
def egg_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flocks = Flock.objects.filter(company=company, status='active')

    if request.method == 'POST':
        try:
            flock_id = request.POST.get('flock')
            date = request.POST.get('date') or timezone.now().date()

            obj, created = EggProduction.objects.update_or_create(
                flock_id=flock_id,
                date=date,
                defaults={
                    'company': company,
                    'eggs_collected': int(request.POST.get('eggs_collected') or 0),
                    'eggs_cracked': int(request.POST.get('eggs_cracked') or 0),
                    'eggs_broken': int(request.POST.get('eggs_broken') or 0),
                    'eggs_consumed': int(request.POST.get('eggs_consumed') or 0),
                    'eggs_discarded': int(request.POST.get('eggs_discarded') or 0),
                    'notes': request.POST.get('notes', '').strip(),
                    'recorded_by': request.user,
                },
            )
            action = 'updated' if not created else 'recorded'
            messages.success(request, f'Egg production {action} successfully.')
            return redirect('kuku_biz:egg_list')
        except Exception as e:
            messages.error(request, f'Error recording eggs: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'flocks': flocks,
        'today': timezone.now().date(),
        'page_title': 'Record Egg Production',
    }
    return render(request, 'kuku_biz/egg_form.html', context)


# ============================================================
# SALES
# ============================================================

@login_required
def sale_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    # ---------- Branches (for filter dropdown) ----------
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    # ---------- Determine which branch the user is scoped to ----------
    user_branch = request.user.branch  # FK on User model
    selected_branch_id = request.GET.get('branch', '').strip()

    # Role-based branch scoping:
    #   - super_admin / company_admin / company_manager: see all branches (or pick one)
    #   - everyone else (cashier, agent, staff, stock_controller): locked to own branch
    can_see_all_branches = (
        request.user.role in ['super_admin', 'company_admin', 'company_manager']
        or is_viewing_company
    )

    if not can_see_all_branches and user_branch:
        # Force their own branch — ignore ?branch param
        selected_branch_id = str(user_branch.id)

    # ---------- Sales queryset ----------
    sales_qs = (
        EggSale.objects
        .filter(company=company)
        .select_related('customer', 'recorded_by')
    )

    # Filter by branch if requested / forced
    # NOTE: EggSale model needs a `branch` FK to filter. If it doesn't have one,
    # fall back to filtering by recorded_by.branch.
    if selected_branch_id:
        sales_qs = sales_qs.filter(recorded_by__branch_id=selected_branch_id)

    # Agents see only their own sales (unless viewing/support)
    if request.user.role == 'company_agent' and not is_viewing_company:
        sales_qs = sales_qs.filter(recorded_by=request.user)

    sales = sales_qs.order_by('-sale_date', '-created_at')[:200]

    # ---------- Egg price list (latest per unit type) ----------
    # Get the most recent price for each unit type
    price_map = {}
    for unit_code, unit_label in [('egg', 'Per Egg'), ('tray', 'Per Tray (30)'), ('crate', 'Per Crate (360)')]:
        latest = (
            PriceHistory.objects
            .filter(company=company, unit=unit_code)
            .order_by('-effective_date', '-created_at')
            .first()
        )
        price_map[unit_code] = {
            'label': unit_label,
            'price': latest.price if latest else None,
            'effective_date': latest.effective_date if latest else None,
        }

    # ---------- Inventory stock for eggs/trays/crates ----------
    # We look for inventory items whose item_type is egg_tray or egg_crate
    stock_items = (
        InventoryItem.objects
        .filter(company=company, item_type__in=['egg_tray', 'egg_crate'])
        .select_related('branch')
    )

    if selected_branch_id:
        stock_items = stock_items.filter(branch_id=selected_branch_id)

    # Group stock by branch for display
    stock_by_branch = {}
    for item in stock_items:
        key = item.branch.name if item.branch else 'Unassigned'
        stock_by_branch.setdefault(key, []).append(item)

    # ---------- Sales totals for the current filter ----------
    total_sales = sales_qs.aggregate(total=Sum('total_amount'))['total'] or 0
    total_paid = sales_qs.aggregate(total=Sum('amount_paid'))['total'] or 0
    total_balance = total_sales - total_paid

    # ---------- Context ----------
    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sales': sales,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all_branches,
        'user_branch': user_branch,

        'price_map': price_map,
        'stock_by_branch': stock_by_branch,

        'total_sales': total_sales,
        'total_paid': total_paid,
        'total_balance': total_balance,

        'page_title': 'Egg Sales',
        'page_subtitle': 'Recent sales log',
    }
    return render(request, 'kuku_biz/sales.html', context)


@login_required
@kuku_sales_access
def sale_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    customers = Customer.objects.filter(company=company, is_active=True)

    if request.method == 'POST':
        try:
            customer_id = request.POST.get('customer') or None

            sale = EggSale.objects.create(
                company=company,
                customer_id=customer_id,
                invoice_number=request.POST.get('invoice_number', '').strip(),
                sale_date=request.POST.get('sale_date') or timezone.now().date(),
                amount_paid=_to_decimal(request.POST.get('amount_paid')),
                payment_method=request.POST.get('payment_method', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
                status='pending',
            )

            unit = request.POST.get('unit', 'tray')
            quantity = int(request.POST.get('quantity') or 0)
            unit_price = _to_decimal(request.POST.get('unit_price'))

            EggSaleItem.objects.create(
                sale=sale,
                unit=unit,
                quantity=quantity,
                unit_price=unit_price,
            )

            sale.recalc_total()

            paid = _to_decimal(request.POST.get('amount_paid'))
            if paid <= 0:
                sale.status = 'credit'
            elif paid < sale.total_amount:
                sale.status = 'partial'
            else:
                sale.status = 'paid'
            sale.save(update_fields=['status'])

            messages.success(request, f'Sale #{sale.pk} recorded as {sale.get_status_display()}.')
            return redirect('kuku_biz:sale_list')
        except Exception as e:
            messages.error(request, f'Error recording sale: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'customers': customers,
        'today': timezone.now().date(),
        'page_title': 'New Egg Sale',
    }
    return render(request, 'kuku_biz/sale_form.html', context)


@login_required
@kuku_sales_access
@require_POST
def sale_mark_paid(request, pk):
    """Mark a sale as fully paid — sets amount_paid = total_amount."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(EggSale, pk=pk, company=company)

    if sale.status == 'paid':
        messages.info(request, 'This sale is already marked as paid.')
        return redirect('kuku_biz:sale_list')

    sale.amount_paid = sale.total_amount
    sale.status = 'paid'
    sale.save(update_fields=['amount_paid', 'status'])

    messages.success(
        request,
        f'Sale #{sale.pk} marked as paid (KES {sale.total_amount:,.0f}).'
    )
    return redirect('kuku_biz:sale_list')


@login_required
@kuku_sales_access
def sale_edit(request, pk):
    """Edit an existing sale — allows updating amount paid, status, notes."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(EggSale, pk=pk, company=company)

    if request.method == 'POST':
        try:
            sale.invoice_number = request.POST.get('invoice_number', '').strip()
            sale.sale_date = request.POST.get('sale_date') or sale.sale_date
            sale.payment_method = request.POST.get('payment_method', '').strip()
            sale.notes = request.POST.get('notes', '').strip()
            sale.amount_paid = _to_decimal(request.POST.get('amount_paid'))

            if sale.amount_paid <= 0:
                sale.status = 'credit'
            elif sale.amount_paid < sale.total_amount:
                sale.status = 'partial'
            else:
                sale.status = 'paid'

            sale.save()

            item = sale.items.first()
            if item:
                unit = request.POST.get('unit', item.unit)
                quantity = int(request.POST.get('quantity') or item.quantity)
                unit_price = _to_decimal(
                    request.POST.get('unit_price'),
                    default=str(item.unit_price)
                )

                item.unit = unit
                item.quantity = quantity
                item.unit_price = unit_price
                item.save()

                sale.recalc_total()

                if sale.amount_paid <= 0:
                    sale.status = 'credit'
                elif sale.amount_paid < sale.total_amount:
                    sale.status = 'partial'
                else:
                    sale.status = 'paid'
                sale.save(update_fields=['status'])

            messages.success(request, f'Sale #{sale.pk} updated.')
            return redirect('kuku_biz:sale_list')
        except Exception as e:
            messages.error(request, f'Error updating sale: {e}')

    item = sale.items.first()

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sale': sale,
        'item': item,
        'customers': Customer.objects.filter(company=company, is_active=True),
        'page_title': f'Edit Sale #{sale.pk}',
    }
    return render(request, 'kuku_biz/sale_edit.html', context)


# ============================================================
# EGG PRICES
# ============================================================

@login_required
def price_list(request):
    """View and manage egg prices. Only admins/stock controllers can write."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    # Who can modify prices?
    can_edit = request.user.role in [
        'super_admin', 'company_admin', 'company_manager', 'stock_controller'
    ] or is_viewing_company

    # ---- POST: create a new price entry ----
    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'Only company admins and stock controllers can set prices.')
            return redirect('kuku_biz:price_list')

        try:
            unit = request.POST.get('unit', 'tray')
            price = _to_decimal(request.POST.get('price'))
            effective_date = request.POST.get('effective_date') or timezone.now().date()
            notes = request.POST.get('notes', '').strip()

            if price <= 0:
                messages.error(request, 'Price must be greater than zero.')
            else:
                PriceHistory.objects.create(
                    company=company,
                    unit=unit,
                    price=price,
                    effective_date=effective_date,
                    notes=notes,
                )
                messages.success(
                    request,
                    f'Price recorded: {dict(EGG_UNIT_CHOICES).get(unit, unit)} — KES {price}.'
                )
                return redirect('kuku_biz:price_list')
        except Exception as e:
            messages.error(request, f'Error saving price: {e}')

    # ---- GET: latest price per unit + history ----
    # Build "current price per unit" map (latest effective_date wins)
    latest_prices = {}
    for code, label in EGG_UNIT_CHOICES:
        latest = (
            PriceHistory.objects
            .filter(company=company, unit=code)
            .order_by('-effective_date', '-created_at')
            .first()
        )
        latest_prices[code] = {
            'label': label,
            'price': latest.price if latest else None,
            'effective_date': latest.effective_date if latest else None,
        }

    history = (
        PriceHistory.objects
        .filter(company=company)
        .order_by('-effective_date', '-created_at')[:100]
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'can_edit': can_edit,
        'latest_prices': latest_prices,
        'history': history,
        'unit_choices': EGG_UNIT_CHOICES,
        'today': timezone.now().date(),
        'page_title': 'Egg Prices',
        'page_subtitle': 'Set and track egg prices per unit',
    }
    return render(request, 'kuku_biz/prices.html', context)


@login_required
@kuku_write_access
@require_POST
def price_delete(request, pk):
    """Delete a price entry — admin/stock-controller only."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    entry = get_object_or_404(PriceHistory, pk=pk, company=company)
    label = entry.get_unit_display()
    entry.delete()
    messages.success(request, f'Price entry removed ({label}).')
    return redirect('kuku_biz:price_list')



# ============================================================
# CUSTOMERS
# ============================================================

@login_required
def customer_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    customers = Customer.objects.filter(company=company).order_by('name')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'customers': customers,
        'page_title': 'Customers',
    }
    return render(request, 'kuku_biz/customers.html', context)


@login_required
@kuku_sales_access
def customer_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            Customer.objects.create(
                company=company,
                name=request.POST.get('name', '').strip(),
                customer_type=request.POST.get('customer_type', 'individual'),
                phone=request.POST.get('phone', '').strip(),
                email=request.POST.get('email', '').strip(),
                location=request.POST.get('location', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                created_by=request.user,
            )
            messages.success(request, 'Customer added successfully.')
        except Exception as e:
            messages.error(request, f'Error adding customer: {e}')

    return redirect('kuku_biz:customer_list')


# ============================================================
# FEED
# ============================================================

@login_required
def feed_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()
    month_ago = today - timedelta(days=30)

    records = (
        FeedRecord.objects
        .filter(company=company)
        .select_related('flock', 'feed_type')
        .order_by('-date')[:100]
    )

    agg = (
        FeedRecord.objects
        .filter(company=company, date__gte=month_ago)
        .aggregate(total_cost=Sum('cost'), total_kg=Sum('quantity_kg'))
    )
    month_feed_cost = agg['total_cost'] or 0
    month_feed_kg = agg['total_kg'] or 0

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'records': records,
        'flocks': Flock.objects.filter(company=company, status='active'),
        'feed_types': FeedType.objects.filter(company=company, is_active=True),
        'month_feed_cost': month_feed_cost,
        'month_feed_kg': month_feed_kg,
        'today': today,
        'page_title': 'Feed Records',
    }
    return render(request, 'kuku_biz/feed.html', context)


@login_required
@kuku_write_access
def feed_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            FeedRecord.objects.create(
                company=company,
                flock_id=request.POST.get('flock'),
                feed_type_id=request.POST.get('feed_type') or None,
                date=request.POST.get('date') or timezone.now().date(),
                quantity_kg=request.POST.get('quantity_kg') or 0,
                cost=request.POST.get('cost') or 0,
                supplier=request.POST.get('supplier', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )
            messages.success(request, 'Feed record saved.')
        except Exception as e:
            messages.error(request, f'Error saving feed record: {e}')

    return redirect('kuku_biz:feed_list')


# ============================================================
# MORTALITY
# ============================================================

@login_required
def mortality_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()
    month_ago = today - timedelta(days=30)

    records = (
        Mortality.objects
        .filter(company=company)
        .select_related('flock')
        .order_by('-date')[:100]
    )

    month_total = (
        Mortality.objects
        .filter(company=company, date__gte=month_ago)
        .aggregate(total=Sum('count'))['total'] or 0
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'records': records,
        'flocks': Flock.objects.filter(company=company, status='active'),
        'month_total': month_total,
        'today': today,
        'page_title': 'Mortality Records',
    }
    return render(request, 'kuku_biz/mortality.html', context)


@login_required
@kuku_write_access
def mortality_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            Mortality.objects.create(
                company=company,
                flock_id=request.POST.get('flock'),
                date=request.POST.get('date') or timezone.now().date(),
                count=int(request.POST.get('count') or 0),
                cause=request.POST.get('cause', 'unknown'),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )
            messages.success(request, 'Mortality recorded. Flock count updated.')
        except Exception as e:
            messages.error(request, f'Error recording mortality: {e}')

    return redirect('kuku_biz:mortality_list')


# ============================================================
# HEALTH
# ============================================================

@login_required
def health_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()
    month_ago = today - timedelta(days=30)

    records = (
        HealthRecord.objects
        .filter(company=company)
        .select_related('flock')
        .order_by('-date')[:100]
    )

    month_cost = (
        HealthRecord.objects
        .filter(company=company, date__gte=month_ago)
        .aggregate(total=Sum('cost'))['total'] or 0
    )

    upcoming = (
        HealthRecord.objects
        .filter(company=company, next_due_date__gte=today)
        .select_related('flock')
        .order_by('next_due_date')[:10]
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'records': records,
        'flocks': Flock.objects.filter(company=company, status='active'),
        'month_cost': month_cost,
        'upcoming': upcoming,
        'today': today,
        'page_title': 'Health Records',
    }
    return render(request, 'kuku_biz/health.html', context)


@login_required
@kuku_write_access
def health_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            HealthRecord.objects.create(
                company=company,
                flock_id=request.POST.get('flock'),
                date=request.POST.get('date') or timezone.now().date(),
                record_type=request.POST.get('record_type', 'vaccination'),
                product_used=request.POST.get('product_used', '').strip(),
                description=request.POST.get('description', '').strip(),
                cost=_to_decimal(request.POST.get('cost')),
                administered_by=request.POST.get('administered_by', '').strip(),
                next_due_date=request.POST.get('next_due_date') or None,
                recorded_by=request.user,
            )
            messages.success(request, 'Health record saved.')
        except Exception as e:
            messages.error(request, f'Error saving health record: {e}')

    return redirect('kuku_biz:health_list')


# ============================================================
# EXPENSES
# ============================================================

@login_required
def expense_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()
    month_ago = today - timedelta(days=30)

    expenses = (
        Expense.objects
        .filter(company=company)
        .select_related('flock')
        .order_by('-date')[:100]
    )

    month_total = (
        Expense.objects
        .filter(company=company, date__gte=month_ago)
        .aggregate(total=Sum('amount'))['total'] or 0
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'expenses': expenses,
        'flocks': Flock.objects.filter(company=company, status='active'),
        'month_total': month_total,
        'today': today,
        'page_title': 'Expenses',
    }
    return render(request, 'kuku_biz/expenses.html', context)


@login_required
@kuku_write_access
def expense_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            Expense.objects.create(
                company=company,
                flock_id=request.POST.get('flock') or None,
                date=request.POST.get('date') or timezone.now().date(),
                category=request.POST.get('category', 'other'),
                description=request.POST.get('description', '').strip(),
                amount=_to_decimal(request.POST.get('amount')),
                paid_to=request.POST.get('paid_to', '').strip(),
                payment_method=request.POST.get('payment_method', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )
            messages.success(request, 'Expense recorded.')
        except Exception as e:
            messages.error(request, f'Error recording expense: {e}')

    return redirect('kuku_biz:expense_list')


# ============================================================
# INVENTORY
# ============================================================

@login_required
def inventory_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    # All active branches for this company (for the filter dropdown)
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    # Base queryset
    items = (
        InventoryItem.objects
        .filter(company=company)
        .select_related('branch')
        .order_by('branch__name', 'name')
    )

    # ── Optional branch filter via ?branch=<id> ──
    branch_filter = request.GET.get('branch', '').strip()
    if branch_filter:
        if branch_filter == 'unassigned':
            items = items.filter(branch__isnull=True)
        else:
            try:
                items = items.filter(branch_id=int(branch_filter))
            except (ValueError, TypeError):
                pass

    low_stock = items.filter(quantity__lte=F('reorder_level'))

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'items': items,
        'low_stock': low_stock,
        'branches': branches,
        'branch_filter': branch_filter,
        'today': timezone.now().date(),
        'page_title': 'Inventory',
    }
    return render(request, 'kuku_biz/inventory.html', context)


@login_required
@kuku_write_access
def inventory_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            branch_id = request.POST.get('branch') or None
            branch = None
            if branch_id:
                branch = Branch.objects.filter(
                    id=branch_id, company=company, is_active=True
                ).first()

            name = request.POST.get('name', '').strip()
            item_type = request.POST.get('item_type', 'other')
            quantity = _to_decimal(request.POST.get('quantity'))

            if not name:
                messages.error(request, 'Item name is required.')
                return render(request, 'kuku_biz/inventory_form.html', {
                    'company': company,
                    'is_viewing_company': is_viewing_company,
                    'branches': branches,
                    'item_types': INVENTORY_ITEM_TYPE_CHOICES,
                    'form_data': request.POST,
                    'page_title': 'Add Inventory Stock',
                })

            # ── Auto-merge if a matching item already exists ──
            existing = InventoryItem.objects.filter(
                company=company, branch=branch,
                name__iexact=name, item_type=item_type
            ).first()

            if existing:
                existing.quantity += quantity
                existing.save(update_fields=['quantity'])
                loc = f" at {branch.name}" if branch else ""
                messages.success(
                    request,
                    f'Added {quantity} to existing stock{loc}. '
                    f'New total: {existing.quantity} {existing.unit}.'
                )
            else:
                InventoryItem.objects.create(
                    company=company,
                    branch=branch,
                    name=name,
                    item_type=item_type,
                    quantity=quantity,
                    unit=request.POST.get('unit', '').strip(),
                    reorder_level=_to_decimal(request.POST.get('reorder_level')),
                    cost_per_unit=_to_decimal(request.POST.get('cost_per_unit')),
                    notes=request.POST.get('notes', '').strip(),
                )
                loc = f" at {branch.name}" if branch else ""
                messages.success(request, f'Inventory item saved{loc}.')

            return redirect('kuku_biz:inventory_list')
        except Exception as e:
            messages.error(request, f'Error saving inventory: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'branches': branches,
        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
        'page_title': 'Add Inventory Stock',
    }
    return render(request, 'kuku_biz/inventory_form.html', context)


@login_required
@kuku_write_access
def inventory_edit(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    item = get_object_or_404(InventoryItem, pk=pk, company=company)
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            branch_id = request.POST.get('branch') or None
            branch = None
            if branch_id:
                branch = Branch.objects.filter(
                    id=branch_id, company=company, is_active=True
                ).first()

            item.branch = branch
            item.name = request.POST.get('name', '').strip()
            item.item_type = request.POST.get('item_type', 'other')
            item.quantity = _to_decimal(request.POST.get('quantity'))
            item.unit = request.POST.get('unit', '').strip()
            item.reorder_level = _to_decimal(request.POST.get('reorder_level'))
            item.cost_per_unit = _to_decimal(request.POST.get('cost_per_unit'))
            item.notes = request.POST.get('notes', '').strip()
            item.save()

            messages.success(request, 'Inventory item updated.')
            return redirect('kuku_biz:inventory_list')
        except Exception as e:
            messages.error(request, f'Error updating inventory: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'item': item,
        'branches': branches,
        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
        'page_title': f'Edit {item.name}',
    }
    return render(request, 'kuku_biz/inventory_form.html', context)


@login_required
@kuku_write_access
@require_POST
def inventory_delete(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    item = get_object_or_404(InventoryItem, pk=pk, company=company)
    name = item.name
    item.delete()
    messages.success(request, f'Inventory item "{name}" deleted.')
    return redirect('kuku_biz:inventory_list')


@login_required
@kuku_write_access
@require_POST
def inventory_adjust(request, pk):
    """Quickly add or subtract stock from an inventory item."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    item = get_object_or_404(InventoryItem, pk=pk, company=company)

    try:
        delta = _to_decimal(request.POST.get('delta'))
        action = request.POST.get('action', 'add')

        if delta <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return redirect('kuku_biz:inventory_list')

        if action == 'subtract':
            delta = -delta

        new_qty = item.quantity + delta
        if new_qty < 0:
            messages.error(request, 'Adjustment would result in negative stock.')
            return redirect('kuku_biz:inventory_list')

        item.quantity = new_qty
        item.save(update_fields=['quantity'])

        verb = 'Added' if action == 'add' else 'Removed'
        messages.success(
            request,
            f'{verb} {abs(delta)} {item.unit or "units"} '
            f'{"to" if action == "add" else "from"} '
            f'{item.name} @ {item.branch.name if item.branch else "unassigned"}. '
            f'New stock: {item.quantity}.'
        )
    except Exception as e:
        messages.error(request, f'Error adjusting stock: {e}')

    return redirect('kuku_biz:inventory_list')


@login_required
@kuku_write_access
@require_POST
def inventory_transfer(request):
    """Transfer stock between branches."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    from_branch_id = request.POST.get('from_branch')
    to_branch_id = request.POST.get('to_branch')
    item_name = request.POST.get('item_name', '').strip()
    item_type = request.POST.get('item_type', 'other')
    quantity = _to_decimal(request.POST.get('quantity'))

    # Validate both branches belong to this company
    from_branch = Branch.objects.filter(
        id=from_branch_id, company=company, is_active=True
    ).first()
    to_branch = Branch.objects.filter(
        id=to_branch_id, company=company, is_active=True
    ).first()

    if not from_branch or not to_branch:
        messages.error(request, 'Invalid source or destination branch.')
        return redirect('kuku_biz:inventory_list')

    if from_branch.id == to_branch.id:
        messages.error(request, 'Source and destination must be different.')
        return redirect('kuku_biz:inventory_list')

    if quantity <= 0:
        messages.error(request, 'Quantity must be greater than zero.')
        return redirect('kuku_biz:inventory_list')

    from_item = InventoryItem.objects.filter(
        company=company, branch=from_branch,
        name__iexact=item_name, item_type=item_type
    ).first()

    if not from_item or from_item.quantity < quantity:
        messages.error(request, 'Insufficient stock in source branch.')
        return redirect('kuku_biz:inventory_list')

    from_item.quantity -= quantity
    from_item.save(update_fields=['quantity'])

    to_item, _ = InventoryItem.objects.get_or_create(
        company=company,
        branch=to_branch,
        name=item_name,
        item_type=item_type,
        defaults={
            'quantity': 0,
            'unit': from_item.unit or 'pcs',
            'reorder_level': from_item.reorder_level,
            'cost_per_unit': from_item.cost_per_unit,
        }
    )
    to_item.quantity += quantity
    to_item.save(update_fields=['quantity'])

    messages.success(
        request,
        f'Transferred {quantity} {from_item.unit} of "{item_name}" '
        f'from {from_branch.name} to {to_branch.name}.'
    )
    return redirect('kuku_biz:inventory_list')


# ============================================================
# REPORTS
# ============================================================

@login_required
def reports(request):
    """Kuku Biz reports — production, sales, profit/loss."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()

    try:
        period_days = int(request.GET.get('period', 30))
    except (ValueError, TypeError):
        period_days = 30
    period_days = max(1, min(period_days, 365))

    start_date = today - timedelta(days=period_days)

    # ---------- Egg Production Summary ----------
    egg_agg = (
        EggProduction.objects
        .filter(company=company, date__gte=start_date)
        .aggregate(
            collected=Sum('eggs_collected'),
            cracked=Sum('eggs_cracked'),
            broken=Sum('eggs_broken'),
            consumed=Sum('eggs_consumed'),
            discarded=Sum('eggs_discarded'),
        )
    )
    eggs_collected = egg_agg['collected'] or 0
    eggs_cracked = egg_agg['cracked'] or 0
    eggs_broken = egg_agg['broken'] or 0
    eggs_consumed = egg_agg['consumed'] or 0
    eggs_discarded = egg_agg['discarded'] or 0
    eggs_good = eggs_collected - eggs_cracked - eggs_broken

    # ---------- Sales Summary ----------
    sales_qs = EggSale.objects.filter(
        company=company,
        sale_date__gte=start_date,
        status__in=['paid', 'partial', 'credit', 'pending'],
    )
    sales_agg = sales_qs.aggregate(
        total=Sum('total_amount'),
        paid=Sum('amount_paid'),
    )
    total_sales = sales_agg['total'] or 0
    total_collected = sales_agg['paid'] or 0
    total_outstanding = total_sales - total_collected

    items_in_period = EggSaleItem.objects.filter(sale__in=sales_qs)
    eggs_sold = sum(item.eggs_count for item in items_in_period)

    # ---------- Cost Summary ----------
    feed_cost = (
        FeedRecord.objects
        .filter(company=company, date__gte=start_date)
        .aggregate(total=Sum('cost'))['total'] or 0
    )
    health_cost = (
        HealthRecord.objects
        .filter(company=company, date__gte=start_date)
        .aggregate(total=Sum('cost'))['total'] or 0
    )
    other_cost = (
        Expense.objects
        .filter(company=company, date__gte=start_date)
        .aggregate(total=Sum('amount'))['total'] or 0
    )
    total_cost = feed_cost + health_cost + other_cost
    profit = total_sales - total_cost

    # ---------- Top Customers ----------
    top_customers = (
        sales_qs
        .filter(customer__isnull=False)
        .values('customer__name')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('-total')[:5]
    )

    # ---------- Per-Flock Summary ----------
    flock_summary = []
    for f in Flock.objects.filter(company=company).order_by('name'):
        eggs = (
            EggProduction.objects
            .filter(flock=f, date__gte=start_date)
            .aggregate(total=Sum('eggs_collected'))['total'] or 0
        )
        deaths = (
            Mortality.objects
            .filter(flock=f, date__gte=start_date)
            .aggregate(total=Sum('count'))['total'] or 0
        )
        feed_kg = (
            FeedRecord.objects
            .filter(flock=f, date__gte=start_date)
            .aggregate(total=Sum('quantity_kg'))['total'] or 0
        )
        flock_summary.append({
            'flock': f,
            'eggs': eggs,
            'deaths': deaths,
            'feed_kg': feed_kg,
        })

    period_labels = {
        7: 'Last 7 days',
        30: 'Last 30 days',
        90: 'Last 90 days',
        365: 'Last 12 months',
    }
    period_label = period_labels.get(period_days, f'Last {period_days} days')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'period_days': period_days,
        'period_label': period_label,
        'start_date': start_date,
        'today': today,

        # Production
        'eggs_collected': eggs_collected,
        'eggs_cracked': eggs_cracked,
        'eggs_broken': eggs_broken,
        'eggs_consumed': eggs_consumed,
        'eggs_discarded': eggs_discarded,
        'eggs_good': eggs_good,

        # Sales
        'total_sales': total_sales,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'eggs_sold': eggs_sold,

        # Costs
        'feed_cost': feed_cost,
        'health_cost': health_cost,
        'other_cost': other_cost,
        'total_cost': total_cost,
        'profit': profit,

        # Lists
        'top_customers': top_customers,
        'flock_summary': flock_summary,

        'page_title': 'Reports',
    }
    return render(request, 'kuku_biz/reports.html', context)