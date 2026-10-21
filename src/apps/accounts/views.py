# apps/users/views.py

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model, logout
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from apps.companies.models import Company
from apps.company.models import Branch
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    UserUpdateSerializer, UserRoleUpdateSerializer,
    UserCompanyUpdateSerializer, UserPasswordChangeSerializer,
    UserPasswordResetSerializer
)
from .permissions import (
    IsSuperAdmin, IsCompanyAdmin, IsAdminOrManager,
    IsSuperAdminOrCompanyAdmin, HasCompanyAccess,
    IsSameCompany, IsSameBranch, CanManageUsers
)

User = get_user_model()


# ============================================================
# AUTH
# ============================================================

class RegisterView(generics.CreateAPIView):
    """Register a new user"""
    serializer_class = RegisterSerializer
    permission_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.perform_create(serializer)

        # Send welcome email
        try:
            subject = 'Welcome to RonoSystems'
            html_message = render_to_string('emails/welcome.html', {'user': user})
            plain_message = strip_tags(html_message)
            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
            )
        except Exception:
            pass

        headers = self.get_success_headers(serializer.data)
        return Response({
            'success': True,
            'message': 'User registered successfully',
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED, headers=headers)


class LoginView(APIView):
    """Login user"""
    permission_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Generate tokens (JWT)
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)

            return Response({
                'success': True,
                'message': 'Login successful',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """Logout user"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # For JWT, blacklist the refresh token
            refresh_token = request.data.get('refresh')
            if refresh_token:
                from rest_framework_simplejwt.tokens import RefreshToken
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass

        # Django logout
        logout(request)

        return Response({
            'success': True,
            'message': 'Logout successful'
        })


# ============================================================
# PROFILE
# ============================================================

class UserProfileView(APIView):
    """Get and update current user profile"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'user': UserSerializer(request.user).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# USER LISTING
# ============================================================

class UserListView(APIView):
    """List all users (Super Admin only)"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        users = User.objects.all().order_by('-created_at')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class CompanyUserListView(APIView):
    """List users in a specific company"""
    permission_classes = [IsAuthenticated, IsSuperAdminOrCompanyAdmin, HasCompanyAccess]

    def get(self, request):
        company_id = request.query_params.get('company_id')

        if company_id:
            users = User.objects.filter(company_id=company_id)
        else:
            users = User.objects.filter(company=request.user.company)

        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


# ============================================================
# USER ROLE / COMPANY / BRANCH MANAGEMENT
# ============================================================

class UserRoleUpdateView(APIView):
    """Update user role (Super Admin only)"""
    permission_classes = [IsSuperAdmin]

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserRoleUpdateSerializer(data=request.data)
        if serializer.is_valid():
            user.role = serializer.validated_data['role']
            user.save()

            return Response({
                'success': True,
                'message': f"Role updated to {user.role}",
                'user': UserSerializer(user).data
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserCompanyUpdateView(APIView):
    """Update user company (Super Admin only)"""
    permission_classes = [IsSuperAdmin]

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserCompanyUpdateSerializer(data=request.data)
        if serializer.is_valid():
            company_id = serializer.validated_data['company_id']
            try:
                company = Company.objects.get(id=company_id)
                user.company = company

                # Update role if provided
                if serializer.validated_data.get('role'):
                    user.role = serializer.validated_data['role']

                user.save()

                return Response({
                    'success': True,
                    'message': f"User assigned to {company.name}",
                    'user': UserSerializer(user).data
                })
            except Company.DoesNotExist:
                return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserBranchUpdateView(APIView):
    """Update user branch (Admin/Manager only)"""
    permission_classes = [IsAuthenticated, IsAdminOrManager, IsSameCompany]

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id, company=request.user.company)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found in your company'},
                status=status.HTTP_404_NOT_FOUND
            )

        branch_id = request.data.get('branch_id')

        if not branch_id:
            return Response(
                {'error': 'branch_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            branch = Branch.objects.get(id=branch_id, company=request.user.company)
        except Branch.DoesNotExist:
            return Response(
                {'error': 'Branch not found in your company'},
                status=status.HTTP_404_NOT_FOUND
            )

        user.branch = branch
        user.save()

        return Response({
            'success': True,
            'message': f'User assigned to {branch.name}',
            'user': UserSerializer(user).data
        })


# ============================================================
# PASSWORD
# ============================================================

class UserChangePasswordView(APIView):
    """Change user password"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserPasswordChangeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()

            return Response({
                'success': True,
                'message': 'Password changed successfully'
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserPasswordResetView(APIView):
    """Request password reset"""
    permission_classes = []

    def post(self, request):
        serializer = UserPasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'User with this email does not exist'
                }, status=status.HTTP_404_NOT_FOUND)

            # Generate reset token
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes
            from django.contrib.auth.tokens import default_token_generator

            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"

            # Send email
            try:
                subject = 'Password Reset Request'
                html_message = render_to_string('emails/password_reset.html', {
                    'user': user,
                    'reset_link': reset_link
                })
                plain_message = strip_tags(html_message)
                send_mail(
                    subject,
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=html_message,
                )
            except Exception as e:
                print(f"Error sending email: {e}")

            return Response({
                'success': True,
                'message': 'Password reset link sent to your email'
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# ROLE INFO
# ============================================================

class UserRoleInfoView(APIView):
    """Get current user's role info"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Use model property if available, otherwise fall back
        role_flags = getattr(user, 'role_flags', None)
        if not role_flags:
            role_flags = {
                # Platform
                'is_super_admin': user.role == 'super_admin',
                'is_site_manager': user.role == 'site_manager',
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
                # Chama
                'is_chairperson': user.role == 'chairperson',
                'is_vice_chairperson': user.role == 'vice_chairperson',
                'is_secretary': user.role == 'secretary',
                'is_vice_secretary': user.role == 'vice_secretary',
                'is_treasurer': user.role == 'treasurer',
                'is_loan_officer': user.role == 'loan_officer',
                'is_coopted_member': user.role == 'coopted_member',
                'is_member': user.role == 'member',
            }

        # Capability flags — now including Chama roles
        capability_flags = {
            # Platform
            'can_manage_users':   user.role in ['super_admin', 'company_admin'],
            'can_manage_sales':   user.role in ['super_admin', 'company_admin', 'company_manager', 'company_cashier'],
            'can_view_reports':   user.role in ['super_admin', 'company_admin', 'company_manager'],
            'can_approve_sales':  user.role in ['super_admin', 'company_admin', 'company_manager'],
            'can_process_sales':  user.role in ['super_admin', 'company_admin', 'company_manager', 'company_cashier', 'company_agent'],
            'can_handle_tickets': user.role in ['super_admin', 'company_admin', 'company_manager', 'customer_care'],
            'can_perform_jobs':   user.role in ['super_admin', 'company_admin', 'company_manager', 'company_technician'],

            # ───── Chama capabilities ─────
            'can_manage_members':       user.role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'secretary', 'vice_secretary'],
            'can_manage_savings':       user.role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'treasurer'],
            'can_manage_loans':         user.role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer'],
            'can_manage_cashbook':      user.role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'treasurer'],
            'can_manage_meetings':      user.role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'secretary', 'vice_secretary', 'treasurer', 'loan_officer', 'coopted_member', 'member'],
            'can_manage_committees':    user.role in ['super_admin', 'company_admin', 'chairperson', 'secretary'],
            'can_view_chama_reports':   user.role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'treasurer', 'loan_officer'],
            'can_view_own_savings':     user.role in ['chairperson', 'vice_chairperson', 'secretary', 'vice_secretary', 'treasurer', 'loan_officer', 'coopted_member', 'member'],
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
            }
        })


# ============================================================
# USER DELETE / STATUS
# ============================================================

class UserDeleteView(APIView):
    """Delete a user (Super Admin only)"""
    permission_classes = [IsSuperAdmin]

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            # Prevent self-deletion
            if user.id == request.user.id:
                return Response({
                    'error': 'You cannot delete your own account'
                }, status=status.HTTP_400_BAD_REQUEST)

            user.delete()
            return Response({
                'success': True,
                'message': 'User deleted successfully'
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class UserStatusToggleView(APIView):
    """Toggle user active status (Super Admin only)"""
    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            # Prevent self-deactivation
            if user.id == request.user.id:
                return Response({
                    'error': 'You cannot deactivate your own account'
                }, status=status.HTTP_400_BAD_REQUEST)

            user.is_active = not user.is_active
            user.save()

            return Response({
                'success': True,
                'message': f"User {'activated' if user.is_active else 'deactivated'} successfully",
                'is_active': user.is_active
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)