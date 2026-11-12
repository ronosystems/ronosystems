from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from datetime import timedelta, date
from .models import Electronic, Phone, Accessory, Sale, Unit, SaleItem, Owner
from apps.companies.models import Company

# ============================================
# SUPPORT MODE HELPER
# ============================================

def get_active_company(request):
    user = request.user

    # 1. Custom domain resolution (with isolation check)
    tenant_company = getattr(request, 'tenant_company', None)
    if tenant_company is not None:
        user_company = getattr(user, 'company', None) if user.is_authenticated else None

        if (
            not user.is_authenticated
            or user.role == 'super_admin'
            or user_company == tenant_company
        ):
            return tenant_company, False

    # 2. Support Mode: Super admin viewing a specific company
    if user.is_authenticated and user.role == 'super_admin':
        viewing_company_id = request.session.get('viewing_company_id')
        if viewing_company_id:
            try:
                company = Company.objects.get(id=viewing_company_id)
                return company, True
            except Company.DoesNotExist:
                request.session.pop('viewing_company_id', None)
                request.session.pop('support_mode', None)
                request.session.pop('support_started_at', None)

    # 3. Regular mode: user's own company
    if user.is_authenticated and user.company:
        return user.company, False

    return None, False


def is_support_mode(request):
    return (
        request.user.is_authenticated
        and request.user.role == 'super_admin'
        and request.session.get('support_mode', False)
        and request.session.get('viewing_company_id')
    )


# ============================================
# EPA DASHBOARD
# ============================================

