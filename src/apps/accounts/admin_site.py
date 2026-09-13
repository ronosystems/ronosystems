from django.contrib.admin import AdminSite
from django.shortcuts import redirect
from django.contrib import messages


class RestrictedAdminSite(AdminSite):
    """Only super_admin users can access /admin/."""

    site_header = 'RonoSystems Administration'
    site_title = 'RonoSystems Admin'
    index_title = 'System Administration'

    def login(self, request, extra_context=None):
        # Logged in but not super_admin → send to no-access
        if request.user.is_authenticated and request.user.role != 'super_admin':
            messages.error(request, 'You do not have permission to access the admin panel.')
            return redirect('/no-access/')   # ✅ FIXED
        return super().login(request, extra_context)

    def has_permission(self, request):
        if not request.user.is_active or not request.user.is_staff:
            return False
        return request.user.role == 'super_admin'


restricted_admin_site = RestrictedAdminSite(name='admin')