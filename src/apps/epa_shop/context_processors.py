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

# apps/epa_shop/context_processors.py
from .models import Sale

def pending_orders_count(request):
    """
    Returns the count of unassigned pending orders for the current company.
    Only runs for authenticated users on a company domain.
    """
    current_company = getattr(request, 'current_company', None)
    if not current_company or not request.user.is_authenticated:
        return {'pending_orders_count': 0}

    count = Sale.objects.filter(
        company=current_company,
        payment_status='pending',
        assigned_to__isnull=True
    ).count()

    return {'pending_orders_count': count}