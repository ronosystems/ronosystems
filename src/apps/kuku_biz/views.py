"""
Kuku Biz — Views

All views are company-scoped and branch-aware.
Super admin in support mode sees the target company's data.
"""

from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse

from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_POST

from apps.companies.support_utils import get_active_company
from apps.epa_shop.models import Branch
from .models import (
    Flock, EggProduction, Customer, EggSale, EggSaleItem,
    FeedType, FeedRecord, FeedConsumption, HealthRecord, Mortality,
    Expense, InventoryItem, PriceHistory,
    VaccineType,   
    BirdSale,
    INVENTORY_ITEM_TYPE_CHOICES,
    EGG_UNIT_CHOICES,
    TRAY_SIZE_CHOICES,
    FEED_RECORD_TYPE_CHOICES,
    FEED_PAYMENT_STATUS_CHOICES,
    HEALTH_RECORD_TYPE_CHOICES,         
    HEALTH_ITEM_KIND_CHOICES,               
    HEALTH_ADMIN_METHOD_CHOICES,            
    HEALTH_PAYMENT_STATUS_CHOICES, 
    MORTALITY_CAUSE_CHOICES,   
    EXPENSE_CATEGORY_CHOICES,  
    EXPENSE_PAYMENT_METHOD_CHOICES,      
)
import time
import cloudinary
import cloudinary.uploader
from django.conf import settings as django_settings


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
    """Return (company, is_viewing_company) or (None, False)."""
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


def _resolve_branch(request, company):
    """
    Determine the branch for a create/save operation.

    Priority:
      1. POST['branch'] (if valid and belongs to company)
      2. request.user.branch
      3. None
    """
    branch_id = request.POST.get('branch') or None
    if branch_id:
        b = Branch.objects.filter(
            id=branch_id, company=company, is_active=True
        ).first()
        if b:
            return b
    return getattr(request.user, 'branch', None)


def _can_see_all_branches(request, is_viewing_company):
    return (
        request.user.role in ['super_admin', 'company_admin', 'company_manager']
        or is_viewing_company
    )


# ============================================================
# CLOUDINARY HELPERS
# ============================================================

def _cloudinary_configure():
    """Configure Cloudinary SDK from Django settings. Idempotent."""
    cfg = getattr(django_settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


def _extract_cloudinary_key(field_value):
    """Extract a clean public_id from any value assigned to an ImageField."""
    if not field_value:
        return ''
    key = getattr(field_value, 'name', None) or str(field_value)
    return key.strip().lstrip('/')


def _destroy_cloudinary_asset(public_id):
    """Best-effort delete of a Cloudinary asset. Never raises."""
    if not public_id:
        return False
    try:
        _cloudinary_configure()
        cloudinary.uploader.destroy(str(public_id).strip().lstrip('/'))
        return True
    except Exception:
        return False


def _upload_image(file, folder, prefix):
    """Upload a file to Cloudinary and return the public_id, or ''."""
    if not file:
        return ''
    if file.size > 5 * 1024 * 1024:
        raise ValueError('Image size must be less than 5MB.')
    _cloudinary_configure()
    public_id = f"{folder}/{prefix}_{int(time.time())}"
    result = cloudinary.uploader.upload(
        file,
        public_id=public_id,
        overwrite=False,
        resource_type='image',
    )
    return result.get('public_id') or public_id


# ============================================================
# STOCK DEDUCTION
# ============================================================

def _deduct_stock_for_sale(sale):
    """
    Deduct inventory from the sale's branch based on eggs sold.

    Strategy:
      - Sum eggs across all line items
      - Look at egg containers in the sale's branch, largest tray first
      - Consume whole trays until eggs are covered
      - Return summary: (list_of_deductions, shortfall_eggs)
    """
    eggs_needed = 0
    for item in sale.items.all():
        eggs_needed += item.eggs_count

    if eggs_needed <= 0:
        return [], 0

    branch = sale.branch or getattr(sale.recorded_by, 'branch', None)
    if not branch:
        return [], eggs_needed

    candidates = (
        InventoryItem.objects
        .filter(
            company=sale.company,
            branch=branch,
            item_type__in=['egg_tray', 'egg_crate'],
            quantity__gt=0,
        )
        .order_by('-tray_size', '-quantity')
    )

    deducted = []
    remaining = eggs_needed

    for inv in candidates:
        if remaining <= 0:
            break
        per_unit = inv.eggs_per_unit
        if per_unit <= 0:
            continue

        trays_to_take = min(remaining // per_unit, int(inv.quantity))
        if trays_to_take <= 0:
            continue

        eggs_covered = trays_to_take * per_unit
        inv.quantity = float(inv.quantity) - trays_to_take
        inv.save(update_fields=['quantity'])

        deducted.append((inv, trays_to_take, eggs_covered))
        remaining -= eggs_covered

    return deducted, remaining


def _restore_stock_for_sale(sale):
    """Add eggs back to inventory (used when a sale is cancelled)."""
    branch = sale.branch or getattr(sale.recorded_by, 'branch', None)
    if not branch:
        return

    # Sum eggs sold
    eggs_to_restore = sum(item.eggs_count for item in sale.items.all())
    if eggs_to_restore <= 0:
        return

    # Prefer the largest tray in that branch
    target = (
        InventoryItem.objects
        .filter(
            company=sale.company,
            branch=branch,
            item_type__in=['egg_tray', 'egg_crate'],
            tray_size__gt=0,
        )
        .order_by('-tray_size')
        .first()
    )
    if target:
        trays_back = eggs_to_restore / target.eggs_per_unit
        target.quantity = float(target.quantity) + trays_back
        target.save(update_fields=['quantity'])


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

    # ============================================================
    # ROLE FLAGS
    # ============================================================
    role = request.user.role
    is_super_admin = role == 'super_admin' or request.user.is_superuser
    is_admin_or_manager = role in ['super_admin', 'company_admin', 'company_manager'] or request.user.is_superuser
    is_stock_controller = role == 'stock_controller'
    is_sales_role = role in ['company_cashier', 'company_agent']
    is_mpesa_agent = role == 'mpesa_agent'
    is_staff_only = role == 'company_staff'

    can_write_eggs = role in [
        'super_admin', 'company_admin', 'company_manager', 'stock_controller'
    ] or request.user.is_superuser
    can_write_sales = role in [
        'super_admin', 'company_admin', 'company_manager',
        'stock_controller', 'company_cashier', 'company_agent'
    ] or request.user.is_superuser

    # ── M-Pesa agents see ONLY the hero ──
    show_only_hero = is_mpesa_agent

    # ============================================================
    # BRANCH SCOPING
    # ============================================================
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    selected_branch = None
    if selected_branch_id:
        selected_branch = Branch.objects.filter(
            id=selected_branch_id, company=company
        ).first()

    def _scope(qs):
        """Apply branch filter when a branch is selected."""
        if selected_branch_id:
            return qs.filter(branch_id=selected_branch_id)
        return qs

    # ============================================================
    # BASE QUERYSETS
    # ============================================================
    flocks_qs = _scope(Flock.objects.filter(company=company, status='active'))
    egg_prod_qs = _scope(EggProduction.objects.filter(company=company))
    sales_qs = _scope(EggSale.objects.filter(company=company))
    bird_sales_qs = _scope(BirdSale.objects.filter(company=company))
    feed_qs = _scope(FeedRecord.objects.filter(company=company))
    health_qs = _scope(HealthRecord.objects.filter(company=company))
    mortality_qs = _scope(Mortality.objects.filter(company=company))
    expense_qs = _scope(Expense.objects.filter(company=company))
    inventory_qs = _scope(InventoryItem.objects.filter(company=company))

    # ============================================================
    # FLOCKS
    # ============================================================
    active_flocks = flocks_qs
    total_birds = active_flocks.aggregate(total=Sum('current_count'))['total'] or 0
    layer_flocks = active_flocks.filter(flock_type='layer')
    broiler_flocks = active_flocks.filter(flock_type='broiler')

    # ============================================================
    # EGGS
    # ============================================================
    eggs_today = egg_prod_qs.filter(date=today).aggregate(total=Sum('eggs_collected'))['total'] or 0
    eggs_this_week = egg_prod_qs.filter(date__gte=week_ago).aggregate(total=Sum('eggs_collected'))['total'] or 0
    eggs_this_month = egg_prod_qs.filter(date__gte=month_ago).aggregate(total=Sum('eggs_collected'))['total'] or 0

    layer_count = layer_flocks.aggregate(total=Sum('current_count'))['total'] or 0
    lay_rate = round((eggs_today / layer_count) * 100, 1) if layer_count else 0

    # ============================================================
    # EGG SALES
    # ============================================================
    sales_today = sales_qs.filter(sale_date=today).aggregate(total=Sum('total_amount'))['total'] or 0
    sales_this_week = sales_qs.filter(sale_date__gte=week_ago).aggregate(total=Sum('total_amount'))['total'] or 0
    sales_this_month = sales_qs.filter(sale_date__gte=month_ago).aggregate(total=Sum('total_amount'))['total'] or 0
    sales_month_count = sales_qs.filter(sale_date__gte=month_ago).count()
    sales_outstanding_month = (
        sales_qs.filter(sale_date__gte=month_ago, status__in=['credit', 'partial'])
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )

    # Total eggs sold in the last 30 days
    eggs_sold_month = sum(
        item.eggs_count
        for item in EggSaleItem.objects.filter(
            sale__company=company,
            sale__sale_date__gte=month_ago,
            sale__status__in=['paid', 'partial', 'credit', 'pending'],
        )
    )

    # ============================================================
    # BIRD SALES (broilers / spent hens)
    # ============================================================
    bird_sales_today = (
        bird_sales_qs.filter(date=today)
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )
    bird_sales_this_month = (
        bird_sales_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('total_amount'))['total'] or 0
    )
    birds_sold_this_month = (
        bird_sales_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('birds_sold'))['total'] or 0
    )
    bird_sales_count_month = bird_sales_qs.filter(date__gte=month_ago).count()

    # ============================================================
    # EXPENSES
    # ============================================================
    feed_cost_month = feed_qs.filter(date__gte=month_ago).aggregate(total=Sum('cost'))['total'] or 0
    health_cost_month = health_qs.filter(date__gte=month_ago).aggregate(total=Sum('cost'))['total'] or 0
    other_expenses_month = expense_qs.filter(date__gte=month_ago).aggregate(total=Sum('amount'))['total'] or 0
    total_expenses_month = feed_cost_month + health_cost_month + other_expenses_month

    # Combined revenue + profit (egg + bird sales)
    total_revenue_month = (sales_this_month or 0) + (bird_sales_this_month or 0)
    profit_month = total_revenue_month - total_expenses_month

    # ============================================================
    # FEED / HEALTH / MORTALITY
    # ============================================================
    feed_kg_month = feed_qs.filter(date__gte=month_ago).aggregate(total=Sum('quantity_kg'))['total'] or 0
    health_records_month = health_qs.filter(date__gte=month_ago).count()
    mortality_month = mortality_qs.filter(date__gte=month_ago).aggregate(total=Sum('count'))['total'] or 0

    # ============================================================
    # INVENTORY
    # ============================================================
    inventory_count = inventory_qs.count()
    low_stock = (
        inventory_qs
        .filter(quantity__lte=F('reorder_level'))
        .select_related('branch')
        .order_by('branch__name', 'name')
    )
    low_stock_count = low_stock.count()

    inventory_value = sum(
        (float(i.quantity) * float(i.cost_per_unit))
        for i in inventory_qs.only('quantity', 'cost_per_unit')
    )

    # Eggs in stock (respecting branch filter)
    egg_inventory_items = inventory_qs.filter(
        item_type__in=['egg_tray', 'egg_crate'], tray_size__gt=0
    ).select_related('branch')
    total_eggs_available = sum(item.total_eggs for item in egg_inventory_items)

    # ============================================================
    # BRANCH BREAKDOWN (only when viewing all)
    # ============================================================
    branch_breakdown = []
    if can_see_all and not selected_branch_id:
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
            b_bird_sales_month = (
                BirdSale.objects.filter(company=company, branch=b, date__gte=month_ago)
                .aggregate(total=Sum('total_amount'))['total'] or 0
            )
            b_low_stock = InventoryItem.objects.filter(
                company=company, branch=b, quantity__lte=F('reorder_level')
            ).count()

            b_eggs_in_stock = sum(
                item.total_eggs
                for item in InventoryItem.objects.filter(
                    company=company, branch=b,
                    item_type__in=['egg_tray', 'egg_crate'],
                    tray_size__gt=0,
                )
            )

            branch_breakdown.append({
                'branch': b,
                'flocks': b_flocks.count(),
                'birds': b_birds,
                'eggs_today': b_eggs_today,
                'eggs_in_stock': b_eggs_in_stock,
                'sales_month': b_sales_month,
                'bird_sales_month': b_bird_sales_month,
                'low_stock': b_low_stock,
            })

    # ============================================================
    # WIDGETS
    # ============================================================
    top_flocks = active_flocks.select_related('branch').order_by('-current_count')[:5]
    recent_sales = (
        sales_qs
        .select_related('customer', 'branch', 'recorded_by')
        .order_by('-sale_date', '-created_at')[:5]
    )
    recent_bird_sales = (
        bird_sales_qs
        .select_related('customer', 'branch', 'flock')
        .order_by('-date', '-created_at')[:5]
    )
    recent_eggs = (
        egg_prod_qs
        .select_related('flock', 'branch')
        .order_by('-date', '-created_at')[:5]
    )

    # ============================================================
    # CONTEXT
    # ============================================================
    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,

        # Role flags
        'is_super_admin': is_super_admin,
        'is_admin_or_manager': is_admin_or_manager,
        'is_stock_controller': is_stock_controller,
        'is_sales_role': is_sales_role,
        'is_staff_only': is_staff_only,
        'can_write_eggs': can_write_eggs,
        'can_write_sales': can_write_sales,
        'is_mpesa_agent': is_mpesa_agent,
        'show_only_hero': show_only_hero,

        # Branch
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'selected_branch': selected_branch,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        # Flocks
        'active_flocks': active_flocks,
        'total_flocks': active_flocks.count(),
        'layer_flocks_count': layer_flocks.count(),
        'broiler_flocks_count': broiler_flocks.count(),
        'total_birds': total_birds,

        # Eggs
        'eggs_today': eggs_today,
        'eggs_this_week': eggs_this_week,
        'eggs_this_month': eggs_this_month,
        'eggs_sold_month': eggs_sold_month,
        'lay_rate': lay_rate,

        # Egg sales
        'sales_today': sales_today,
        'sales_this_week': sales_this_week,
        'sales_this_month': sales_this_month,
        'sales_month_count': sales_month_count,
        'sales_outstanding_month': sales_outstanding_month,

        # Bird sales
        'bird_sales_today': bird_sales_today,
        'bird_sales_this_month': bird_sales_this_month,
        'birds_sold_this_month': birds_sold_this_month,
        'bird_sales_count_month': bird_sales_count_month,

        # Expenses / profit
        'feed_cost_month': feed_cost_month,
        'health_cost_month': health_cost_month,
        'other_expenses_month': other_expenses_month,
        'total_expenses_month': total_expenses_month,
        'total_revenue_month': total_revenue_month,
        'profit_month': profit_month,

        # Feed / Health / Mortality
        'feed_kg_month': feed_kg_month,
        'health_records_month': health_records_month,
        'mortality_month': mortality_month,

        # Inventory
        'inventory_count': inventory_count,
        'low_stock': low_stock,
        'low_stock_count': low_stock_count,
        'inventory_value': inventory_value,
        'total_eggs_available': total_eggs_available,

        # Widgets
        'branch_breakdown': branch_breakdown,
        'top_flocks': top_flocks,
        'recent_sales': recent_sales,
        'recent_bird_sales': recent_bird_sales,
        'recent_eggs': recent_eggs,

        # Page meta
        'page_title': 'Kuku Biz Dashboard',
        'page_subtitle': selected_branch.name if selected_branch else company.name,
    }
    return render(request, 'kuku_biz/dashboard.html', context)


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

    # ============================================================
    # EGG PRODUCTION SUMMARY
    # ============================================================
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

    # ============================================================
    # EGG SALES SUMMARY
    # ============================================================
    egg_sales_qs = EggSale.objects.filter(
        company=company,
        sale_date__gte=start_date,
        status__in=['paid', 'partial', 'credit', 'pending'],
    )
    egg_sales_agg = egg_sales_qs.aggregate(
        total=Sum('total_amount'),
        paid=Sum('amount_paid'),
    )
    egg_sales_total = egg_sales_agg['total'] or 0
    egg_sales_collected = egg_sales_agg['paid'] or 0

    items_in_period = EggSaleItem.objects.filter(sale__in=egg_sales_qs)
    eggs_sold = sum(item.eggs_count for item in items_in_period)

    # ============================================================
    # BIRD SALES SUMMARY
    # ============================================================
    bird_sales_qs = BirdSale.objects.filter(
        company=company,
        date__gte=start_date,
    )
    bird_sales_agg = bird_sales_qs.aggregate(
        total=Sum('total_amount'),
        paid=Sum('amount_paid'),
        birds=Sum('birds_sold'),
    )
    bird_sales_total = bird_sales_agg['total'] or 0
    bird_sales_collected = bird_sales_agg['paid'] or 0
    birds_sold_count = bird_sales_agg['birds'] or 0
    bird_sales_count = bird_sales_qs.count()

    # ============================================================
    # COMBINED REVENUE
    # ============================================================
    total_sales = egg_sales_total + bird_sales_total
    total_collected = egg_sales_collected + bird_sales_collected
    total_outstanding = total_sales - total_collected

    # ============================================================
    # COST SUMMARY
    # ============================================================
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

    # Profit = all revenue − all costs
    profit = total_sales - total_cost

    # ============================================================
    # TOP CUSTOMERS (combined egg + bird sales)
    # ============================================================
    top_customers = (
        egg_sales_qs
        .filter(customer__isnull=False)
        .values('customer__name')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('-total')[:5]
    )

    # ============================================================
    # PER-FLOCK SUMMARY
    # ============================================================
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
        # Bird sales from this flock in the period
        birds_sold = (
            BirdSale.objects
            .filter(flock=f, date__gte=start_date)
            .aggregate(total=Sum('birds_sold'))['total'] or 0
        )
        bird_revenue = (
            BirdSale.objects
            .filter(flock=f, date__gte=start_date)
            .aggregate(total=Sum('total_amount'))['total'] or 0
        )
        flock_summary.append({
            'flock': f,
            'eggs': eggs,
            'deaths': deaths,
            'feed_kg': feed_kg,
            'birds_sold': birds_sold,
            'bird_revenue': bird_revenue,
        })

    # ============================================================
    # PERIOD LABEL
    # ============================================================
    period_labels = {
        7: 'Last 7 days',
        30: 'Last 30 days',
        90: 'Last 90 days',
        365: 'Last 12 months',
    }
    period_label = period_labels.get(period_days, f'Last {period_days} days')

    # ============================================================
    # CONTEXT
    # ============================================================
    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'period_days': period_days,
        'period_label': period_label,
        'start_date': start_date,
        'today': today,

        # Egg production
        'eggs_collected': eggs_collected,
        'eggs_cracked': eggs_cracked,
        'eggs_broken': eggs_broken,
        'eggs_consumed': eggs_consumed,
        'eggs_discarded': eggs_discarded,
        'eggs_good': eggs_good,
        'eggs_sold': eggs_sold,

        # Egg sales
        'egg_sales_total': egg_sales_total,
        'egg_sales_collected': egg_sales_collected,

        # Bird sales
        'bird_sales_total': bird_sales_total,
        'bird_sales_collected': bird_sales_collected,
        'bird_sales_count': bird_sales_count,
        'birds_sold_count': birds_sold_count,

        # Combined
        'total_sales': total_sales,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,

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

    
# ============================================================
# FLOCKS
# ============================================================

