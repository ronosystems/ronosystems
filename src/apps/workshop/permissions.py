# apps/workshop/permissions.py

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from rest_framework import permissions


WORKSHOP_ROLES = {
    'super_admin',
    'company_admin',
    'company_manager',       # optional — remove if you want strict roles
    'company_technician',
    'stock_controller',
}


def user_has_workshop_access(user):
    """
    True if:
      - user is authenticated
      - user.role is in WORKSHOP_ROLES
      - user has a company
      - company's active plan includes has_workshop
    Super admins bypass the role and plan checks.
    """
    if not user or not user.is_authenticated:
        return False

    if user.role == 'super_admin':
        return True

    if user.role not in WORKSHOP_ROLES:
        return False

    company = getattr(user, 'company', None)
    if not company:
        return False

    # Prefer active subscription
    sub = (
        company.subscriptions
        .filter(status='active')
        .select_related('plan')
        .order_by('-created_at')
        .first()
    )
    if sub:
        return sub.has_workshop_access

    # Fallback: company.plan FK
    plan = getattr(company, 'plan', None)
    return bool(plan and plan.has_workshop)


def workshop_required(view_func):
    """Decorator for FBVs: gates a view on workshop access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not user_has_workshop_access(request.user):
            messages.error(
                request,
                'You do not have access to the Workshop module. '
                'Either your plan does not include it, or your role is not permitted.'
            )
            return redirect('/no-access/')
        return view_func(request, *args, **kwargs)
    return wrapper


class HasWorkshopAccess(permissions.BasePermission):
    """DRF permission class — same logic."""
    message = 'You do not have access to the Workshop module.'

    def has_permission(self, request, view):
        return user_has_workshop_access(request.user)


class IsTechnicianOrAdmin(permissions.BasePermission):
    """Who can create/edit jobs. Broader than access — allows stock_controller to view but not edit."""
    ALLOWED = {'super_admin', 'company_admin', 'company_manager', 'company_technician'}

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if not user_has_workshop_access(user):
            return False
        return user.role in self.ALLOWED