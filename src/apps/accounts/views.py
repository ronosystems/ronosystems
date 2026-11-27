# apps/accounts/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model, logout, login as django_login
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.http import url_has_allowed_host_and_scheme
from apps.companies.models import Company, Branch
from apps.accounts.models import Membership
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    UserUpdateSerializer, UserRoleUpdateSerializer,
    UserCompanyUpdateSerializer, UserPasswordChangeSerializer,
    UserPasswordResetSerializer, MembershipSerializer,
)
from .permissions import (
    IsSuperAdmin, IsAdminOrManager, IsSuperAdminOrCompanyAdmin,
    HasCompanyAccess, IsSameCompany,
)




User = get_user_model()





# ============================================================
# HELPERS
# ============================================================

def _active_company(request):
    """Return the company for this request (membership-aware)."""
    m = getattr(request, 'membership', None)
    if m and m.company_id:
        return m.company
    return (
        getattr(request, 'company', None)
        or getattr(request, 'current_company', None)
        or getattr(request.user, 'company', None)
    )


def _issue_tokens_for(user, membership=None):
    """Build a JWT whose claims describe the active membership."""
    refresh = RefreshToken.for_user(user)
    if membership:
        refresh['membership_id'] = membership.id
        refresh['company_id']    = membership.company_id
        refresh['role']          = membership.role
    else:
        refresh['company_id']    = user.company_id
        refresh['role']          = user.role
    return refresh


def _bind_session(request, user, membership):
    """Keep Django session in sync (so template pages also work)."""
    django_login(request, user)
    if membership:
        request.session['active_membership_id'] = membership.id
        request.session['active_company_id']    = membership.company_id
    else:
        request.session.pop('active_membership_id', None)
        request.session.pop('active_company_id', None)




# ============================================================
# WEB LOGIN (HTML) - kwa session expired / browser
# Inatumia LoginSerializer ile ile kama API, kwa hiyo
# company_username kama FEK984331 inafanya kazi hapa pia
# ===========================================================

def web_login(request):
    # Kama tayari amelogin
    if request.user.is_authenticated:
        next_url = request.GET.get('next') or request.POST.get('next')
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return post_login_redirect(request)

    if request.method == 'POST':
        # Template yako inatuma field inaitwa "login", serializer inataka "username"
        # Tuna-convert hapa
        data = {
            'username': request.POST.get('login', '').strip(),
            'password': request.POST.get('password', ''),
        }
        serializer = LoginSerializer(data=data, context={'request': request})

        if serializer.is_valid():
            user = serializer.validated_data['user']
            membership = getattr(user, 'active_membership', None)

            # Hii ndiyo ile _bind_session yako uliyonayo - inaweka Django session
            _bind_session(request, user, membership)

            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)

            # Tumia logic yako ya post_login_redirect (superadmin -> /superadmin/, wengine -> /dashboard/)
            return post_login_redirect(request)
        else:
            # Weka error ili template yako ionyeshe modal
            # Template yako inacheck form.errors - tunatuma form dummy
            messages.error(request, 'Invalid Phone/Email or PIN.')
            # Weka form.errors ili trigger ya modal ifanye kazi
            from django import forms
            class DummyForm(forms.Form):
                pass
            form = DummyForm()
            form.add_error(None, 'Invalid login')
    else:
        form = None

    return render(request, 'account/login.html', {
        'form': form,
        'current_company': _active_company(request),
        'next': request.GET.get('next', ''),
    })









# ============================================================
# SESSION / TEMPLATE VIEWS  (unchanged behaviour, safer lookups)
# ============================================================

@login_required
def post_login_redirect(request):
    """Where to send the user after login (template flow)."""
    user = request.user
    current_company = _active_company(request)

    if user.is_superuser or user.role == 'super_admin':
        return redirect('/superadmin/dashboard/')

    if current_company:
        return redirect('/dashboard/')

    return redirect('/select-company/')


@login_required
def select_company(request):
    """List of companies the user belongs to (template flow)."""
    memberships = (
        request.user.memberships
        .filter(is_active=True)
        .select_related('company', 'branch')
    )

    if memberships.count() == 1:
        m = memberships.first()
        return redirect_to_company_dashboard(m.company, request)

    return render(request, 'accounts/select_company.html', {
        'memberships': memberships,
    })