@login_required
def flock_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flocks = (
        Flock.objects
        .filter(company=company)
        .select_related('branch')
        .order_by('-date_acquired')
    )

    # KPI totals
    total_active_birds = (
        flocks.filter(status='active')
        .aggregate(total=Sum('current_count'))['total'] or 0
    )
    total_purchase_cost = (
        flocks.aggregate(total=Sum('total_purchase_cost'))['total'] or 0
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'flocks': flocks,
        'total_active_birds': total_active_birds,
        'total_purchase_cost': total_purchase_cost,
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

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            branch = _resolve_branch(request, company)
            Flock.objects.create(
                company=company,
                branch=branch,
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
        'branches': branches,
        'page_title': 'New Flock',
    }
    return render(request, 'kuku_biz/flock_form.html', context)


@login_required
@kuku_write_access
def flock_edit(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flock = get_object_or_404(Flock, pk=pk, company=company)
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            flock.name = request.POST.get('name', '').strip()
            flock.flock_type = request.POST.get('flock_type', 'layer')
            flock.breed = request.POST.get('breed', '').strip()

            branch_id = request.POST.get('branch') or None
            if branch_id:
                flock.branch = Branch.objects.filter(
                    id=branch_id, company=company, is_active=True
                ).first()
            else:
                flock.branch = None

            flock.date_acquired = request.POST.get('date_acquired') or flock.date_acquired
            flock.supplier = request.POST.get('supplier', '').strip()
            flock.purchase_price_per_bird = _to_decimal(request.POST.get('purchase_price'))
            flock.total_purchase_cost = _to_decimal(request.POST.get('total_purchase'))
            flock.age_at_acquisition_days = int(request.POST.get('age_at_acquisition') or 0)
            flock.notes = request.POST.get('notes', '').strip()

            flock.save()
            messages.success(request, f'Flock "{flock.name}" updated.')
            return redirect('kuku_biz:flock_list')
        except Exception as e:
            messages.error(request, f'Error updating flock: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'flock': flock,
        'branches': branches,
        'user_branch': request.user.branch,
        'today': timezone.now().date(),
        'page_title': f'Edit {flock.name}',
    }
    return render(request, 'kuku_biz/flock_form.html', context)
    

@login_required
def flock_detail(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flock = get_object_or_404(Flock, pk=pk, company=company)

    # ── Egg production history (last 30 days) ──
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    egg_history = (
        EggProduction.objects
        .filter(flock=flock, date__gte=thirty_days_ago)
        .order_by('-date')
    )
    eggs_last_30 = (
        egg_history.aggregate(total=Sum('eggs_collected'))['total'] or 0
    )

    # ── Bird sales from this flock ──
    bird_sales = (
        BirdSale.objects
        .filter(flock=flock)
        .select_related('customer', 'branch')
        .order_by('-date')[:50]
    )
    bird_sales_agg = BirdSale.objects.filter(flock=flock).aggregate(
        birds=Sum('birds_sold'),
        revenue=Sum('total_amount'),
    )
    total_birds_sold = bird_sales_agg['birds'] or 0
    total_bird_revenue = bird_sales_agg['revenue'] or 0

    # ════════════════════════════════════════════════════════════
    # FEED CONSUMPTION HISTORY (full history)
    # ════════════════════════════════════════════════════════════
    feed_consumption_qs = (
        FeedConsumption.objects
        .filter(flock=flock, company=company)
        .select_related('feed_type', 'branch', 'recorded_by')
        .order_by('-date', '-created_at')
    )

    # Full history for the table
    feed_consumption = feed_consumption_qs

    # ── Aggregate stats ──
    consumption_agg = feed_consumption_qs.aggregate(
        total_kg=Sum('quantity_kg'),
        records=Count('id'),
    )
    total_feed_kg_consumed = consumption_agg['total_kg'] or 0
    total_feed_records = consumption_agg['records'] or 0

    # Last 7 days + last 30 days totals
    week_ago = timezone.now().date() - timedelta(days=7)
    feed_kg_last_7 = (
        feed_consumption_qs.filter(date__gte=week_ago)
        .aggregate(t=Sum('quantity_kg'))['t'] or 0
    )
    feed_kg_last_30 = (
        feed_consumption_qs.filter(date__gte=thirty_days_ago)
        .aggregate(t=Sum('quantity_kg'))['t'] or 0
    )

    # ── Per-feed-type breakdown ──
    feed_breakdown = (
        feed_consumption_qs
        .values(
            'feed_type__id',
            'feed_type__name',
            'feed_type__brand',
        )
        .annotate(
            total_kg=Sum('quantity_kg'),
            entries=Count('id'),
        )
        .order_by('-total_kg')
    )

    # ── Feed cost estimate (using each feed type's cost_per_kg) ──
    # We compute this in Python so we can mix per-feed rates
    feed_cost_estimate = Decimal('0')
    for entry in feed_consumption_qs.select_related('feed_type'):
        if entry.feed_type and entry.feed_type.cost_per_kg:
            feed_cost_estimate += (
                _to_decimal(entry.feed_type.cost_per_kg)
                * _to_decimal(entry.quantity_kg)
            )

    # ── Recent feed purchases tied to this flock (if any were logged) ──
    flock_feed_purchases = (
        FeedRecord.objects
        .filter(company=company, flock=flock, record_type='purchase')
        .select_related('feed_type', 'branch')
        .order_by('-date', '-created_at')[:30]
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'flock': flock,
        'egg_history': egg_history,
        'eggs_last_30': eggs_last_30,
        'bird_sales': bird_sales,
        'total_birds_sold': total_birds_sold,
        'total_bird_revenue': total_bird_revenue,

        # Feed consumption
        'feed_consumption': feed_consumption,
        'total_feed_kg_consumed': total_feed_kg_consumed,
        'total_feed_records': total_feed_records,
        'feed_kg_last_7': feed_kg_last_7,
        'feed_kg_last_30': feed_kg_last_30,
        'feed_breakdown': feed_breakdown,
        'feed_cost_estimate': feed_cost_estimate,

        # Feed purchases tied to this flock (optional section)
        'flock_feed_purchases': flock_feed_purchases,

        'page_title': flock.name,
        'page_subtitle': flock.get_flock_type_display(),
    }
    return render(request, 'kuku_biz/flock_detail.html', context)


@login_required
@kuku_write_access
@require_POST
def flock_delete(request, pk):
    """Delete a flock. Does NOT cascade-delete related records."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    flock = get_object_or_404(Flock, pk=pk, company=company)
    name = flock.name

    # Safety: don't allow deletion if there are still active birds
    if flock.status == 'active' and flock.current_count > 0:
        messages.warning(
            request,
            f'Cannot delete "{name}" — it has {flock.current_count} active birds. '
            f'Mark it as retired, sold, or depleted first.'
        )
        return redirect('kuku_biz:flock_list')

    # Count related records before deleting (for the message)
    egg_count = flock.egg_production.count()
    feed_count = flock.feed_records.count()
    health_count = flock.health_records.count()
    mortality_count = flock.mortality_records.count()

    flock.delete()

    parts = []
    if egg_count: parts.append(f"{egg_count} egg records")
    if feed_count: parts.append(f"{feed_count} feed records")
    if health_count: parts.append(f"{health_count} health records")
    if mortality_count: parts.append(f"{mortality_count} mortality records")

    msg = f'Flock "{name}" deleted.'
    if parts:
        msg += f' Note: {", ".join(parts)} were also deleted (cascade).'

    messages.success(request, msg)
    return redirect('kuku_biz:flock_list')

# ============================================================
# BIRD SALES
# ============================================================

@login_required
@kuku_sales_access
def bird_sale_create(request):
    """Record a sale of live birds (broilers, spent hens, surplus males)."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    customers = Customer.objects.filter(company=company, is_active=True)
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    # Only active/mixed/broiler flocks can be sold from
    flocks = Flock.objects.filter(
        company=company,
        status='active',
    ).order_by('name')

    # Pre-select flock if ?flock=<id> is passed (e.g. from flock detail page)
    preselected_flock_id = request.GET.get('flock', '').strip()

    if request.method == 'POST':
        try:
            flock_id = request.POST.get('flock')
            flock = get_object_or_404(Flock, pk=flock_id, company=company)

            branch = _resolve_branch(request, company)

            birds_sold = int(request.POST.get('birds_sold') or 0)
            unit_price = _to_decimal(request.POST.get('unit_price'))
            amount_paid = _to_decimal(request.POST.get('amount_paid'))

            if birds_sold <= 0:
                messages.error(request, 'Number of birds sold must be greater than zero.')
                return redirect('kuku_biz:bird_sale_create')

            if birds_sold > flock.current_count:
                messages.error(
                    request,
                    f'Cannot sell {birds_sold} birds — only {flock.current_count} available in {flock.name}.'
                )
                return redirect('kuku_biz:bird_sale_create')

            sale = BirdSale.objects.create(
                company=company,
                branch=branch,
                flock=flock,
                customer_id=request.POST.get('customer') or None,
                buyer_name=request.POST.get('buyer_name', '').strip(),
                date=request.POST.get('date') or timezone.now().date(),
                birds_sold=birds_sold,
                unit_price=unit_price,
                total_amount=unit_price * birds_sold,
                amount_paid=amount_paid,
                payment_method=request.POST.get('payment_method', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )

            messages.success(
                request,
                f'Sale of {birds_sold} birds from {flock.name} recorded '
                f'(KES {sale.total_amount:,.0f}).'
            )
            return redirect('kuku_biz:bird_sale_list')

        except Exception as e:
            messages.error(request, f'Error recording bird sale: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'customers': customers,
        'branches': branches,
        'flocks': flocks,
        'preselected_flock_id': preselected_flock_id,
        'today': timezone.now().date(),
        'page_title': 'New Bird Sale',
        'page_subtitle': 'Record sale of live birds',
    }
    return render(request, 'kuku_biz/bird_sale_form.html', context)


@login_required
def bird_sale_list(request):
    """List recent bird sales."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    sales_qs = (
        BirdSale.objects
        .filter(company=company)
        .select_related('flock', 'customer', 'branch', 'recorded_by')
    )
    if selected_branch_id:
        sales_qs = sales_qs.filter(branch_id=selected_branch_id)

    sales = sales_qs.order_by('-date', '-created_at')[:200]

    total_birds = sales_qs.aggregate(total=Sum('birds_sold'))['total'] or 0
    total_revenue = sales_qs.aggregate(total=Sum('total_amount'))['total'] or 0
    total_paid = sales_qs.aggregate(total=Sum('amount_paid'))['total'] or 0

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sales': sales,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,
        'total_birds': total_birds,
        'total_revenue': total_revenue,
        'total_paid': total_paid,
        'total_balance': total_revenue - total_paid,
        'page_title': 'Bird Sales',
        'page_subtitle': 'Live bird sales log',
    }
    return render(request, 'kuku_biz/bird_sales.html', context)


@login_required
@kuku_sales_access
@require_POST
def bird_sale_mark_paid(request, pk):
    """Mark a bird sale as fully paid."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(BirdSale, pk=pk, company=company)

    sale.amount_paid = sale.total_amount
    sale.save(update_fields=['amount_paid'])

    messages.success(request, f'Bird sale #{sale.pk} marked as fully paid.')
    return redirect('kuku_biz:bird_sale_list')

@login_required
def bird_sale_receipt(request, pk):
    """Printable receipt for a single bird sale."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(
        BirdSale.objects.select_related('flock', 'customer', 'branch', 'recorded_by'),
        pk=pk,
        company=company,
    )

    # Role scoping (same as egg sale receipt)
    if not is_viewing_company:
        if request.user.role == 'company_agent' and sale.recorded_by != request.user:
            messages.error(request, 'You do not have permission to view this receipt.')
            return redirect('kuku_biz:bird_sale_list')

        if request.user.role not in ['super_admin', 'company_admin', 'company_manager']:
            if request.user.branch and sale.branch and sale.branch_id != request.user.branch_id:
                messages.error(request, 'You do not have permission to view receipts from other branches.')
                return redirect('kuku_biz:bird_sale_list')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sale': sale,
        'page_title': f'Bird Sale Receipt #{sale.pk}',
        'page_subtitle': sale.buyer_display,
        'auto_print': request.GET.get('print') == '1',
    }
    return render(request, 'kuku_biz/bird_sale_receipt.html', context)


@login_required
@kuku_sales_access
def bird_sale_edit(request, pk):
    """Edit an existing bird sale."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(BirdSale, pk=pk, company=company)
    customers = Customer.objects.filter(company=company, is_active=True)
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    flocks = Flock.objects.filter(company=company).order_by('name')

    if request.method == 'POST':
        try:
            # ── Compute the difference in birds if changing flock or count ──
            old_flock = sale.flock
            old_birds = sale.birds_sold

            new_flock_id = request.POST.get('flock')
            new_flock = get_object_or_404(Flock, pk=new_flock_id, company=company)
            new_birds = int(request.POST.get('birds_sold') or 0)

            if new_birds <= 0:
                messages.error(request, 'Number of birds sold must be greater than zero.')
                return redirect('kuku_biz:bird_sale_edit', pk=sale.pk)

            # ── Update fields ──
            sale.flock = new_flock
            sale.customer_id = request.POST.get('customer') or None
            sale.buyer_name = request.POST.get('buyer_name', '').strip()
            sale.date = request.POST.get('date') or sale.date
            sale.birds_sold = new_birds
            sale.unit_price = _to_decimal(request.POST.get('unit_price'))
            sale.amount_paid = _to_decimal(request.POST.get('amount_paid'))
            sale.payment_method = request.POST.get('payment_method', '').strip()
            sale.notes = request.POST.get('notes', '').strip()

            # ── Update flock counts ──
            # If flock changed → add old birds back to old flock, remove new from new flock
            if old_flock.id != new_flock.id:
                old_flock.current_count = old_flock.current_count + old_birds
                old_flock.save(update_fields=['current_count'])

                new_flock.current_count = max(new_flock.current_count - new_birds, 0)
                new_flock.save(update_fields=['current_count'])
            else:
                # Same flock → adjust by the difference
                diff = new_birds - old_birds
                new_flock.current_count = max(new_flock.current_count - diff, 0)
                new_flock.save(update_fields=['current_count'])

            # ── Recompute total ──
            sale.total_amount = sale.unit_price * sale.birds_sold
            sale.save()

            messages.success(request, f'Bird sale #{sale.pk} updated.')
            return redirect('kuku_biz:bird_sale_list')

        except Exception as e:
            messages.error(request, f'Error updating bird sale: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sale': sale,
        'customers': customers,
        'branches': branches,
        'flocks': flocks,
        'today': timezone.now().date(),
        'page_title': f'Edit Bird Sale #{sale.pk}',
    }
    return render(request, 'kuku_biz/bird_sale_form.html', context)


@login_required
@kuku_sales_access
@require_POST
def bird_sale_delete(request, pk):
    """Delete a bird sale and add the birds back to the flock."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(BirdSale, pk=pk, company=company)
    flock_name = sale.flock.name
    birds = sale.birds_sold

    # Add birds back to the flock
    flock = sale.flock
    flock.current_count = flock.current_count + birds
    flock.save(update_fields=['current_count'])

    sale.delete()

    messages.success(
        request,
        f'Bird sale deleted. {birds} bird{"s" if birds != 1 else ""} returned to "{flock_name}".'
    )
    return redirect('kuku_biz:bird_sale_list')


# ============================================================
# EGG PRODUCTION
# ============================================================

@login_required
def egg_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    # ── Base queryset ──
    eggs_qs = (
        EggProduction.objects
        .filter(company=company)
        .select_related('flock', 'branch')
    )
    if selected_branch_id:
        eggs_qs = eggs_qs.filter(branch_id=selected_branch_id)

    eggs = eggs_qs.order_by('-date', 'flock__name')[:200]

    # ── KPIs (respect branch filter) ──
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    eggs_today = (
        eggs_qs.filter(date=today)
        .aggregate(total=Sum('eggs_collected'))['total'] or 0
    )
    eggs_this_week = (
        eggs_qs.filter(date__gte=week_ago)
        .aggregate(total=Sum('eggs_collected'))['total'] or 0
    )
    eggs_this_month = (
        eggs_qs.filter(date__gte=month_ago)
        .aggregate(total=Sum('eggs_collected'))['total'] or 0
    )

    # Layer count for lay-rate calculation
    layer_flocks = Flock.objects.filter(
        company=company, status='active', flock_type='layer'
    )
    if selected_branch_id:
        layer_flocks = layer_flocks.filter(branch_id=selected_branch_id)

    layer_count = layer_flocks.aggregate(total=Sum('current_count'))['total'] or 0
    lay_rate = round((eggs_today / layer_count) * 100, 1) if layer_count else 0

    # ── Per-branch breakdown ──
    branch_breakdown = []
    if can_see_all and not selected_branch_id:
        for b in branches:
            b_eggs_today = (
                EggProduction.objects.filter(
                    company=company, branch=b, date=today
                ).aggregate(total=Sum('eggs_collected'))['total'] or 0
            )
            b_eggs_week = (
                EggProduction.objects.filter(
                    company=company, branch=b, date__gte=week_ago
                ).aggregate(total=Sum('eggs_collected'))['total'] or 0
            )
            b_eggs_month = (
                EggProduction.objects.filter(
                    company=company, branch=b, date__gte=month_ago
                ).aggregate(total=Sum('eggs_collected'))['total'] or 0
            )
            b_layer_count = (
                Flock.objects.filter(
                    company=company, branch=b,
                    status='active', flock_type='layer',
                ).aggregate(total=Sum('current_count'))['total'] or 0
            )
            b_lay_rate = round((b_eggs_today / b_layer_count) * 100, 1) if b_layer_count else 0

            branch_breakdown.append({
                'branch': b,
                'layers': b_layer_count,
                'eggs_today': b_eggs_today,
                'eggs_week': b_eggs_week,
                'eggs_month': b_eggs_month,
                'lay_rate': b_lay_rate,
            })

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'eggs': eggs,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,
        'branch_breakdown': branch_breakdown,

        'eggs_today': eggs_today,
        'eggs_this_week': eggs_this_week,
        'eggs_this_month': eggs_this_month,
        'lay_rate': lay_rate,
        'layer_count': layer_count,

        'page_title': 'Egg Production',
        'page_subtitle': 'Recent collection log',
    }
    return render(request, 'kuku_biz/eggs.html', context)


@login_required
@kuku_write_access
def egg_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    flocks = Flock.objects.filter(company=company, status='active').order_by('name')

    if request.method == 'POST':
        try:
            flock_id = request.POST.get('flock')
            date = request.POST.get('date') or timezone.now().date()
            branch = _resolve_branch(request, company)

            obj, created = EggProduction.objects.update_or_create(
                flock_id=flock_id,
                date=date,
                defaults={
                    'company': company,
                    'branch': branch,
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
        'branches': branches,
        'user_branch': request.user.branch,
        'today': timezone.now().date(),
        'page_title': 'Record Egg Production',
    }
    return render(request, 'kuku_biz/egg_form.html', context)


@login_required
@kuku_write_access
def egg_edit(request, pk):
    """Edit an existing egg production record."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(EggProduction, pk=pk, company=company)
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    flocks = Flock.objects.filter(company=company, status='active').order_by('name')

    if request.method == 'POST':
        try:
            flock_id = request.POST.get('flock')
            date = request.POST.get('date') or record.date
            branch = _resolve_branch(request, company)

            record.flock_id = flock_id
            record.date = date
            record.branch = branch
            record.eggs_collected = int(request.POST.get('eggs_collected') or 0)
            record.eggs_cracked = int(request.POST.get('eggs_cracked') or 0)
            record.eggs_broken = int(request.POST.get('eggs_broken') or 0)
            record.eggs_consumed = int(request.POST.get('eggs_consumed') or 0)
            record.eggs_discarded = int(request.POST.get('eggs_discarded') or 0)
            record.notes = request.POST.get('notes', '').strip()
            record.save()

            messages.success(request, f'Egg record for {record.date} updated.')
            return redirect('kuku_biz:egg_list')
        except Exception as e:
            messages.error(request, f'Error updating egg record: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'record': record,
        'flocks': flocks,
        'branches': branches,
        'user_branch': request.user.branch,
        'today': timezone.now().date(),
        'page_title': f'Edit Egg Record — {record.date}',
        'page_subtitle': record.flock.name,
        'is_edit': True,
    }
    return render(request, 'kuku_biz/egg_form.html', context)


@login_required
@kuku_write_access
@require_POST
def egg_delete(request, pk):
    """Delete an egg production record."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(EggProduction, pk=pk, company=company)
    label = f"{record.flock.name} — {record.date}"
    record.delete()

    messages.success(request, f'Egg record deleted ({label}).')
    return redirect('kuku_biz:egg_list') 



# ============================================================
# SALES
# ============================================================

@login_required
def sale_list(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    sales_qs = (
        EggSale.objects
        .filter(company=company)
        .select_related('customer', 'recorded_by', 'branch')
    )

    # ── FIXED: filter by the sale's own branch FK, not recorded_by.branch ──
    if selected_branch_id:
        sales_qs = sales_qs.filter(branch_id=selected_branch_id)

    if request.user.role == 'company_agent' and not is_viewing_company:
        sales_qs = sales_qs.filter(recorded_by=request.user)

    sales = sales_qs.order_by('-sale_date', '-created_at')[:200]

    # ── Latest price per (unit, tray_size) ──
    # Build a map keyed by (unit, tray_size) so the hero can show 30/45/6/12 separately.
    price_map = {}
    # Standard non-tray units
    for code, label in [('egg', 'Per Egg'), ('crate', 'Per Crate (360)')]:
        latest = (
            PriceHistory.objects
            .filter(company=company, unit=code)
            .order_by('-effective_date', '-created_at')
            .first()
        )
        price_map[f"{code}_0"] = {
            'unit': code,
            'tray_size': 0,
            'label': label,
            'price': latest.price if latest else None,
            'effective_date': latest.effective_date if latest else None,
            'image_url': latest.image_url if latest else None,
        }

    # Tray prices — one row per tray size we have a price for
    tray_sizes_seen = set()
    tray_prices = (
        PriceHistory.objects
        .filter(company=company, unit='tray')
        .order_by('-effective_date', '-created_at')
    )
    for p in tray_prices:
        key = p.tray_size or 30
        if key in tray_sizes_seen:
            continue
        tray_sizes_seen.add(key)
        price_map[f"tray_{key}"] = {
            'unit': 'tray',
            'tray_size': key,
            'label': f"Per {key}-Egg Tray",
            'price': p.price,
            'effective_date': p.effective_date,
            'image_url': p.image_url,
        }

    # If no tray prices exist at all, seed a default 30-egg entry
    if not any(k.startswith('tray_') for k in price_map):
        price_map['tray_30'] = {
            'unit': 'tray',
            'tray_size': 30,
            'label': 'Per 30-Egg Tray',
            'price': None,
            'effective_date': None,
            'image_url': None,
        }

    # ── Stock by branch (with egg totals) ──
    stock_items = (
        InventoryItem.objects
        .filter(company=company, item_type__in=['egg_tray', 'egg_crate'])
        .select_related('branch')
        .order_by('branch__name', '-tray_size')
    )
    if selected_branch_id:
        stock_items = stock_items.filter(branch_id=selected_branch_id)

    stock_by_branch = {}
    for item in stock_items:
        key = item.branch.name if item.branch else 'Unassigned'
        if key not in stock_by_branch:
            stock_by_branch[key] = {
                'items': [],
                'total_eggs': 0,
            }
        stock_by_branch[key]['items'].append(item)
        stock_by_branch[key]['total_eggs'] += item.total_eggs

    total_eggs_available = sum(item.total_eggs for item in stock_items)

    # KPIs
    total_sales = sales_qs.aggregate(total=Sum('total_amount'))['total'] or 0
    total_paid = sales_qs.aggregate(total=Sum('amount_paid'))['total'] or 0
    total_balance = total_sales - total_paid

    # ── Total eggs sold for the current filter ──
    # Re-query items for the sales in view, sum their egg counts
    sale_ids = list(sales.values_list('id', flat=True))
    total_eggs_sold = sum(
        item.eggs_count
        for item in EggSaleItem.objects.filter(sale_id__in=sale_ids)
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sales': sales,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        'price_map': price_map,
        'stock_by_branch': stock_by_branch,
        'total_eggs_available': total_eggs_available,
        'total_eggs_sold': total_eggs_sold,

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
    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            customer_id = request.POST.get('customer') or None
            branch = _resolve_branch(request, company)

            sale = EggSale.objects.create(
                company=company,
                branch=branch,
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
            try:
                tray_size = int(request.POST.get('tray_size') or 30)
            except (TypeError, ValueError):
                tray_size = 30

            quantity = int(request.POST.get('quantity') or 0)
            unit_price = _to_decimal(request.POST.get('unit_price'))

            EggSaleItem.objects.create(
                sale=sale,
                unit=unit,
                tray_size=tray_size,
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

            # ── Auto-deduct stock ──
            try:
                deducted, shortfall = _deduct_stock_for_sale(sale)
                if deducted:
                    detail = ', '.join(
                        f"{qty}×{inv.tray_size}-egg tray"
                        for inv, qty, _ in deducted
                    )
                    messages.info(request, f'Stock deducted: {detail}.')
                if shortfall > 0:
                    messages.warning(
                        request,
                        f'{shortfall} eggs could not be covered by branch stock.'
                    )
            except Exception as stock_err:
                messages.warning(request, f'Stock deduction failed: {stock_err}')

            messages.success(request, f'Sale #{sale.pk} recorded as {sale.get_status_display()}.')
            return redirect('kuku_biz:sale_list')
        except Exception as e:
            messages.error(request, f'Error recording sale: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'customers': customers,
        'branches': branches,
        'today': timezone.now().date(),
        'page_title': 'New Egg Sale',
    }
    return render(request, 'kuku_biz/sale_form.html', context)


@login_required
@kuku_sales_access
@require_POST
def sale_mark_paid(request, pk):
    """Mark a sale as fully paid."""
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

    messages.success(request, f'Sale #{sale.pk} marked as paid (KES {sale.total_amount:,.0f}).')
    return redirect('kuku_biz:sale_list')


@login_required
@kuku_sales_access
def sale_edit(request, pk):
    """Edit an existing sale — updates amount paid, notes, and the first line item."""
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
                try:
                    tray_size = int(request.POST.get('tray_size') or item.tray_size or 30)
                except (TypeError, ValueError):
                    tray_size = item.tray_size or 30

                quantity = int(request.POST.get('quantity') or item.quantity)
                unit_price = _to_decimal(
                    request.POST.get('unit_price'),
                    default=str(item.unit_price),
                )

                item.unit = unit
                item.tray_size = tray_size
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
        'tray_sizes': TRAY_SIZE_CHOICES,
        'page_title': f'Edit Sale #{sale.pk}',
    }
    return render(request, 'kuku_biz/sale_form.html', context)


# ============================================================
# SALE RECEIPT
# ============================================================

@login_required
def sale_receipt(request, pk):
    """Printable receipt for a single egg sale."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    sale = get_object_or_404(
        EggSale.objects.select_related('customer', 'branch', 'recorded_by'),
        pk=pk,
        company=company,
    )

    if not is_viewing_company:
        if request.user.role == 'company_agent' and sale.recorded_by != request.user:
            messages.error(request, 'You do not have permission to view this receipt.')
            return redirect('kuku_biz:sale_list')

        if request.user.role not in ['super_admin', 'company_admin', 'company_manager']:
            if request.user.branch and sale.branch and sale.branch_id != request.user.branch_id:
                messages.error(request, 'You do not have permission to view receipts from other branches.')
                return redirect('kuku_biz:sale_list')

    items = EggSaleItem.objects.filter(sale=sale).order_by('id')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'sale': sale,
        'items': items,
        'page_title': f'Receipt {sale.receipt_number}',
        'page_subtitle': sale.customer.name if sale.customer else 'Walk-in',
        'auto_print': request.GET.get('print') == '1',
    }
    return render(request, 'kuku_biz/receipt.html', context)


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

    can_edit = request.user.role in [
        'super_admin', 'company_admin', 'company_manager', 'stock_controller'
    ] or is_viewing_company

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'Only company admins and stock controllers can set prices.')
            return redirect('kuku_biz:price_list')

        try:
            unit = request.POST.get('unit', 'tray')
            try:
                tray_size = int(request.POST.get('tray_size') or 0)
            except (TypeError, ValueError):
                tray_size = 0
            price = _to_decimal(request.POST.get('price'))
            effective_date = request.POST.get('effective_date') or timezone.now().date()
            notes = request.POST.get('notes', '').strip()
            image_file = request.FILES.get('image')

            if price <= 0:
                messages.error(request, 'Price must be greater than zero.')
                return redirect('kuku_biz:price_list')

            new_image_key = ''
            if image_file:
                try:
                    new_image_key = _upload_image(
                        image_file, 'kuku/prices', f"price_{company.id}"
                    )
                except ValueError as e:
                    messages.error(request, str(e))
                    return redirect('kuku_biz:price_list')
                except Exception as e:
                    messages.error(request, f'Image upload failed: {e}')
                    return redirect('kuku_biz:price_list')

            PriceHistory.objects.create(
                company=company,
                unit=unit,
                tray_size=tray_size,
                price=price,
                effective_date=effective_date,
                notes=notes,
                image=new_image_key,
            )
            messages.success(
                request,
                f'Price recorded: {dict(EGG_UNIT_CHOICES).get(unit, unit)} — KES {price}.'
            )
            return redirect('kuku_biz:price_list')
        except Exception as e:
            messages.error(request, f'Error saving price: {e}')

    # GET — latest per unit + tray size
    latest_prices = {}
    for code, label in EGG_UNIT_CHOICES:
        if code == 'tray':
            continue  # handled separately per tray size
        latest = (
            PriceHistory.objects
            .filter(company=company, unit=code)
            .order_by('-effective_date', '-created_at')
            .first()
        )
        latest_prices[f"{code}_0"] = {
            'unit': code,
            'tray_size': 0,
            'label': label,
            'price': latest.price if latest else None,
            'effective_date': latest.effective_date if latest else None,
            'image_url': latest.image_url if latest else None,
        }

    # Latest per tray size
    seen_sizes = set()
    for p in PriceHistory.objects.filter(company=company, unit='tray').order_by('-effective_date', '-created_at'):
        size = p.tray_size or 30
        if size in seen_sizes:
            continue
        seen_sizes.add(size)
        latest_prices[f"tray_{size}"] = {
            'unit': 'tray',
            'tray_size': size,
            'label': f"{size}-Egg Tray",
            'price': p.price,
            'effective_date': p.effective_date,
            'image_url': p.image_url,
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
        'tray_size_choices': TRAY_SIZE_CHOICES,
        'today': timezone.now().date(),
        'page_title': 'Egg Prices',
        'page_subtitle': 'Set and track egg prices per unit',
    }
    return render(request, 'kuku_biz/prices.html', context)


@login_required
@kuku_write_access
@require_POST
def price_delete(request, pk):
    """Delete a price entry."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    entry = get_object_or_404(PriceHistory, pk=pk, company=company)

    # Best-effort delete of Cloudinary image
    if entry.image:
        _destroy_cloudinary_asset(_extract_cloudinary_key(entry.image))

    label = entry.display_label
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
    """Create customer — supports AJAX modal + regular form POST."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method != 'POST':
        return redirect('kuku_biz:customer_list')

    is_modal = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.POST.get('_modal') == '1'
    )

    name = request.POST.get('name', '').strip()
    phone = request.POST.get('phone', '').strip()
    customer_type = request.POST.get('customer_type', 'individual')
    email = request.POST.get('email', '').strip()
    location = request.POST.get('location', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not name:
        if is_modal:
            return JsonResponse({'success': False, 'error': 'Customer name is required.'}, status=400)
        messages.error(request, 'Customer name is required.')
        return redirect('kuku_biz:customer_list')

    dup = Customer.objects.filter(company=company, name__iexact=name, phone=phone).first()
    if dup:
        if is_modal:
            return JsonResponse({
                'success': False,
                'error': 'A customer with this name and phone already exists.',
                'existing_id': dup.id,
            }, status=409)
        messages.warning(request, f'Customer "{name}" already exists.')
        return redirect('kuku_biz:customer_list')

    try:
        customer = Customer.objects.create(
            company=company,
            name=name,
            customer_type=customer_type,
            phone=phone,
            email=email,
            location=location,
            notes=notes,
            created_by=request.user,
        )
    except Exception as e:
        if is_modal:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error adding customer: {e}')
        return redirect('kuku_biz:customer_list')

    if is_modal:
        return JsonResponse({
            'success': True,
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'type': customer.get_customer_type_display(),
        })

    messages.success(request, 'Customer added successfully.')
    return redirect('kuku_biz:customer_list')

# ============================================================
# FEED TYPES (admin)
# ============================================================

@login_required
@kuku_write_access
def feed_type_list(request):
    """Manage the catalog of feed products for the company."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    feed_types = (
        FeedType.objects
        .filter(company=company)
        .order_by('name', 'brand')
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'feed_types': feed_types,
        'stage_choices': FeedType.STAGE_CHOICES,
        'page_title': 'Feed Types',
        'page_subtitle': f'{feed_types.count()} defined',
    }
    return render(request, 'kuku_biz/feed_types.html', context)


@login_required
@kuku_write_access
def feed_type_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'Feed name is required.')
                return redirect('kuku_biz:feed_type_list')

            brand = request.POST.get('brand', '').strip()
            existing = FeedType.objects.filter(
                company=company, name__iexact=name, brand__iexact=brand,
            ).first()
            if existing:
                messages.warning(request, f'"{name}" ({brand}) already exists.')
                return redirect('kuku_biz:feed_type_list')

            FeedType.objects.create(
                company=company,
                name=name,
                brand=brand,
                stage=request.POST.get('stage', 'other'),
                cost_per_kg=_to_decimal(request.POST.get('cost_per_kg')),
                protein_percent=(
                    _to_decimal(request.POST.get('protein_percent'))
                    if request.POST.get('protein_percent') else None
                ),
                default_unit=request.POST.get('default_unit', 'kg'),
                kg_per_bag=_to_decimal(request.POST.get('kg_per_bag')) or 50,
                is_active=request.POST.get('is_active') == 'on',
            )
            messages.success(request, f'Feed type "{name}" added.')
        except Exception as e:
            messages.error(request, f'Error adding feed type: {e}')

    return redirect('kuku_biz:feed_type_list')


@login_required
@kuku_write_access
def feed_type_edit(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    ft = get_object_or_404(FeedType, pk=pk, company=company)

    if request.method == 'POST':
        try:
            ft.name = request.POST.get('name', '').strip()
            ft.brand = request.POST.get('brand', '').strip()
            ft.stage = request.POST.get('stage', ft.stage)
            ft.cost_per_kg = _to_decimal(request.POST.get('cost_per_kg'))
            ft.default_unit = request.POST.get('default_unit', ft.default_unit)
            ft.kg_per_bag = _to_decimal(request.POST.get('kg_per_bag')) or 50
            ft.is_active = request.POST.get('is_active') == 'on'
            if request.POST.get('protein_percent'):
                ft.protein_percent = _to_decimal(request.POST.get('protein_percent'))
            ft.save()
            messages.success(request, f'Feed type "{ft.name}" updated.')
        except Exception as e:
            messages.error(request, f'Error updating feed type: {e}')

    return redirect('kuku_biz:feed_type_list')


@login_required
@kuku_write_access
@require_POST
def feed_type_delete(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    ft = get_object_or_404(FeedType, pk=pk, company=company)

    # Safety: don't delete if used anywhere — mark inactive instead
    used = FeedRecord.objects.filter(feed_type=ft).exists()
    if used:
        ft.is_active = False
        ft.save(update_fields=['is_active'])
        messages.warning(
            request,
            f'"{ft.name}" is used by existing records — marked inactive instead of deleting.'
        )
    else:
        ft.delete()
        messages.success(request, f'Feed type "{ft.name}" deleted.')

    return redirect('kuku_biz:feed_type_list')


# ============================================================
# FEED — MAIN HUB
# ============================================================

@login_required
def feed_list(request):
    """
    Feed hub — shows:
      - KPI cards (kg purchased, kg consumed, cost, stock on hand)
      - Feed inventory cards (per feed type: purchased, consumed, on hand)
      - Recent purchases + recent consumption logs
      - Per-flock feed summary (last 30 days)
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    today = timezone.now().date()
    month_ago = today - timedelta(days=30)
    week_ago = today - timedelta(days=7)

    # ── Base querysets ──
    records_qs = FeedRecord.objects.filter(company=company).select_related(
        'flock', 'feed_type', 'branch', 'inventory_item', 'recorded_by'
    )
    if selected_branch_id:
        records_qs = records_qs.filter(branch_id=selected_branch_id)

    purchases_qs   = records_qs.filter(record_type='purchase')
    consumption_qs = records_qs.filter(record_type='consumption')

    # ── KPIs (last 30 days) ──
    month_purchases   = purchases_qs.filter(date__gte=month_ago)
    month_consumption = consumption_qs.filter(date__gte=month_ago)

    month_feed_cost        = month_purchases.aggregate(t=Sum('cost'))['t'] or 0
    month_feed_kg_bought   = month_purchases.aggregate(t=Sum('quantity_kg'))['t'] or 0
    month_feed_kg_used     = month_consumption.aggregate(t=Sum('quantity_kg'))['t'] or 0

    month_cost_total  = month_purchases.aggregate(t=Sum('cost'))['t'] or 0
    month_cost_paid   = month_purchases.aggregate(t=Sum('amount_paid'))['t'] or 0
    month_feed_balance = month_cost_total - month_cost_paid

    week_feed_kg_used = (
        consumption_qs.filter(date__gte=week_ago)
        .aggregate(t=Sum('quantity_kg'))['t'] or 0
    )

    # ── Feed inventory on hand (from InventoryItem lines) ──
    feed_inventory_qs = (
        InventoryItem.objects
        .filter(company=company, item_type='feed_bag')
        .select_related('branch')
        .order_by('branch__name', 'name')
    )
    if selected_branch_id:
        feed_inventory_qs = feed_inventory_qs.filter(branch_id=selected_branch_id)

    total_feed_kg_on_hand = 0.0
    feed_stock_value = Decimal('0')
    low_feed_items = []
    for item in feed_inventory_qs:
        qty = _to_decimal(item.quantity)
        total_feed_kg_on_hand += float(qty)
        feed_stock_value += qty * _to_decimal(item.cost_per_unit)
        if item.needs_reorder:
            low_feed_items.append(item)

    # ── Feed inventory rows (per feed type, live stock) ──
    feed_inventory_rows = []
    all_feed_types = FeedType.objects.filter(company=company, is_active=True).order_by('name')

    for ft in all_feed_types:
        f_purch = purchases_qs.filter(feed_type=ft)
        f_cons  = consumption_qs.filter(feed_type=ft)

        purchased_kg   = f_purch.aggregate(t=Sum('quantity_kg'))['t'] or 0
        consumed_kg    = f_cons.aggregate(t=Sum('quantity_kg'))['t'] or 0
        purchased_cost = f_purch.aggregate(t=Sum('cost'))['t'] or 0

        # Prefer the actual InventoryItem quantity when available (single source of truth)
        inv_filter = InventoryItem.objects.filter(
            company=company, item_type='feed_bag',
        ).filter(name__icontains=ft.name)
        if ft.brand:
            inv_filter = inv_filter.filter(name__icontains=ft.brand)
        if selected_branch_id:
            inv_filter = inv_filter.filter(branch_id=selected_branch_id)

        inv_qty = sum(float(i.quantity) for i in inv_filter)

        # On-hand = whatever the inventory line says; fallback to purchases−consumption
        if inv_qty > 0:
            on_hand_kg = inv_qty
        else:
            on_hand_kg = max(purchased_kg - consumed_kg, 0)

        avg_cost = (purchased_cost / purchased_kg) if purchased_kg else (ft.cost_per_kg or 0)
        value = float(on_hand_kg) * float(avg_cost or 0)

        # Show only feed types with any activity, or that have stock
        if purchased_kg or consumed_kg or on_hand_kg:
            feed_inventory_rows.append({
                'feed_type': ft,
                'name': ft.name,
                'brand': ft.brand,
                'unit': ft.default_unit or 'kg',
                'purchased_kg': purchased_kg,
                'consumed_kg': consumed_kg,
                'on_hand_kg': on_hand_kg,
                'cost_per_kg': avg_cost,
                'value': value,
                'low': 0 < on_hand_kg <= 1,
                'empty': on_hand_kg <= 0,
            })

    feed_inventory_rows.sort(key=lambda r: (not r['low'], r['name']))

    # ── Recent activity ──
    recent_purchases   = purchases_qs.order_by('-date', '-created_at')[:15]
    recent_consumption = consumption_qs.order_by('-date', '-created_at')[:15]

    # ── Per-flock feed cost (last 30 days) ──
    flocks = Flock.objects.filter(company=company, status='active').select_related('branch')
    if selected_branch_id:
        flocks = flocks.filter(branch_id=selected_branch_id)

    flock_feed_summary = []
    for f in flocks:
        purchased_kg = (
            purchases_qs.filter(flock=f, date__gte=month_ago)
            .aggregate(t=Sum('quantity_kg'))['t'] or 0
        )
        purchased_cost = (
            purchases_qs.filter(flock=f, date__gte=month_ago)
            .aggregate(t=Sum('cost'))['t'] or 0
        )
        consumed_kg = (
            consumption_qs.filter(flock=f, date__gte=month_ago)
            .aggregate(t=Sum('quantity_kg'))['t'] or 0
        )
        flock_feed_summary.append({
            'flock': f,
            'purchased_kg': purchased_kg,
            'purchased_cost': purchased_cost,
            'consumed_kg': consumed_kg,
            'balance_kg': (purchased_kg or 0) - (consumed_kg or 0),
        })

    # ── Consumption log (straight from FeedRecord, filtered to consumption) ──
    consumption_log = consumption_qs.order_by('-date', '-created_at')[:50]

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        # KPIs
        'month_feed_cost': month_feed_cost,
        'month_feed_kg_bought': month_feed_kg_bought,
        'month_feed_kg_used': month_feed_kg_used,
        'month_feed_balance': month_feed_balance,
        'week_feed_kg_used': week_feed_kg_used,
        'total_feed_kg_on_hand': total_feed_kg_on_hand,
        'feed_stock_value': feed_stock_value,
        'low_feed_count': len(low_feed_items),

        # Feed inventory cards
        'feed_inventory_rows': feed_inventory_rows,

        # Logs
        'recent_purchases': recent_purchases,
        'recent_consumption': recent_consumption,
        'consumption_log': consumption_log,
        'flock_feed_summary': flock_feed_summary,

        # Form choices for modals
        'flocks': flocks.order_by('name'),
        'feed_types': all_feed_types,
        'today': today,

        'page_title': 'Feed',
        'page_subtitle': 'Purchases, consumption & stock',
    }
    return render(request, 'kuku_biz/feed.html', context)


