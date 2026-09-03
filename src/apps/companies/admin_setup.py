from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Company
from apps.accounts.permissions import IsSuperAdmin
from apps.accounts.serializers import UserSerializer

User = get_user_model()

class SetupCompanyAdminView(APIView):
    """
    Super Admin: Setup a company admin for a company
    """
    permission_classes = [IsSuperAdmin]
    
    def post(self, request):
        company_id = request.data.get('company_id')
        email = request.data.get('email')
        username = request.data.get('username')
        password = request.data.get('password')
        
        # Validate company
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return Response(
                {'error': 'Company not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate required fields
        if not all([company_id, email, username, password]):
            return Response(
                {'error': 'company_id, email, username, password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if email exists
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'User with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate password
        try:
            validate_password(password)
        except ValidationError as e:
            return Response(
                {'error': list(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create company admin
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role='company_admin',
            company=company,
            is_verified=True,
            phone=request.data.get('phone', ''),
            first_name=request.data.get('first_name', ''),
            last_name=request.data.get('last_name', ''),
        )
        
        serializer = UserSerializer(user)
        return Response({
            'success': True,
            'message': f'Company admin created for {company.name}',
            'user': serializer.data
        }, status=status.HTTP_201_CREATED)

class CompanyAdminListView(APIView):
    """
    Super Admin: List all company admins
    """
    permission_classes = [IsSuperAdmin]
    
    def get(self, request):
        admins = User.objects.filter(role='company_admin').order_by('-created_at')
        serializer = UserSerializer(admins, many=True)
        return Response({
            'count': admins.count(),
            'company_admins': serializer.data
        })
