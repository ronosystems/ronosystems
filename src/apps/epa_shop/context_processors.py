# apps/epa_shop/context_processors.py

def user_context(request):
    if request.user.is_authenticated:
        is_admin = (
            request.user.is_company_admin or 
            request.user.is_company_manager or 
            request.user.is_super_admin or
            request.user.is_superuser or
            request.user.is_staff
        )
        return {
            'is_admin_or_manager': is_admin,
            'user_branch': request.user.branch,
            'user_role': request.user.role,
        }
    return {
        'is_admin_or_manager': False,
        'user_branch': None,
        'user_role': None,
    }

def sidebar_low_stock_count(request):
    """
    Dedicated context processor to calculate low stock count for the sidebar.
    Runs on every page.
    """
    from apps.companies.support_utils import get_active_company
    from apps.epa_shop.models import Phone, Electronic, Accessory, Unit
    
    company, _ = get_active_company(request)
    if not company:
        return {'sidebar_low_stock_count': 0}
        
    role = getattr(request.user, 'role', '')
    if role not in ('company_admin', 'stock_controller', 'super_admin', 'company_manager'):
        return {'sidebar_low_stock_count': 0}
        
    count = 0
    
    # 1. Count live units for Phones
    for item in Phone.objects.filter(company=company, is_active=True):
        if Unit.objects.filter(phone=item, status='available').count() <= 5:
            count += 1
            
    # 2. Count live units for Electronics
    for item in Electronic.objects.filter(company=company, is_active=True):
        if Unit.objects.filter(electronic=item, status='available').count() <= 5:
            count += 1
            
    # 3. Count Accessories
    for item in Accessory.objects.filter(company=company, is_active=True):
        if item.total_quantity_in_stock <= 5:
            count += 1
            
    return {'sidebar_low_stock_count': count}

# /home/rs/ronosystems/src/apps/epa_shop/context_processors.py

from apps.cart_orders.models import Order

def pending_orders_count(request):
    company = getattr(request, 'current_company', None)
    
    # If there is no company, or the user is not logged in, return 0
    if not company or not request.user.is_authenticated:
        return {'pending_orders_count': 0}

    # Count the open orders (new, picked, confirmed) for this company
    count = Order.objects.filter(
        company=company,
        status__in=['new', 'picked', 'confirmed']
    ).count()

    return {'pending_orders_count': count}