# ============================================================
# FEED — CREATE (purchase OR consumption)
# ============================================================

@login_required
@kuku_write_access
def feed_create(request):
    """
    Record a feed purchase (stock in) OR a direct consumption entry.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method != 'POST':
        return redirect('kuku_biz:feed_list')

    try:
        record_type = request.POST.get('record_type', 'purchase')
        if record_type not in ('purchase', 'consumption'):
            record_type = 'purchase'

        branch = _resolve_branch(request, company)
        flock_id = request.POST.get('flock') or None
        feed_type_id = request.POST.get('feed_type') or None

        quantity_kg = _to_decimal(request.POST.get('quantity_kg'))
        if quantity_kg <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return redirect('kuku_biz:feed_list')

        cost = _to_decimal(request.POST.get('cost')) if record_type == 'purchase' else Decimal('0')
        amount_paid = _to_decimal(request.POST.get('amount_paid')) if record_type == 'purchase' else Decimal('0')

        # Auto-fill cost from feed_type.cost_per_kg if blank
        if record_type == 'purchase' and cost <= 0 and feed_type_id:
            ft = FeedType.objects.filter(id=feed_type_id, company=company).first()
            if ft and ft.cost_per_kg:
                cost = _to_decimal(ft.cost_per_kg) * quantity_kg

        record = FeedRecord.objects.create(
            company=company,
            branch=branch,
            flock_id=flock_id,
            feed_type_id=feed_type_id,
            record_type=record_type,
            date=request.POST.get('date') or timezone.now().date(),
            quantity_kg=quantity_kg,
            cost=cost,
            amount_paid=amount_paid,
            supplier=request.POST.get('supplier', '').strip(),
            supplier_invoice=request.POST.get('supplier_invoice', '').strip(),
            payment_status=request.POST.get('payment_status', 'paid') if record_type == 'purchase' else 'paid',
            notes=request.POST.get('notes', '').strip(),
            recorded_by=request.user,
        )

        if record_type == 'purchase':
            record.recompute_payment_status()

        verb = 'Purchase' if record_type == 'purchase' else 'Consumption'
        messages.success(
            request,
            f'{verb} recorded: {quantity_kg}kg'
            + (f' — KES {cost:,.0f}' if record_type == 'purchase' and cost else '')
            + '.'
        )

    except Exception as e:
        messages.error(request, f'Error recording feed: {e}')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
    if next_url:
        return redirect(next_url)
    return redirect('kuku_biz:feed_list')


# ============================================================
# FEED — CONSUMPTION (daily ration per flock)
# ============================================================

@login_required
@kuku_write_access
def feed_consume(request):
    """
    Record daily feed given to a flock.

    Creates a FeedConsumption row (which auto-creates the matching
    stock-out FeedRecord) AND directly creates a matching consumption
    FeedRecord so the feed_list log and inventory cards stay in sync
    even if FeedConsumption's auto-link fails.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method != 'POST':
        return redirect('kuku_biz:feed_list')

    try:
        flock_id = request.POST.get('flock')
        flock = get_object_or_404(Flock, pk=flock_id, company=company)

        feed_type_id = request.POST.get('feed_type') or None
        date = request.POST.get('date') or timezone.now().date()
        quantity_kg = _to_decimal(request.POST.get('quantity_kg'))

        if quantity_kg <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return redirect('kuku_biz:feed_list')

        # 1) Create/update the FeedConsumption record
        obj, created = FeedConsumption.objects.update_or_create(
            flock=flock,
            feed_type_id=feed_type_id,
            date=date,
            defaults={
                'company': company,
                'branch': flock.branch,
                'quantity_kg': quantity_kg,
                'notes': request.POST.get('notes', '').strip(),
                'recorded_by': request.user,
            },
        )

        # 2) If updating an existing one, sync the linked FeedRecord
        if not created and obj.feed_record_id:
            fr = obj.feed_record
            fr.quantity_kg = quantity_kg
            fr.date = date
            fr.feed_type_id = feed_type_id
            fr.save()

        action = 'recorded' if created else 'updated'
        messages.success(
            request,
            f'Feed consumption {action}: {quantity_kg}kg for {flock.name}.'
        )

    except Exception as e:
        messages.error(request, f'Error recording feed consumption: {e}')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
    if next_url:
        return redirect(next_url)
    return redirect('kuku_biz:feed_list')


