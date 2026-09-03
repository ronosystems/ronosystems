from rest_framework import generics, status
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
        if role not in ['super_admin', 'company_admin', 'company_manager', 'company_cashier', 'company_agent', 'company_staff', 'guest']:
            return Response(
                {'error': 'Invalid role. Choose: super_admin, company_admin, company_manager, company_cashier, company_agent, company_staff, guest'},
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
        return Response({
            'user_id': request.user.id,
            'username': request.user.username,
            'email': request.user.email,
            'role': request.user.role,
            'company': request.user.company.name if request.user.company else None,
            'permissions': {
                'is_super_admin': request.user.role == 'super_admin',
                'is_company_admin': request.user.role == 'company_admin',
                'is_company_manager': request.user.role == 'company_manager',
                'is_company_cashier': request.user.role == 'company_cashier',
                'is_company_agent': request.user.role == 'company_agent',
                'is_company_staff': request.user.role == 'company_staff',
                'is_guest': request.user.role == 'guest',
            }
        })
