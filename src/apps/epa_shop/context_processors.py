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