# ============================================================
# FEED — EDIT
# ============================================================

@login_required
@kuku_write_access
def feed_edit(request, pk):
    """Edit an existing FeedRecord (purchase or consumption)."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(
        FeedRecord.objects.select_related('flock', 'feed_type', 'branch', 'inventory_item'),
        pk=pk, company=company,
    )

    if request.method == 'POST':
        try:
            old_signed_kg  = record.signed_quantity
            old_feed_type  = record.feed_type
            old_inventory  = record.inventory_item

            # Reverse the old inventory impact
            try:
                if old_inventory:
                    units = (
                        old_feed_type.kg_to_units(abs(old_signed_kg))
                        if old_feed_type else abs(old_signed_kg)
                    )
                    old_inventory.quantity = _to_decimal(old_inventory.quantity) - (
                        units if old_signed_kg > 0 else -units
                    )
                    if old_inventory.quantity < 0:
                        old_inventory.quantity = Decimal('0')
                    old_inventory.save(update_fields=['quantity'])
            except Exception:
                pass

            # ── Apply new values ──
            record.record_type = request.POST.get('record_type', record.record_type)
            record.flock_id = request.POST.get('flock') or None
            record.feed_type_id = request.POST.get('feed_type') or None
            record.date = request.POST.get('date') or record.date
            record.quantity_kg = _to_decimal(request.POST.get('quantity_kg'))

            if record.record_type == 'purchase':
                record.cost = _to_decimal(request.POST.get('cost'))
                record.amount_paid = _to_decimal(request.POST.get('amount_paid'))
                record.supplier = request.POST.get('supplier', '').strip()
                record.supplier_invoice = request.POST.get('supplier_invoice', '').strip()
                record.payment_status = request.POST.get('payment_status', 'paid')
            else:
                record.cost = Decimal('0')
                record.amount_paid = Decimal('0')
                record.payment_status = 'paid'

            record.notes = request.POST.get('notes', '').strip()

            # Re-resolve branch if flock changed
            if record.flock_id and not record.branch_id:
                record.branch = getattr(record.flock, 'branch', None)

            # Reset inventory linkage so save() picks it up fresh
            record.inventory_item = None

            # Bypass the "new record" inventory hook — we already reversed
            super(FeedRecord, record).save()

            # Apply the new inventory impact
            record._apply_inventory_delta(sign=1)

            if record.record_type == 'purchase':
                record.recompute_payment_status()

            messages.success(request, f'Feed record #{record.pk} updated.')
            return redirect('kuku_biz:feed_list')

        except Exception as e:
            messages.error(request, f'Error updating feed record: {e}')

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'record': record,
        'flocks': Flock.objects.filter(company=company, status='active').order_by('name'),
        'feed_types': FeedType.objects.filter(company=company, is_active=True).order_by('name'),
        'branches': Branch.objects.filter(company=company, is_active=True).order_by('name'),
        'today': timezone.now().date(),
        'page_title': f'Edit Feed Record #{record.pk}',
    }
    return render(request, 'kuku_biz/feed_form.html', context)


# ============================================================
# FEED — DELETE
# ============================================================

@login_required
@kuku_write_access
@require_POST
def feed_delete(request, pk):
    """
    Delete a FeedRecord. Reverses its inventory impact first.
    If it came from a FeedConsumption, delete that too.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(FeedRecord, pk=pk, company=company)
    label = (
        f"{record.quantity_kg}kg — "
        f"{record.flock.name if record.flock else 'General'} — "
        f"{record.date}"
    )

    consumption = getattr(record, 'consumption_source', None)
    if consumption:
        consumption.delete()
    else:
        record.delete()

    messages.success(request, f'Feed record deleted ({label}).')
    return redirect('kuku_biz:feed_list')