@login_required
def epa_dashboard(request):
    """EPA Shop Web Dashboard - Shows company-specific EPA data in HTML"""

    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            messages.info(request, 'Please select a company to view.')
            return redirect('/api/support/select/')

        if not request.user.company:
            messages.warning(request, 'You are not assigned to any company.')
            return redirect('/dashboard/')

        company = request.user.company

    if not is_viewing_company:
        if not company.business_type or 'epa' not in company.business_type.name.lower():
            messages.warning(request, 'Your company is not an EPA Shop.')
            return redirect('/dashboard/')

    user = request.user

    if is_viewing_company and user.role == 'super_admin':
        is_admin = True
        user_branch = None
    else:
        is_admin = (
            user.is_company_admin or
            user.is_company_manager or
            user.is_super_admin or
            user.is_superuser or
            user.is_staff
        )
        user_branch = user.branch if not is_admin else None

    # ============================================
    # Product counts
    # ============================================
    electronics = Electronic.objects.filter(company=company)
    phones = Phone.objects.filter(company=company)
    accessories = Accessory.objects.filter(company=company)

    # Option B: Branch filtering disabled (stock is per BranchStock)
    
    electronics_count = electronics.count()
    phones_count = phones.count()
    accessories_count = accessories.count()
    total_products = electronics_count + phones_count + accessories_count

    # ============================================
    # TOTAL UNITS
    # ============================================
    total_units = Unit.objects.filter(
        Q(phone__company=company) | Q(electronic__company=company)
    )
    total_unit_items = total_units.count()

    # ============================================
    # DONUT CHART DATA (Added)
    # ============================================
    phones_unit_count = Unit.objects.filter(phone__company=company).count()
    electronics_unit_count = Unit.objects.filter(electronic__company=company).count()

    # ============================================
    # TOTAL STOCK
    # ============================================
    total_phone_stock = phones.aggregate(total=Sum('total_quantity_in_stock'))['total'] or 0
    total_electronic_stock = electronics.aggregate(total=Sum('total_quantity_in_stock'))['total'] or 0
    total_accessory_stock = accessories.aggregate(total=Sum('total_quantity_in_stock'))['total'] or 0
    total_stock_items = total_phone_stock + total_electronic_stock + total_accessory_stock
    
    # Accessories are the only ones with a direct stock count for the chart
    accessories_unit_count = total_accessory_stock

    # ============================================
    # Sales data
    # ============================================
    sales = Sale.objects.filter(company=company)

    if not is_viewing_company:
        if user.role == 'company_agent':
            sales = sales.filter(sold_by=user)
        elif user.role == 'company_cashier':
            if user_branch:
                sales = sales.filter(branch=user_branch)
        elif not is_admin and user_branch:
            sales = sales.filter(branch=user_branch)

    total_sales = sales.count()
    total_revenue = sales.aggregate(total=Sum('net_amount'))['total'] or 0

    # ============================================
    # Date-based stats
    # ============================================
    today = timezone.localtime(timezone.now()).date()

    today_sales = sales.filter(sale_date__date=today)
    today_count = today_sales.count()
    today_revenue = today_sales.aggregate(total=Sum('net_amount'))['total'] or 0

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_sales = sales.filter(
        sale_date__date__gte=week_start,
        sale_date__date__lte=min(week_end, today),
    )
    week_count = week_sales.count()
    week_revenue = week_sales.aggregate(total=Sum('net_amount'))['total'] or 0

    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)
    last_week_sales = sales.filter(
        sale_date__date__gte=last_week_start,
        sale_date__date__lte=last_week_end,
    )
    last_week_count = last_week_sales.count()
    last_week_revenue = last_week_sales.aggregate(total=Sum('net_amount'))['total'] or 0

    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    month_sales = sales.filter(
        sale_date__date__gte=month_start,
        sale_date__date__lte=min(month_end, today),
    )
    month_count = month_sales.count()
    month_revenue = month_sales.aggregate(total=Sum('net_amount'))['total'] or 0

    # ============================================
    # Low stock items (Fixed for Option B)
    # ============================================
    low_stock_products = []

    for item in electronics.filter(total_quantity_in_stock__lte=5)[:5]:
        low_stock_products.append({
            'name': f"{item.brand} {item.name}",
            'quantity': item.total_quantity_in_stock,
            'type': 'Electronic',
            'branch': 'N/A'  # Multi-branch now
        })

    for item in phones.filter(total_quantity_in_stock__lte=5)[:5]:
        low_stock_products.append({
            'name': f"{item.brand} {item.model}",
            'quantity': item.total_quantity_in_stock,
            'type': 'Phone',
            'branch': 'N/A'
        })

    for item in accessories.filter(total_quantity_in_stock__lte=5)[:5]:
        low_stock_products.append({
            'name': f"{item.brand} {item.name}",
            'quantity': item.total_quantity_in_stock,
            'type': 'Accessory',
            'branch': 'N/A'
        })

    # ============================================
    # Recent sales & Top products
    # ============================================
    recent_sales = sales.select_related('branch', 'sold_by').order_by('-sale_date')[:10]

    if user.role == 'company_agent' and not is_viewing_company:
        owner = Owner.objects.filter(company=company, phone=user.phone).first()
        if owner:
            agent_units = Unit.objects.filter(owner=owner)
            agent_units_count = agent_units.count()
            agent_available_units = agent_units.filter(status='available').count()
            agent_sold_units = agent_units.filter(status='sold').count()
        else:
            agent_units_count = 0
            agent_available_units = 0
            agent_sold_units = 0
    else:
        agent_units_count = 0
        agent_available_units = 0
        agent_sold_units = 0

    top_products = []
    try:
        top_items = SaleItem.objects.filter(
            sale__company=company
        ).values('item_name').annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold')[:5]
        top_products = top_items
    except Exception:
        pass

    # ============================================
    # Stats & Context
    # ============================================
    stats = {
        'total_products': total_products,
        'electronics': electronics_count,
        'phones': phones_count,
        'accessories': accessories_count,
        'total_unit_items': total_unit_items,
        'total_stock_items': total_stock_items,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'today_sales': today_count,
        'today_revenue': today_revenue,
        'week_sales': week_count,
        'week_revenue': week_revenue,
        'month_sales': month_count,
        'month_revenue': month_revenue,
        'low_stock': len(low_stock_products),
        'last_week_sales': last_week_count,
        'last_week_revenue': last_week_revenue,
        'agent_units': agent_units_count,
        'agent_available': agent_available_units,
        'agent_sold': agent_sold_units,
        
        # 👇 DONUT CHART DATA ADDED HERE
        'phones_unit_count': phones_unit_count,
        'electronics_unit_count': electronics_unit_count,
        'accessories_unit_count': accessories_unit_count,
    }

    context = {
        'company': company,
        'business_type': company.business_type,
        'stats': stats,
        'recent_sales': recent_sales,
        'low_stock_products': low_stock_products[:5],
        'top_products': top_products,
        'is_admin': is_admin,
        'is_viewing_company': is_viewing_company,
        'support_mode': is_viewing_company,
        'user_role': user.role,
        'user_branch': user_branch,
        'is_super_admin': user.role == 'super_admin',
        'today': today,
        'week_start': week_start,
        'week_end': week_end,
        'month_start': month_start,
        'month_end': month_end,
        'page_title': f'EPA Dashboard - {company.name}' if is_viewing_company else 'EPA Dashboard',
        'page_subtitle': f'Welcome back, {user.get_full_name() or user.username}!',
    }

    return render(request, 'epa/dashboard.html', context)