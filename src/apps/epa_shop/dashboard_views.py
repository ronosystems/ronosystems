from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from datetime import timedelta
from .models import Electronic, Phone, Accessory, Sale, Unit, SaleItem
from apps.companies.models import Company


@login_required
def epa_dashboard(request):
    """EPA Shop Web Dashboard - Shows company-specific EPA data in HTML"""
    
    # ============================================
    # COMPANY SELECTION (with super admin switching)
    # ============================================
    
    company = None
    is_viewing_company = False
    
    # Check if super admin is viewing a specific company
    if request.user.role == 'super_admin' and 'viewing_company_id' in request.session:
        try:
            company = Company.objects.get(id=request.session['viewing_company_id'])
            is_viewing_company = True
        except Company.DoesNotExist:
            if 'viewing_company_id' in request.session:
                del request.session['viewing_company_id']
            messages.warning(request, 'Company not found. Returning to your dashboard.')
            return redirect('/super-admin/dashboard/')
    
    # If no company found, use the user's company
    if not company:
        # SUPER ADMIN: If no company is selected, redirect to company selection
        if request.user.role == 'super_admin':
            messages.info(request, 'Please select a company to view.')
            return redirect('/companies/')
        
        # Regular user: Check if assigned to a company
        if not request.user.company:
            messages.warning(request, 'You are not assigned to any company.')
            return redirect('/admin/')
        company = request.user.company
    
    # ============================================
    # BUSINESS TYPE VALIDATION (Skip for super admin)
    # ============================================
    
    # Skip business type check for super admin in support mode
    if not (request.user.role == 'super_admin' and is_viewing_company):
        if not company.business_type or 'epa' not in company.business_type.name.lower():
            messages.warning(request, 'Your company is not an EPA Shop.')
            return redirect('/dashboard/')
    
    # ============================================
    # Role-based data filtering
    # ============================================
    
    user = request.user
    
    # For super admin viewing a company, treat as admin
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
    # Product counts (filtered by branch for non-admins)
    # ============================================
    
    electronics = Electronic.objects.filter(company=company)
    phones = Phone.objects.filter(company=company)
    accessories = Accessory.objects.filter(company=company)
    
    # Filter by branch for non-admins
    if not is_admin and user_branch:
        electronics = electronics.filter(branch=user_branch)
        phones = phones.filter(branch=user_branch)
        accessories = accessories.filter(branch=user_branch)
    
    electronics_count = electronics.count()
    phones_count = phones.count()
    accessories_count = accessories.count()
    total_products = electronics_count + phones_count + accessories_count
    
    # ============================================
    # Sales data (filtered by branch/agent)
    # ============================================
    
    sales = Sale.objects.filter(company=company)
    
    # Filter by role
    if user.role == 'company_agent' and not is_viewing_company:
        # Agents see only sales they created
        sales = sales.filter(sold_by=user)
    elif user.role == 'company_cashier' and not is_viewing_company:
        # Cashiers see sales in their branch
        if user_branch:
            sales = sales.filter(branch=user_branch)
    elif not is_admin and user_branch and not is_viewing_company:
        # Staff see sales in their branch
        sales = sales.filter(branch=user_branch)
    
    total_sales = sales.count()
    total_revenue = sales.aggregate(total=Sum('net_amount'))['total'] or 0
    
    # Today's sales
    today = timezone.now().date()
    today_sales = sales.filter(sale_date__date=today)
    today_count = today_sales.count()
    today_revenue = today_sales.aggregate(total=Sum('net_amount'))['total'] or 0
    
    # Week sales
    week_ago = today - timedelta(days=7)
    week_sales = sales.filter(sale_date__date__gte=week_ago).count()
    
    # Month sales
    month_ago = today - timedelta(days=30)
    month_sales = sales.filter(sale_date__date__gte=month_ago).count()
    
    # ============================================
    # Low stock items (filtered by branch)
    # ============================================
    
    low_stock_products = []
    
    electronics_low = electronics.filter(quantity_in_stock__lte=F('minimum_stock_level'))
    phones_low = phones.filter(quantity_in_stock__lte=F('minimum_stock_level'))
    accessories_low = accessories.filter(quantity_in_stock__lte=F('minimum_stock_level'))
    
    for item in electronics_low[:5]:
        low_stock_products.append({
            'name': f"{item.brand} {item.name}",
            'quantity': item.quantity_in_stock,
            'type': 'Electronic',
            'branch': item.branch.name if item.branch else 'N/A'
        })
    
    for item in phones_low[:5]:
        low_stock_products.append({
            'name': f"{item.brand} {item.model}",
            'quantity': item.quantity_in_stock,
            'type': 'Phone',
            'branch': item.branch.name if item.branch else 'N/A'
        })
    
    for item in accessories_low[:5]:
        low_stock_products.append({
            'name': f"{item.brand} {item.name}",
            'quantity': item.quantity_in_stock,
            'type': 'Accessory',
            'branch': item.branch.name if item.branch else 'N/A'
        })
    
    # ============================================
    # Recent sales (filtered)
    # ============================================
    
    recent_sales = sales.select_related('branch', 'sold_by').order_by('-sale_date')[:10]
    
    # ============================================
    # Agent-specific stats (units owned by agent)
    # ============================================
    
    if user.role == 'company_agent' and not is_viewing_company:
        from .models import Owner
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
    
    # ============================================
    # Top selling products
    # ============================================
    
    top_products = []
    try:
        from django.db.models import Sum as SumModel
        top_items = SaleItem.objects.filter(
            sale__company=company
        ).values('item_name').annotate(
            total_sold=SumModel('quantity')
        ).order_by('-total_sold')[:5]
        top_products = top_items
    except:
        pass
    
    # ============================================
    # Stats for template
    # ============================================
    
    stats = {
        'total_products': total_products,
        'electronics': electronics_count,
        'phones': phones_count,
        'accessories': accessories_count,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'today_sales': today_count,
        'today_revenue': today_revenue,
        'week_sales': week_sales,
        'month_sales': month_sales,
        'low_stock': len(low_stock_products),
        # Agent-specific stats
        'agent_units': agent_units_count,
        'agent_available': agent_available_units,
        'agent_sold': agent_sold_units,
    }
    
    # ============================================
    # Context
    # ============================================
    
    # Check if in support mode
    is_support_mode = request.session.get('support_mode', False)
    
    context = {
        'company': company,
        'business_type': company.business_type,
        'stats': stats,
        'recent_sales': recent_sales,
        'low_stock_products': low_stock_products[:5],
        'top_products': top_products,
        'is_admin': is_admin,
        'is_viewing_company': is_viewing_company,
        'support_mode': is_support_mode,
        'user_role': user.role,
        'user_branch': user_branch,
        'is_super_admin': user.role == 'super_admin',
        'page_title': f'EPA Dashboard - {company.name}' if is_viewing_company else 'EPA Dashboard',
        'page_subtitle': f'Welcome back, {user.get_full_name() or user.username}!',
    }
    
    return render(request, 'epa/dashboard.html', context)