@login_required
@kuku_write_access
@require_POST
def feed_mark_paid(request, pk):
    """Mark a feed purchase as fully paid."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(
        FeedRecord, pk=pk, company=company, record_type='purchase'
    )

    record.amount_paid = record.cost
    record.payment_status = 'paid'
    record.save(update_fields=['amount_paid', 'payment_status'])

    messages.success(request, f'Feed purchase #{record.pk} marked as fully paid.')
    return redirect('kuku_biz:feed_list')


# ============================================================
# FEED CONSUMPTION — DEDICATED PAGE
# ============================================================

@login_required
def feed_consumption_list(request):
    """
    Dedicated feed consumption log page.

    Columns: Date | Flock | Feed Type | Quantity (kg) | Feed Value (KES)
    Footer:  Grand totals (kg + KES)
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    # ── Date filters ──
    today = timezone.now().date()
    try:
        period_days = int(request.GET.get('period', 30))
    except (ValueError, TypeError):
        period_days = 30
    period_days = max(0, min(period_days, 3650))
    start_date = today - timedelta(days=period_days) if period_days else None

    # ── Base queryset ──
    qs = (
        FeedConsumption.objects
        .filter(company=company)
        .select_related('flock', 'feed_type', 'branch', 'recorded_by')
    )
    if selected_branch_id:
        qs = qs.filter(branch_id=selected_branch_id)
    if start_date:
        qs = qs.filter(date__gte=start_date)

    # Optional flock filter
    flock_id = request.GET.get('flock', '').strip()
    if flock_id:
        qs = qs.filter(flock_id=flock_id)

    # Optional feed type filter
    feed_type_id = request.GET.get('feed_type', '').strip()
    if feed_type_id:
        qs = qs.filter(feed_type_id=feed_type_id)

    rows = qs.order_by('-date', '-created_at')

    # ── Build rows with computed value ──
    records = []
    total_kg = Decimal('0')
    total_value = Decimal('0')

    for c in rows:
        kg = _to_decimal(c.quantity_kg)
        # Prefer the feed type's price; fall back to its linked FeedRecord cost/kg
        rate = Decimal('0')
        if c.feed_type and c.feed_type.cost_per_kg:
            rate = _to_decimal(c.feed_type.cost_per_kg)
        elif c.feed_record_id and c.feed_record.cost_per_kg:
            rate = _to_decimal(c.feed_record.cost_per_kg)

        value = kg * rate
        total_kg += kg
        total_value += value

        records.append({
            'obj': c,
            'date': c.date,
            'flock': c.flock,
            'feed_type': c.feed_type,
            'quantity_kg': kg,
            'rate': rate,
            'value': value,
            'branch': c.branch,
        })

    # ── Context ──
    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        'records': records,
        'total_kg': total_kg,
        'total_value': total_value,
        'record_count': len(records),

        # Filter form values
        'period_days': period_days,
        'selected_flock_id': flock_id,
        'selected_feed_type_id': feed_type_id,
        'flocks': Flock.objects.filter(company=company).order_by('name'),
        'feed_types': FeedType.objects.filter(company=company, is_active=True).order_by('name'),
        'today': today,
        'start_date': start_date,

        'page_title': 'Feed Consumption',
        'page_subtitle': f'{len(records)} record{"s" if len(records) != 1 else ""}',
    }
    return render(request, 'kuku_biz/feed_consumption.html', context)
    

