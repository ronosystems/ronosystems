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