def redirect_to_company_dashboard(company, request):
    """Build the absolute URL for a company subdomain."""
    host = request.get_host()

    if 'localhost' in host:
        base_domain = 'localhost:8000'
        return redirect(f"http://{company.subdomain}.{base_domain}/dashboard/")

    base_domain = 'ronosystems.com'
    if 'onrender.com' in host:
        base_domain = 'ronosystems.onrender.com'

    return redirect(f"https://{company.subdomain}.{base_domain}/dashboard/")


# ============================================================
# AUTH
# ============================================================

class RegisterView(generics.CreateAPIView):
    """Register a new user + company + primary membership."""
    serializer_class = RegisterSerializer
    permission_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        try:
            subject = 'Welcome to RonoSystems'
            html_message = render_to_string('emails/welcome.html', {'user': user})
            send_mail(
                subject,
                strip_tags(html_message),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
            )
        except Exception:
            pass

        headers = self.get_success_headers(serializer.data)
        user.refresh_from_db()

        # Attach the primary membership so the response mirrors login payload
        user.active_membership = user.get_primary_membership()

        return Response({
            'success': True,
            'message': 'User registered successfully',
            'user': UserSerializer(user).data,
        }, status=status.HTTP_201_CREATED, headers=headers)


class LoginView(APIView):
    """
    Multi-tenant login.
    Accepts company_username / email / phone / username + password.
    Issues a JWT carrying membership_id / company_id / role.
    """
    permission_classes = []

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={'request': request},   # ← REQUIRED for MembershipBackend
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']
        membership = getattr(user, 'active_membership', None)

        refresh = _issue_tokens_for(user, membership)
        _bind_session(request, user, membership)

        return Response({
            'success': True,
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'membership_id': membership.id if membership else None,
            'company_id':    membership.company_id if membership else user.company_id,
            'role':          membership.role if membership else user.role,
            'user': UserSerializer(user).data,
        })


class LogoutView(APIView):
    """Blacklist refresh token + clear Django session."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
        except Exception:
            pass

        logout(request)
        request.session.pop('active_membership_id', None)
        request.session.pop('active_company_id', None)

        return Response({'success': True, 'message': 'Logout successful'})


# ============================================================
# MEMBERSHIPS  (multi-company profiles)
# ============================================================

class MyMembershipsView(APIView):
    """List all active memberships of the current user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            request.user.memberships
            .filter(is_active=True)
            .select_related('company', 'branch')
        )
        return Response(MembershipSerializer(qs, many=True).data)


class SwitchCompanyView(APIView):
    """
    Switch active company for this session.
    Issues a NEW JWT bound to the chosen membership.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        membership_id = request.data.get('membership_id')
        membership = (
            request.user.memberships
            .select_related('company', 'branch')
            .filter(pk=membership_id, is_active=True)
            .first()
        )
        if not membership:
            return Response(
                {'error': 'Membership not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        refresh = _issue_tokens_for(request.user, membership)
        request.session['active_membership_id'] = membership.id
        request.session['active_company_id']    = membership.company_id

        # Expose membership on the user for the response serializer
        request.user.active_membership = membership

        return Response({
            'success': True,
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'membership_id':     membership.id,
            'company_id':        membership.company_id,
            'company_subdomain': membership.company.subdomain,
            'role':              membership.role,
            'user':              UserSerializer(request.user).data,
        })


# ============================================================
# PROFILE
# ============================================================

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        request.user.active_membership = getattr(request, 'membership', None)
        return Response(UserSerializer(request.user).data)

    def put(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            request.user.active_membership = getattr(request, 'membership', None)
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'user': UserSerializer(request.user).data,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# USER LISTING
# ============================================================

class UserListView(APIView):
    """List all users (Super Admin only)."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        users = User.objects.all().order_by('-created_at')
        return Response(UserSerializer(users, many=True).data)