@login_required
@kuku_write_access
@require_POST
def feed_consumption_delete(request, pk):
    """Delete a FeedConsumption (and its linked stock-out FeedRecord)."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    obj = get_object_or_404(FeedConsumption, pk=pk, company=company)
    label = f"{obj.quantity_kg}kg — {obj.flock.name} — {obj.date}"

    if obj.feed_record_id:
        obj.feed_record.delete()
    obj.delete()

    messages.success(request, f'Feed consumption deleted ({label}).')
    return redirect('kuku_biz:feed_list')
    

# ============================================================
# MORTALITY
# ============================================================

@login_required
def mortality_list(request):
    """
    Mortality log with cost/loss tracking and cause breakdown.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    today = timezone.now().date()

    # ── Filters ──
    flock_id = request.GET.get('flock', '').strip()
    cause = request.GET.get('cause', '').strip()
    try:
        period_days = int(request.GET.get('period', 30))
    except (ValueError, TypeError):
        period_days = 30
    period_days = max(0, min(period_days, 3650))
    start_date = today - timedelta(days=period_days) if period_days else None

    # ── Base queryset ──
    qs = (
        Mortality.objects
        .filter(company=company)
        .select_related('flock', 'branch', 'related_health_record')
    )
    if flock_id:
        qs = qs.filter(flock_id=flock_id)
    if cause:
        qs = qs.filter(cause=cause)
    if start_date:
        qs = qs.filter(date__gte=start_date)

    records = qs.order_by('-date', '-created_at')[:200]

    # ── Aggregates (respect filters) ──
    agg = qs.aggregate(
        total_deaths=Sum('count'),
        total_loss=Sum('estimated_loss'),
        total_records=Count('id'),
    )
    month_total = agg['total_deaths'] or 0
    total_loss_value = agg['total_loss'] or 0
    total_records = agg['total_records'] or 0

    avg_loss_per_bird = (
        round(float(total_loss_value) / float(month_total), 2)
        if month_total else 0
    )

    # ── Flock-wide mortality rate (all-time, all flocks) ──
    all_flocks = Flock.objects.filter(company=company)
    total_initial_birds = (
        all_flocks.aggregate(t=Sum('initial_count'))['t'] or 0
    )
    total_birds_lost = (
        Mortality.objects.filter(company=company)
        .aggregate(t=Sum('count'))['t'] or 0
    )
    mortality_rate = (
        round((total_birds_lost / total_initial_birds) * 100, 2)
        if total_initial_birds else 0
    )

    # ── Cause breakdown for the bar chart ──
    cause_counts = (
        qs.values('cause')
        .annotate(total=Sum('count'))
        .order_by('-total')
    )

    cause_colors = {
        'disease':  'linear-gradient(90deg, #ef4444 0%, #dc2626 100%)',
        'predator': 'linear-gradient(90deg, #f59e0b 0%, #d97706 100%)',
        'culled':   'linear-gradient(90deg, #3b82f6 0%, #1d4ed8 100%)',
        'accident': 'linear-gradient(90deg, #ec4899 0%, #be185d 100%)',
        'unknown':  'linear-gradient(90deg, #9ca3af 0%, #6b7280 100%)',
    }
    cause_labels = dict(MORTALITY_CAUSE_CHOICES)

    cause_breakdown = []
    for row in cause_counts:
        code = row['cause']
        count = row['total'] or 0
        percent = round((count / month_total) * 100, 1) if month_total else 0
        cause_breakdown.append({
            'code': code,
            'label': cause_labels.get(code, code.title()),
            'count': count,
            'percent': percent,
            'color': cause_colors.get(code, 'linear-gradient(90deg,#9ca3af,#6b7280)'),
        })

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'records': records,
        'flocks': Flock.objects.filter(company=company, status='active').order_by('name'),
        'today': today,

        # Filters
        'selected_flock_id': flock_id,
        'selected_cause': cause,
        'period_days': period_days,

        # KPIs
        'month_total': month_total,
        'total_loss_value': total_loss_value,
        'avg_loss_per_bird': avg_loss_per_bird,
        'mortality_rate': mortality_rate,
        'total_birds_lost': total_birds_lost,
        'total_initial_birds': total_initial_birds,
        'total_records': total_records,

        # Breakdown
        'cause_breakdown': cause_breakdown,

        'page_title': 'Mortality',
        'page_subtitle': 'Deaths, culling & loss tracking',
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
            branch = _resolve_branch(request, company)
            Mortality.objects.create(
                company=company,
                branch=branch,
                flock_id=request.POST.get('flock'),
                date=request.POST.get('date') or timezone.now().date(),
                count=int(request.POST.get('count') or 0),
                cause=request.POST.get('cause', 'unknown'),
                age_group=request.POST.get('age_group', 'unknown'),
                symptoms=request.POST.get('symptoms', '').strip(),
                disposal_method=request.POST.get('disposal_method', 'none'),
                action_taken=request.POST.get('action_taken', '').strip(),
                estimated_loss=_to_decimal(request.POST.get('estimated_loss')),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )
            messages.success(request, 'Mortality recorded. Flock count updated.')
        except Exception as e:
            messages.error(request, f'Error recording mortality: {e}')

    # Return to wherever the user came from
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
    if next_url:
        return redirect(next_url)
    return redirect('kuku_biz:mortality_list')


@login_required
@kuku_write_access
@require_POST
def mortality_delete(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(Mortality, pk=pk, company=company)
    label = f"{record.count} bird{'s' if record.count != 1 else ''} — {record.flock.name} — {record.date}"
    record.delete()
    messages.success(request, f'Mortality record deleted ({label}). Flock count recalculated.')
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

    records_qs = (
        HealthRecord.objects
        .filter(company=company)
        .select_related('flock', 'branch', 'vaccine_type', 'inventory_item')
        .order_by('-date', '-created_at')
    )

    purchases_qs = records_qs.filter(record_type='purchase')
    admin_qs     = records_qs.filter(record_type='administration')

    month_cost = (
        purchases_qs.filter(date__gte=month_ago)
        .aggregate(t=Sum('cost'))['t'] or 0
    )
    month_paid = (
        purchases_qs.filter(date__gte=month_ago)
        .aggregate(t=Sum('amount_paid'))['t'] or 0
    )
    month_balance = month_cost - month_paid

    month_admin_count = admin_qs.filter(date__gte=month_ago).count()
    month_birds_treated = (
        admin_qs.filter(date__gte=month_ago)
        .aggregate(t=Sum('birds_treated'))['t'] or 0
    )

    upcoming = (
        admin_qs.filter(next_due_date__gte=today)
        .select_related('flock', 'vaccine_type')
        .order_by('next_due_date')[:10]
    )

    # Live inventory rows per vaccine type
    health_inventory_rows = []
    all_vts = VaccineType.objects.filter(company=company, is_active=True).order_by('name')
    for vt in all_vts:
        f_purch = purchases_qs.filter(vaccine_type=vt)
        f_admin = admin_qs.filter(vaccine_type=vt)

        purchased_qty = f_purch.aggregate(t=Sum('quantity'))['t'] or 0
        admin_qty     = f_admin.aggregate(t=Sum('quantity'))['t'] or 0

        inv_filter = InventoryItem.objects.filter(
            company=company, item_type='medicine',
            name__icontains=vt.name,
        )
        if vt.brand:
            inv_filter = inv_filter.filter(name__icontains=vt.brand)

        inv_qty = sum(float(i.quantity) for i in inv_filter)
        on_hand = inv_qty if inv_qty > 0 else max(purchased_qty - admin_qty, 0)

        health_inventory_rows.append({
            'vaccine_type': vt,
            'name': vt.name,
            'brand': vt.brand,
            'target_disease': vt.target_disease,
            'unit': vt.default_unit or 'dose',
            'purchased_qty': purchased_qty,
            'admin_qty': admin_qty,
            'on_hand': on_hand,
            'low': 0 < on_hand <= 10,
            'empty': on_hand <= 0,
        })

    records_purchases = purchases_qs[:15]
    records_admins    = admin_qs[:15]

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'records_purchases': records_purchases,
        'records_admins': records_admins,
        'flocks': Flock.objects.filter(company=company, status='active').order_by('name'),
        'vaccine_types': all_vts,
        'health_inventory_rows': health_inventory_rows,
        'month_cost': month_cost,
        'month_balance': month_balance,
        'month_admin_count': month_admin_count,
        'month_birds_treated': month_birds_treated,
        'upcoming': upcoming,
        'today': today,
        'page_title': 'Health',
        'page_subtitle': 'Vaccine purchases, administration & stock',
    }
    return render(request, 'kuku_biz/health.html', context)


