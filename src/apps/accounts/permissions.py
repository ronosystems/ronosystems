# apps/users/permissions.py

from rest_framework import permissions


class IsSuperAdmin(permissions.BasePermission):
    """Allow only super admins"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'super_admin'


class IsCompanyAdmin(permissions.BasePermission):
    """Allow only company admins"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'company_admin'


class IsCompanyManager(permissions.BasePermission):
    """Allow only company managers"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'company_manager'


class IsCompanyCashier(permissions.BasePermission):
    """Allow only company cashiers"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'company_cashier'


class IsCompanyAgent(permissions.BasePermission):
    """Allow only company agents"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'company_agent'


class IsCompanyStaff(permissions.BasePermission):
    """Allow only company staff"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'company_staff'


class IsAdminOrManager(permissions.BasePermission):
    """Allow company admins, managers, and super admins"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['super_admin', 'company_admin', 'company_manager']


class IsSuperAdminOrCompanyAdmin(permissions.BasePermission):
    """Allow super admins and company admins"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['super_admin', 'company_admin']


class IsSameCompany(permissions.BasePermission):
    """Check if user belongs to same company"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if request.user.role == 'super_admin':
            return True
        
        company_id = request.query_params.get('company_id') or request.data.get('company_id')
        if company_id:
            return str(request.user.company.id) == str(company_id)
        
        return True
    
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'super_admin':
            return True
        
        if hasattr(obj, 'company'):
            return obj.company == request.user.company
        elif hasattr(obj, 'company_id'):
            return obj.company_id == request.user.company.id
        
        return False


class IsSameBranch(permissions.BasePermission):
    """Check if user belongs to same branch"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if request.user.role in ['super_admin', 'company_admin', 'company_manager']:
            return True
        
        branch_id = request.query_params.get('branch_id') or request.data.get('branch_id')
        if branch_id and request.user.branch:
            return str(request.user.branch.id) == str(branch_id)
        
        return True


class HasCompanyAccess(permissions.BasePermission):
    """Check if user has access to a company"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Super admins can access everything
        if request.user.role == 'super_admin':
            return True
        
        # Company admins and managers can access their own company
        if request.user.role in ['company_admin', 'company_manager']:
            company_id = request.query_params.get('company_id') or request.data.get('company_id')
            if company_id:
                return str(request.user.company.id) == str(company_id)
            return True
        
        # Other roles have limited access
        return False


class CanProcessSales(permissions.BasePermission):
    """Allow users who can process sales"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in [
            'super_admin', 'company_admin', 'company_manager', 
            'company_cashier', 'company_agent'
        ]


class CanApproveSales(permissions.BasePermission):
    """Allow users who can approve sales"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['super_admin', 'company_admin', 'company_manager']


class CanViewReports(permissions.BasePermission):
    """Allow users who can view reports"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['super_admin', 'company_admin', 'company_manager']


class CanManageUsers(permissions.BasePermission):
    """Allow users who can manage other users"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.role in ['super_admin', 'company_admin']


class IsAuthenticatedOrReadOnly(permissions.BasePermission):
    """Allow read-only access for unauthenticated users"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated