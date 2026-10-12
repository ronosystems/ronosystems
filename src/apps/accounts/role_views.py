# apps/accounts/role_views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .serializers import UserSerializer
from .permissions import IsSuperAdmin, IsCompanyAdmin, IsSameCompany

User = get_user_model()


class UserRoleUpdateView(APIView):
    """Update user role (Super Admin only)"""
    permission_classes = [IsSuperAdmin]

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        role = request.data.get('role')
        valid_roles = [choice[0] for choice in User.ROLE_CHOICES]

        if role not in valid_roles:
            return Response(
                {'error': f'Invalid role. Choose one of: {", ".join(valid_roles)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.role = role
        user.save()

        return Response({
            'success': True,
            'message': f'Role updated to {role}',
            'user': UserSerializer(user).data
        })


class CompanyUserListView(APIView):
    """List users in a specific company (Company Admin)"""
    permission_classes = [IsCompanyAdmin, IsSameCompany]

    def get(self, request):
        users = User.objects.filter(company=request.user.company)
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class UserRoleInfoView(APIView):
    """Get current user's role info"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Prefer the model's role_flags property (single source of truth).
        # Fall back to a manual build so this view never breaks if the
        # property is renamed or removed.
        role_flags = getattr(user, 'role_flags', None)
        if not role_flags:
            role_flags = {
                'is_super_admin': user.role == 'super_admin',
                'is_company_admin': user.role == 'company_admin',
                'is_company_manager': user.role == 'company_manager',
                'is_company_cashier': user.role == 'company_cashier',
                'is_stock_controller': user.role == 'stock_controller',
                'is_company_agent': user.role == 'company_agent',
                'is_mpesa_agent': user.role == 'mpesa_agent',
                'is_company_technician': user.role == 'company_technician',
                'is_customer_care': user.role == 'customer_care',
                'is_company_staff': user.role == 'company_staff',
                'is_guest': user.role == 'guest',
            }

        capability_flags = {
            'can_manage_users':   user.role in ['super_admin', 'company_admin'],
            'can_manage_sales':   user.role in ['super_admin', 'company_admin', 'company_manager', 'company_cashier'],
            'can_view_reports':   user.role in ['super_admin', 'company_admin', 'company_manager'],
            'can_approve_sales':  user.role in ['super_admin', 'company_admin', 'company_manager'],
            'can_process_sales':  user.role in ['super_admin', 'company_admin', 'company_manager', 'company_cashier', 'company_agent'],
            'can_handle_tickets': user.role in ['super_admin', 'company_admin', 'company_manager', 'customer_care'],
            'can_perform_jobs':   user.role in ['super_admin', 'company_admin', 'company_manager', 'company_technician'],
        }

        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.full_name,
            'role': user.role,
            'role_display': user.get_role_display(),
            'company': user.company.name if user.company else None,
            'company_id': user.company.id if user.company else None,
            'branch': user.branch.name if user.branch else None,
            'branch_id': user.branch.id if user.branch else None,
            'permissions': {
                **role_flags,
                **capability_flags,
            },
        })