@login_required
@kuku_write_access
def health_create(request):
    """
    Handles both purchase and administration records.
    Field `record_type` in POST decides which.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method != 'POST':
        return redirect('kuku_biz:health_list')

    try:
        record_type = request.POST.get('record_type', 'administration')
        branch = _resolve_branch(request, company)
        flock_id = request.POST.get('flock') or None
        vaccine_type_id = request.POST.get('vaccine_type') or None

        quantity = _to_decimal(request.POST.get('quantity'))
        if quantity <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return redirect('kuku_biz:health_list')

        if record_type == 'purchase':
            cost = _to_decimal(request.POST.get('cost'))
            amount_paid = _to_decimal(request.POST.get('amount_paid'))

            # Auto-fill cost from vaccine_type.cost_per_unit if blank
            if cost <= 0 and vaccine_type_id:
                vt = VaccineType.objects.filter(id=vaccine_type_id, company=company).first()
                if vt and vt.cost_per_unit:
                    cost = _to_decimal(vt.cost_per_unit) * quantity

            record = HealthRecord.objects.create(
                company=company,
                branch=branch,
                flock_id=None,   # purchases are general stock
                vaccine_type_id=vaccine_type_id,
                product_used=request.POST.get('product_used', '').strip(),
                record_type='purchase',
                date=request.POST.get('date') or timezone.now().date(),
                quantity=quantity,
                unit=request.POST.get('unit', 'dose'),
                cost=cost,
                amount_paid=amount_paid,
                supplier=request.POST.get('supplier', '').strip(),
                supplier_invoice=request.POST.get('supplier_invoice', '').strip(),
                payment_status=request.POST.get('payment_status', 'paid'),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )
            record.recompute_payment_status()
            messages.success(
                request,
                f'Health purchase recorded: {quantity} {record.unit} for KES {cost:,.0f}.'
            )

        else:  # administration
            record = HealthRecord.objects.create(
                company=company,
                branch=branch,
                flock_id=flock_id,
                vaccine_type_id=vaccine_type_id,
                product_used=request.POST.get('product_used', '').strip(),
                record_type='administration',
                date=request.POST.get('date') or timezone.now().date(),
                quantity=quantity,
                unit=request.POST.get('unit', 'dose'),
                birds_treated=int(request.POST.get('birds_treated') or 0),
                admin_method=request.POST.get('admin_method', 'drinking_water'),
                administered_by=request.POST.get('administered_by', '').strip(),
                next_due_date=request.POST.get('next_due_date') or None,
                description=request.POST.get('description', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                recorded_by=request.user,
            )
            messages.success(
                request,
                f'Administration recorded: {quantity} {record.unit} to {record.birds_treated} birds.'
            )

    except Exception as e:
        messages.error(request, f'Error recording health event: {e}')

    return redirect('kuku_biz:health_list')


@login_required
@kuku_write_access
@require_POST
def health_delete(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    record = get_object_or_404(HealthRecord, pk=pk, company=company)
    label = (
        f"{record.vaccine_type.name if record.vaccine_type else (record.product_used or 'Record')} "
        f"— {record.date}"
    )
    record.delete()
    messages.success(request, f'Health record deleted ({label}).')
    return redirect('kuku_biz:health_list')

# ============================================================
# VACCINE / DRUG TYPES (catalog — admin)
# ============================================================

@login_required
@kuku_write_access
def vaccine_type_list(request):
    """Manage the catalog of vaccine / drug products for the company."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    vaccine_types = (
        VaccineType.objects
        .filter(company=company)
        .order_by('name', 'brand')
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'vaccine_types': vaccine_types,
        'kind_choices': HEALTH_ITEM_KIND_CHOICES,
        'page_title': 'Vaccine Types',
        'page_subtitle': f'{vaccine_types.count()} defined',
    }
    return render(request, 'kuku_biz/vaccine_types.html', context)


@login_required
@kuku_write_access
def vaccine_type_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'Name is required.')
                return redirect('kuku_biz:vaccine_type_list')

            brand = request.POST.get('brand', '').strip()
            existing = VaccineType.objects.filter(
                company=company, name__iexact=name, brand__iexact=brand,
            ).first()
            if existing:
                messages.warning(request, f'"{name}" ({brand}) already exists.')
                return redirect('kuku_biz:vaccine_type_list')

            VaccineType.objects.create(
                company=company,
                name=name,
                brand=brand,
                item_kind=request.POST.get('item_kind', 'vaccine'),
                target_disease=request.POST.get('target_disease', '').strip(),
                default_unit=request.POST.get('default_unit', 'dose'),
                cost_per_unit=_to_decimal(request.POST.get('cost_per_unit')),
                repeat_interval_days=int(request.POST.get('repeat_interval_days') or 0),
                storage_notes=request.POST.get('storage_notes', '').strip(),
                is_active=request.POST.get('is_active') == 'on',
            )
            messages.success(request, f'"{name}" added.')
        except Exception as e:
            messages.error(request, f'Error adding vaccine type: {e}')

    return redirect('kuku_biz:vaccine_type_list')


@login_required
@kuku_write_access
def vaccine_type_edit(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    vt = get_object_or_404(VaccineType, pk=pk, company=company)

    if request.method == 'POST':
        try:
            vt.name = request.POST.get('name', '').strip()
            vt.brand = request.POST.get('brand', '').strip()
            vt.item_kind = request.POST.get('item_kind', vt.item_kind)
            vt.target_disease = request.POST.get('target_disease', '').strip()
            vt.default_unit = request.POST.get('default_unit', vt.default_unit)
            vt.cost_per_unit = _to_decimal(request.POST.get('cost_per_unit'))
            vt.repeat_interval_days = int(request.POST.get('repeat_interval_days') or 0)
            vt.storage_notes = request.POST.get('storage_notes', '').strip()
            vt.is_active = request.POST.get('is_active') == 'on'
            vt.save()
            messages.success(request, f'"{vt.name}" updated.')
        except Exception as e:
            messages.error(request, f'Error updating vaccine type: {e}')

    return redirect('kuku_biz:vaccine_type_list')


@login_required
@kuku_write_access
@require_POST
def vaccine_type_delete(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    vt = get_object_or_404(VaccineType, pk=pk, company=company)

    used = HealthRecord.objects.filter(vaccine_type=vt).exists()
    if used:
        vt.is_active = False
        vt.save(update_fields=['is_active'])
        messages.warning(
            request,
            f'"{vt.name}" is used by existing records — marked inactive instead of deleting.'
        )
    else:
        vt.delete()
        messages.success(request, f'"{vt.name}" deleted.')

    return redirect('kuku_biz:vaccine_type_list')

@login_required
def vaccine_inventory(request):
    """
    Vaccine/drug inventory — sourced from InventoryItem lines
    (item_type='medicine') that were auto-created by HealthRecord
    purchases and administrations.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    items = (
        InventoryItem.objects
        .filter(company=company, item_type='medicine')
        .select_related('branch')
        .order_by('branch__name', 'name')
    )
    if selected_branch_id:
        items = items.filter(branch_id=selected_branch_id)

    low_stock = items.filter(quantity__lte=F('reorder_level'))

    total_units = sum(float(i.quantity) for i in items)
    total_value = sum(i.stock_value for i in items)

    # Match each inventory line to its VaccineType for the "Give" quick action
    vaccine_rows = []
    for item in items:
        base = item.name.split('(')[0].strip()
        vt = VaccineType.objects.filter(
            company=company, name__iexact=base
        ).first()
        vaccine_rows.append({
            'item': item,
            'vaccine_type': vt,
            'units': float(item.quantity),
            'value': item.stock_value,
            'low': item.quantity <= item.reorder_level,
        })

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'items': items,
        'vaccine_rows': vaccine_rows,
        'low_stock': low_stock,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,
        'total_units': total_units,
        'total_value': total_value,
        'today': timezone.now().date(),
        'page_title': 'Vaccine Inventory',
        'page_subtitle': f'{items.count()} item{"s" if items.count() != 1 else ""}',
    }
    return render(request, 'kuku_biz/vaccine_inventory.html', context)

# ============================================================
# EXPENSES
# ============================================================

@login_required
def expense_list(request):
    """
    Expenses hub — KPIs, category breakdown, filtered log with totals.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    today = timezone.now().date()
    try:
        period_days = int(request.GET.get('period', 30))
    except (ValueError, TypeError):
        period_days = 30
    period_days = max(0, min(period_days, 3650))
    start_date = today - timedelta(days=period_days) if period_days else None

    # ── Filters ──
    category = request.GET.get('category', '').strip()
    flock_id = request.GET.get('flock', '').strip()

    qs = (
        Expense.objects
        .filter(company=company)
        .select_related('flock', 'branch')
    )
    if selected_branch_id:
        qs = qs.filter(branch_id=selected_branch_id)
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if category:
        qs = qs.filter(category=category)
    if flock_id:
        qs = qs.filter(flock_id=flock_id)

    records = qs.order_by('-date', '-created_at')[:200]

    # ── KPIs ──
    agg = qs.aggregate(
        total=Sum('amount'),
        paid=Sum('amount_paid'),
        count=Count('id'),
    )
    total_amount = agg['total'] or 0
    total_paid   = agg['paid'] or 0
    total_balance = _to_decimal(total_amount) - _to_decimal(total_paid)
    record_count = agg['count'] or 0

    # ── Category breakdown ──
    cat_counts = (
        qs.values('category')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    cat_labels = dict(EXPENSE_CATEGORY_CHOICES)

    category_breakdown = []
    for row in cat_counts:
        code = row['category']
        total = row['total'] or 0
        percent = round((float(total) / float(total_amount)) * 100, 1) if total_amount else 0
        category_breakdown.append({
            'code': code,
            'label': cat_labels.get(code, code.title()),
            'total': total,
            'count': row['count'],
            'percent': percent,
        })

    # ── Per-flock summary (last 30d) ──
    month_ago = today - timedelta(days=30)
    flock_summary = []
    flocks = Flock.objects.filter(company=company, status='active')
    if selected_branch_id:
        flocks = flocks.filter(branch_id=selected_branch_id)

    for f in flocks:
        f_total = (
            Expense.objects
            .filter(company=company, flock=f, date__gte=month_ago)
            .aggregate(t=Sum('amount'))['t'] or 0
        )
        if f_total:
            flock_summary.append({'flock': f, 'total': f_total})

    flock_summary.sort(key=lambda x: -float(x['total']))

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        'records': records,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'record_count': record_count,
        'category_breakdown': category_breakdown,
        'flock_summary': flock_summary,

        'flocks': Flock.objects.filter(company=company, status='active').order_by('name'),
        'categories': EXPENSE_CATEGORY_CHOICES,
        'payment_methods': EXPENSE_PAYMENT_METHOD_CHOICES,

        'selected_category': category,
        'selected_flock_id': flock_id,
        'period_days': period_days,
        'today': today,

        'page_title': 'Expenses',
        'page_subtitle': 'Track farm costs and payments',
    }
    return render(request, 'kuku_biz/expenses.html', context)


@login_required
@kuku_write_access
def expense_create(request):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    if request.method != 'POST':
        return redirect('kuku_biz:expense_list')

    try:
        branch = _resolve_branch(request, company)

        amount = _to_decimal(request.POST.get('amount'))
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('kuku_biz:expense_list')

        Expense.objects.create(
            company=company,
            branch=branch,
            flock_id=request.POST.get('flock') or None,
            date=request.POST.get('date') or timezone.now().date(),
            category=request.POST.get('category', 'other'),
            description=request.POST.get('description', '').strip(),
            amount=amount,
            amount_paid=_to_decimal(request.POST.get('amount_paid')),
            paid_to=request.POST.get('paid_to', '').strip(),
            payment_method=request.POST.get('payment_method', 'cash'),
            reference=request.POST.get('reference', '').strip(),
            notes=request.POST.get('notes', '').strip(),
            recorded_by=request.user,
        )
        messages.success(request, f'Expense recorded: KES {amount:,.0f}.')
    except Exception as e:
        messages.error(request, f'Error recording expense: {e}')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
    if next_url:
        return redirect(next_url)
    return redirect('kuku_biz:expense_list')


@login_required
@kuku_write_access
def expense_edit(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    expense = get_object_or_404(Expense, pk=pk, company=company)

    if request.method != 'POST':
        return redirect('kuku_biz:expense_list')

    try:
        branch = _resolve_branch(request, company)

        expense.branch = branch
        expense.flock_id = request.POST.get('flock') or None
        expense.date = request.POST.get('date') or expense.date
        expense.category = request.POST.get('category', expense.category)
        expense.description = request.POST.get('description', '').strip()
        expense.amount = _to_decimal(request.POST.get('amount'))
        expense.amount_paid = _to_decimal(request.POST.get('amount_paid'))
        expense.paid_to = request.POST.get('paid_to', '').strip()
        expense.payment_method = request.POST.get('payment_method', expense.payment_method)
        expense.reference = request.POST.get('reference', '').strip()
        expense.notes = request.POST.get('notes', '').strip()
        expense.save()

        messages.success(request, 'Expense updated.')
    except Exception as e:
        messages.error(request, f'Error updating expense: {e}')

    return redirect('kuku_biz:expense_list')


@login_required
@kuku_write_access
@require_POST
def expense_delete(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    expense = get_object_or_404(Expense, pk=pk, company=company)
    label = f"{expense.get_category_display()} — KES {expense.amount}"
    expense.delete()
    messages.success(request, f'Expense deleted ({label}).')
    return redirect('kuku_biz:expense_list')


@login_required
@kuku_write_access
@require_POST
def expense_mark_paid(request, pk):
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    expense = get_object_or_404(Expense, pk=pk, company=company)
    expense.amount_paid = expense.amount
    expense.save(update_fields=['amount_paid', 'payment_status'])
    messages.success(request, f'Expense marked as paid (KES {expense.amount:,.0f}).')
    return redirect('kuku_biz:expense_list')

# ============================================================
# INVENTORY
# ============================================================

@login_required
def inventory_hub(request):
    """
    Inventory landing page — shows four cards linking to:
      - Egg Inventory (trays & crates)
      - Feed Inventory (bags)
      - Vaccine Inventory (medicine lines)
      - Other Supplies (equipment, misc)
    with summary KPIs for each.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    # ── Shared helper: filter a queryset by selected branch ──
    def _scope(qs):
        if selected_branch_id:
            return qs.filter(branch_id=selected_branch_id)
        return qs

    # ============================================================
    # EGG INVENTORY (trays + crates)
    # ============================================================
    egg_qs = _scope(
        InventoryItem.objects.filter(
            company=company,
            item_type__in=['egg_tray', 'egg_crate'],
        )
    )

    egg_item_count = egg_qs.count()
    egg_total_eggs = sum(item.total_eggs for item in egg_qs)
    egg_value = sum(item.stock_value for item in egg_qs)
    egg_low = egg_qs.filter(quantity__lte=F('reorder_level')).count()

    # ============================================================
    # FEED INVENTORY (bags)
    # ============================================================
    feed_qs = _scope(
        InventoryItem.objects.filter(
            company=company, item_type='feed_bag',
        )
    )

    feed_item_count = feed_qs.count()
    feed_total_kg = sum(float(item.quantity) for item in feed_qs)
    feed_value = sum(item.stock_value for item in feed_qs)
    feed_low = feed_qs.filter(quantity__lte=F('reorder_level')).count()

    # ============================================================
    # VACCINE INVENTORY (medicine)
    # ============================================================
    vaccine_qs = _scope(
        InventoryItem.objects.filter(
            company=company, item_type='medicine',
        )
    )

    vaccine_item_count = vaccine_qs.count()
    vaccine_total_units = sum(float(item.quantity) for item in vaccine_qs)
    vaccine_value = sum(item.stock_value for item in vaccine_qs)
    vaccine_low = vaccine_qs.filter(quantity__lte=F('reorder_level')).count()

    # ============================================================
    # OTHER SUPPLIES (equipment, misc — everything else)
    # ============================================================
    other_qs = _scope(
        InventoryItem.objects
        .filter(company=company)
        .exclude(item_type__in=[
            'egg_tray', 'egg_crate',
            'feed_bag',
            'medicine',
        ])
    )
    other_count = other_qs.count()
    other_value = sum(item.stock_value for item in other_qs)

    # ============================================================
    # CONTEXT
    # ============================================================
    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        # Egg summary
        'egg_item_count': egg_item_count,
        'egg_total_eggs': egg_total_eggs,
        'egg_value': egg_value,
        'egg_low': egg_low,

        # Feed summary
        'feed_item_count': feed_item_count,
        'feed_total_kg': feed_total_kg,
        'feed_value': feed_value,
        'feed_low': feed_low,

        # Vaccine summary
        'vaccine_item_count': vaccine_item_count,
        'vaccine_total_units': vaccine_total_units,
        'vaccine_value': vaccine_value,
        'vaccine_low': vaccine_low,

        # Other supplies
        'other_count': other_count,
        'other_value': other_value,

        'page_title': 'Inventory',
        'page_subtitle': 'Eggs, feed, vaccines and supplies',
    }
    return render(request, 'kuku_biz/inventory_hub.html', context)

@login_required
def inventory_list(request):
    """
    Full inventory list — all item types in one page.
    This is the canonical 'all inventory' view used by create/edit/delete flows.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    items = (
        InventoryItem.objects
        .filter(company=company)
        .select_related('branch')
        .order_by('branch__name', 'item_type', 'name')
    )
    if selected_branch_id:
        items = items.filter(branch_id=selected_branch_id)

    # Optional type filter
    item_type = request.GET.get('type', '').strip()
    if item_type:
        items = items.filter(item_type=item_type)

    low_stock = items.filter(quantity__lte=F('reorder_level'))

    total_value = sum(
        float(i.quantity) * float(i.cost_per_unit)
        for i in items
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'items': items,
        'low_stock': low_stock,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,
        'total_value': total_value,
        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
        'selected_item_type': item_type,
        'today': timezone.now().date(),
        'page_title': 'Inventory',
        'page_subtitle': f'{items.count()} item{"s" if items.count() != 1 else ""}',
    }
    return render(request, 'kuku_biz/inventory.html', context)


# ============================================================
# INVENTORY — EGGS ONLY
# ============================================================

@login_required
def egg_inventory(request):
    """
    Egg inventory — trays & crates only.

    Columns: Item | Type | Tray Size | Quantity | Eggs Total | Branch | Value
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    items = (
        InventoryItem.objects
        .filter(
            company=company,
            item_type__in=['egg_tray', 'egg_crate'],
        )
        .select_related('branch')
        .order_by('branch__name', '-tray_size', 'name')
    )
    if selected_branch_id:
        items = items.filter(branch_id=selected_branch_id)

    low_stock = items.filter(quantity__lte=F('reorder_level'))

    # Totals
    total_trays = sum(float(i.quantity) for i in items)
    total_eggs = sum(i.total_eggs for i in items)
    total_value = sum(
        float(i.quantity) * float(i.cost_per_unit)
        for i in items
    )

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'items': items,
        'low_stock': low_stock,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        'total_trays': total_trays,
        'total_eggs': total_eggs,
        'total_value': total_value,

        'today': timezone.now().date(),
        'page_title': 'Egg Inventory',
        'page_subtitle': f'{items.count()} item{"s" if items.count() != 1 else ""}',
    }
    return render(request, 'kuku_biz/egg_inventory.html', context)


# ============================================================
# INVENTORY — FEED ONLY
# ============================================================

@login_required
def feed_inventory(request):
    """
    Feed inventory — bags only, sourced from InventoryItem lines
    that were auto-created by FeedRecord purchases/consumption.
    """
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    items = (
        InventoryItem.objects
        .filter(company=company, item_type='feed_bag')
        .select_related('branch')
        .order_by('branch__name', 'name')
    )
    if selected_branch_id:
        items = items.filter(branch_id=selected_branch_id)

    low_stock = items.filter(quantity__lte=F('reorder_level'))

    # Totals
    total_kg = sum(float(i.quantity) for i in items)
    total_value = sum(
        float(i.quantity) * float(i.cost_per_unit)
        for i in items
    )

    # Match each inventory line to its FeedType (for brand display + buy button)
    feed_rows = []
    for item in items:
        # Match by name like "Chick Mash" or "Chick Mash (Pembe)"
        base = item.name.split('(')[0].strip()
        ft = FeedType.objects.filter(
            company=company, name__iexact=base
        ).first()
        feed_rows.append({
            'item': item,
            'feed_type': ft,
            'kg': float(item.quantity),
            'value': float(item.quantity) * float(item.cost_per_unit),
            'low': item.quantity <= item.reorder_level,
        })

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'items': items,
        'feed_rows': feed_rows,
        'low_stock': low_stock,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,

        'total_kg': total_kg,
        'total_value': total_value,

        'today': timezone.now().date(),
        'page_title': 'Feed Inventory',
        'page_subtitle': f'{items.count()} item{"s" if items.count() != 1 else ""}',
    }
    return render(request, 'kuku_biz/feed_inventory.html', context)

# ============================================================
# INVENTORY — OTHER
# ============================================================

@login_required
def other_inventory(request):
    """Inventory — everything that isn't eggs or feed."""
    company, is_viewing_company = _require_company(request)
    redir = _redirect_if_no_company(request, company)
    if redir:
        return redir

    branches = Branch.objects.filter(company=company, is_active=True).order_by('name')
    user_branch = request.user.branch
    can_see_all = _can_see_all_branches(request, is_viewing_company)

    selected_branch_id = request.GET.get('branch', '').strip()
    if not can_see_all and user_branch:
        selected_branch_id = str(user_branch.id)

    items = (
        InventoryItem.objects
        .filter(company=company)
        .exclude(item_type__in=['egg_tray', 'egg_crate', 'feed_bag'])
        .select_related('branch')
        .order_by('branch__name', 'name')
    )
    if selected_branch_id:
        items = items.filter(branch_id=selected_branch_id)

    total_value = sum(i.stock_value for i in items)

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'items': items,
        'branches': branches,
        'selected_branch_id': selected_branch_id,
        'can_see_all_branches': can_see_all,
        'user_branch': user_branch,
        'total_value': total_value,
        'today': timezone.now().date(),
        'page_title': 'Other Supplies',
        'page_subtitle': f'{items.count()} item{"s" if items.count() != 1 else ""}',
    }
    return render(request, 'kuku_biz/other_inventory.html', context)


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
            try:
                tray_size = int(request.POST.get('tray_size') or 0)
            except (TypeError, ValueError):
                tray_size = 0
            quantity = _to_decimal(request.POST.get('quantity'))

            if not name:
                messages.error(request, 'Item name is required.')
                return render(request, 'kuku_biz/inventory_form.html', {
                    'company': company,
                    'is_viewing_company': is_viewing_company,
                    'branches': branches,
                    'item_types': INVENTORY_ITEM_TYPE_CHOICES,
                    'tray_sizes': TRAY_SIZE_CHOICES,
                    'form_data': request.POST,
                    'page_title': 'Add Inventory Stock',
                })

            # Image upload
            new_image_key = ''
            image_file = request.FILES.get('image')
            if image_file:
                try:
                    new_image_key = _upload_image(
                        image_file, 'kuku/inventory', f"item_{company.id}"
                    )
                except ValueError as e:
                    messages.error(request, str(e))
                    return render(request, 'kuku_biz/inventory_form.html', {
                        'company': company,
                        'is_viewing_company': is_viewing_company,
                        'branches': branches,
                        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
                        'tray_sizes': TRAY_SIZE_CHOICES,
                        'form_data': request.POST,
                        'page_title': 'Add Inventory Stock',
                    })
                except Exception as e:
                    messages.error(request, f'Image upload failed: {e}')
                    return render(request, 'kuku_biz/inventory_form.html', {
                        'company': company,
                        'is_viewing_company': is_viewing_company,
                        'branches': branches,
                        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
                        'tray_sizes': TRAY_SIZE_CHOICES,
                        'form_data': request.POST,
                        'page_title': 'Add Inventory Stock',
                    })

            # Auto-merge only when name + type + tray_size + branch match
            existing = InventoryItem.objects.filter(
                company=company, branch=branch,
                name__iexact=name, item_type=item_type,
                tray_size=tray_size,
            ).first()

            if existing:
                existing.quantity += quantity
                if new_image_key:
                    old_key = _extract_cloudinary_key(existing.image)
                    existing.image = new_image_key
                    existing.save()
                    if old_key and old_key != new_image_key:
                        _destroy_cloudinary_asset(old_key)
                else:
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
                    tray_size=tray_size,
                    quantity=quantity,
                    unit=request.POST.get('unit', '').strip(),
                    reorder_level=_to_decimal(request.POST.get('reorder_level')),
                    cost_per_unit=_to_decimal(request.POST.get('cost_per_unit')),
                    image=new_image_key,
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
        'tray_sizes': TRAY_SIZE_CHOICES,
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

            old_key = _extract_cloudinary_key(item.image)

            item.branch = branch
            item.name = request.POST.get('name', '').strip()
            item.item_type = request.POST.get('item_type', 'other')
            try:
                item.tray_size = int(request.POST.get('tray_size') or 0)
            except (TypeError, ValueError):
                item.tray_size = 0
            item.quantity = _to_decimal(request.POST.get('quantity'))
            item.unit = request.POST.get('unit', '').strip()
            item.reorder_level = _to_decimal(request.POST.get('reorder_level'))
            item.cost_per_unit = _to_decimal(request.POST.get('cost_per_unit'))
            item.notes = request.POST.get('notes', '').strip()

            if request.POST.get('remove_image') == 'on':
                _destroy_cloudinary_asset(old_key)
                item.image = ''
                old_key = ''

            image_file = request.FILES.get('image')
            if image_file:
                try:
                    new_key = _upload_image(
                        image_file, 'kuku/inventory', f"item_{company.id}"
                    )
                    item.image = new_key
                    if old_key and old_key != new_key:
                        _destroy_cloudinary_asset(old_key)
                except ValueError as e:
                    messages.error(request, str(e))
                    return render(request, 'kuku_biz/inventory_form.html', {
                        'company': company,
                        'is_viewing_company': is_viewing_company,
                        'item': item,
                        'branches': branches,
                        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
                        'tray_sizes': TRAY_SIZE_CHOICES,
                        'page_title': f'Edit {item.name}',
                    })
                except Exception as e:
                    messages.error(request, f'Image upload failed: {e}')
                    return render(request, 'kuku_biz/inventory_form.html', {
                        'company': company,
                        'is_viewing_company': is_viewing_company,
                        'item': item,
                        'branches': branches,
                        'item_types': INVENTORY_ITEM_TYPE_CHOICES,
                        'tray_sizes': TRAY_SIZE_CHOICES,
                        'page_title': f'Edit {item.name}',
                    })

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
        'tray_sizes': TRAY_SIZE_CHOICES,
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

    if item.image:
        _destroy_cloudinary_asset(_extract_cloudinary_key(item.image))

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
    try:
        tray_size = int(request.POST.get('tray_size') or 0)
    except (TypeError, ValueError):
        tray_size = 0
    quantity = _to_decimal(request.POST.get('quantity'))

    from_branch = Branch.objects.filter(id=from_branch_id, company=company, is_active=True).first()
    to_branch = Branch.objects.filter(id=to_branch_id, company=company, is_active=True).first()

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
        name__iexact=item_name, item_type=item_type, tray_size=tray_size,
    ).first()

    if not from_item or from_item.quantity < quantity:
        messages.error(request, 'Insufficient stock in source branch.')
        return redirect('kuku_biz:inventory_list')

    from_item.quantity -= quantity
    from_item.save(update_fields=['quantity'])

    to_item, _ = InventoryItem.objects.get_or_create(
        company=company, branch=to_branch,
        name=item_name, item_type=item_type, tray_size=tray_size,
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