class CompanyUserListView(APIView):
    """
    List users in a specific company.
    Uses Membership (source of truth) — not just User.company.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminOrCompanyAdmin, HasCompanyAccess]

    def get(self, request):
        company_id = request.query_params.get('company_id')
        if company_id:
            company = Company.objects.filter(pk=company_id).first()
        else:
            company = _active_company(request)

        if not company:
            return Response(
                {'error': 'Company context required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Users who have a membership in this company
        memberships = (
            Membership.objects
            .filter(company=company, is_active=True)
            .select_related('user', 'user__company', 'user__branch')
        )
        users = [m.user for m in memberships]

        return Response(UserSerializer(users, many=True).data)


# ============================================================
# USER ROLE / COMPANY / BRANCH MANAGEMENT
# ============================================================

class UserRoleUpdateView(APIView):
    """Update user role (Super Admin only). Also updates the active membership."""
    permission_classes = [IsSuperAdmin]

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserRoleUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_role = serializer.validated_data['role']
        user.role = new_role
        user.save(update_fields=['role'])

        # Keep the primary membership in sync (company profile role)
        primary = user.get_primary_membership()
        if primary:
            primary.role = new_role
            primary.save(update_fields=['role'])

        return Response({
            'success': True,
            'message': f"Role updated to {user.role}",
            'user': UserSerializer(user).data,
        })


class UserCompanyUpdateView(APIView):
    """
    Assign a user to a company (Super Admin only).
    Creates/updates the corresponding Membership.
    """
    permission_classes = [IsSuperAdmin]

    def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserCompanyUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        company = Company.objects.filter(pk=serializer.validated_data['company_id']).first()
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        role = serializer.validated_data.get('role') or 'company_staff'

        # Update global company (backward compat)
        user.company = company
        user.role = role
        user.save(update_fields=['company', 'role'])

        # Create or update membership
        membership, _ = Membership.objects.get_or_create(
            user=user, company=company,
            defaults={'role': role, 'is_active': True},
        )
        if membership.role != role:
            membership.role = role
            membership.save(update_fields=['role'])
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=['is_active'])

        return Response({
            'success': True,
            'message': f"User assigned to {company.name}",
            'user': UserSerializer(user).data,
        })


class UserBranchUpdateView(APIView):
    """Update user branch within the active company."""
    permission_classes = [IsAuthenticated, IsAdminOrManager, IsSameCompany]

    def put(self, request, user_id):
        company = _active_company(request)
        if not company:
            return Response(
                {'error': 'Company context required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id, company=company)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found in your company'},
                status=status.HTTP_404_NOT_FOUND,
            )

        branch_id = request.data.get('branch_id')
        if not branch_id:
            return Response(
                {'error': 'branch_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch = Branch.objects.filter(pk=branch_id, company=company).first()
        if not branch:
            return Response(
                {'error': 'Branch not found in your company'},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.branch = branch
        user.save(update_fields=['branch'])

        # Keep membership branch in sync
        m = user.get_membership_for_company(company)
        if m:
            m.branch = branch
            m.save(update_fields=['branch'])

        return Response({
            'success': True,
            'message': f'User assigned to {branch.name}',
            'user': UserSerializer(user).data,
        })


# ============================================================
# PASSWORD
# ============================================================

class UserChangePasswordView(APIView):
    """
    Change password. If there's an active membership, its password
    is updated too — so per-company login stays consistent.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserPasswordChangeSerializer(
            data=request.data,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_password = serializer.validated_data['new_password']

        user = request.user
        user.set_password(new_password)
        user.save(update_fields=['password'])

        # Keep active membership in sync (if any)
        membership = getattr(request, 'membership', None) or user.get_primary_membership()
        if membership:
            membership.set_password(new_password)
            membership.save(update_fields=['password'])

        return Response({
            'success': True,
            'message': 'Password changed successfully',
        })


class UserPasswordResetView(APIView):
    """Request password reset."""
    permission_classes = []

    def post(self, request):
        serializer = UserPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({
                'success': False,
                'message': 'User with this email does not exist',
            }, status=status.HTTP_404_NOT_FOUND)

        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from django.contrib.auth.tokens import default_token_generator

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}"

        try:
            html_message = render_to_string('emails/password_reset.html', {
                'user': user, 'reset_link': reset_link,
            })
            send_mail(
                'Password Reset Request',
                strip_tags(html_message),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error sending email: {e}")

        return Response({
            'success': True,
            'message': 'Password reset link sent to your email',
        })


# ============================================================
# ROLE INFO
# ============================================================

class UserRoleInfoView(APIView):
    """Get current user's role info (membership-aware)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        membership = getattr(request, 'membership', None) or user.get_primary_membership()

        # Effective role: membership wins over global user.role
        effective_role = membership.role if membership else user.role
        effective_company = membership.company if membership else user.company
        effective_branch = membership.branch if membership else user.branch

        role_flags = {
            'is_super_admin': user.role == 'super_admin',
            'is_site_manager': effective_role == 'site_manager',
            'is_company_admin': effective_role == 'company_admin',
            'is_company_manager': effective_role == 'company_manager',
            'is_company_cashier': effective_role == 'company_cashier',
            'is_stock_controller': effective_role == 'stock_controller',
            'is_company_agent': effective_role == 'company_agent',
            'is_mpesa_agent': effective_role == 'mpesa_agent',
            'is_company_technician': effective_role == 'company_technician',
            'is_customer_care': effective_role == 'customer_care',
            'is_company_staff': effective_role == 'company_staff',
            'is_guest': effective_role == 'guest',
            'is_chairperson': effective_role == 'chairperson',
            'is_vice_chairperson': effective_role == 'vice_chairperson',
            'is_secretary': effective_role == 'secretary',
            'is_vice_secretary': effective_role == 'vice_secretary',
            'is_treasurer': effective_role == 'treasurer',
            'is_loan_officer': effective_role == 'loan_officer',
            'is_coopted_member': effective_role == 'coopted_member',
            'is_member': effective_role == 'member',
        }

        capability_flags = {
            'can_manage_users':   effective_role in ['super_admin', 'company_admin'],
            'can_manage_sales':   effective_role in ['super_admin', 'company_admin', 'company_manager', 'company_cashier'],
            'can_view_reports':   effective_role in ['super_admin', 'company_admin', 'company_manager'],
            'can_approve_sales':  effective_role in ['super_admin', 'company_admin', 'company_manager'],
            'can_process_sales':  effective_role in ['super_admin', 'company_admin', 'company_manager', 'company_cashier', 'company_agent'],
            'can_handle_tickets': effective_role in ['super_admin', 'company_admin', 'company_manager', 'customer_care'],
            'can_perform_jobs':   effective_role in ['super_admin', 'company_admin', 'company_manager', 'company_technician'],

            'can_manage_members':     effective_role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'secretary', 'vice_secretary'],
            'can_manage_savings':     effective_role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'treasurer'],
            'can_manage_loans':       effective_role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'treasurer', 'loan_officer'],
            'can_manage_cashbook':    effective_role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'treasurer'],
            'can_manage_meetings':    effective_role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'vice_chairperson', 'secretary', 'vice_secretary', 'treasurer', 'loan_officer', 'coopted_member', 'member'],
            'can_manage_committees':  effective_role in ['super_admin', 'company_admin', 'chairperson', 'secretary'],
            'can_view_chama_reports': effective_role in ['super_admin', 'company_admin', 'company_manager', 'chairperson', 'treasurer', 'loan_officer'],
            'can_view_own_savings':   effective_role in ['chairperson', 'vice_chairperson', 'secretary', 'vice_secretary', 'treasurer', 'loan_officer', 'coopted_member', 'member'],
        }

        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.full_name,
            'role': effective_role,
            'role_display': dict(User.ROLE_CHOICES).get(effective_role, effective_role),
            'company': effective_company.name if effective_company else None,
            'company_id': effective_company.id if effective_company else None,
            'branch': effective_branch.name if effective_branch else None,
            'branch_id': effective_branch.id if effective_branch else None,
            'membership_id': membership.id if membership else None,
            'company_username': membership.company_username if membership else None,
            'permissions': {**role_flags, **capability_flags},
        })


# ============================================================
# USER DELETE / STATUS
# ============================================================

class UserDeleteView(APIView):
    permission_classes = [IsSuperAdmin]

    def delete(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response(
                {'error': 'You cannot delete your own account'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.delete()
        return Response({'success': True, 'message': 'User deleted successfully'})


class UserStatusToggleView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response(
                {'error': 'You cannot deactivate your own account'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])

        return Response({
            'success': True,
            'message': f"User {'activated' if user.is_active else 'deactivated'} successfully",
            'is_active': user.is_active,
        })