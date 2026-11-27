# apps/accounts/backends.py

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.contrib.auth.hashers import check_password

from apps.customers.models import Customer
from apps.companies.models import Company
from apps.accounts.models import Membership

UserModel = get_user_model()


# ============================================================
# HELPERS
# ============================================================
def _get_current_company(request):
    """
    Resolve the current tenant company from the request.
    Supports middleware that sets either `request.company`
    or `request.current_company`.
    """
    if not request:
        return None
    return (
        getattr(request, 'company', None)
        or getattr(request, 'current_company', None)
    )


# ============================================================
# CUSTOMER DOMAIN BACKEND
# ============================================================
class CustomerDomainBackend(ModelBackend):
    """
    Handles logins for Customers (end-users of a shop).
    They log in using Phone Number + PIN, isolated to the current company.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not request or not username or not password:
            return None

        current_company = _get_current_company(request)
        if not current_company:
            return None

        # 1. Find the customer profile ONLY within the current domain's company
        customer = Customer.objects.filter(
            company=current_company,
            phone_number=username,
        ).select_related('user').first()

        if not customer:
            return None

        # 2. Check the PIN saved specifically for THIS company in the Customer model
        if customer.pin and check_password(password, customer.pin):
            return customer.user

        return None


# ============================================================
# EMAIL / PHONE / USERNAME BACKEND (global fallback)
# ============================================================
class EmailOrPhoneBackend(ModelBackend):
    """
    Fallback backend for general authentication using email, username, or phone.
    Used primarily when logging in from the Mother Domain (localhost:8000).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        users = UserModel.objects.filter(
            Q(username__iexact=username) |
            Q(email__iexact=username) |
            Q(phone__iexact=username)
        )

        if not users.exists():
            UserModel().set_password(password)  # timing-attack mitigation
            return None

        for user in users:
            if not user.check_password(password):
                continue
            if not self.user_can_authenticate(user):
                continue

            # If they are a customer, ensure they belong to the current company
            if user.role == 'customer' and request:
                current_company = _get_current_company(request)
                if not current_company:
                    return None

                is_customer_here = Customer.objects.filter(
                    user=user, company=current_company,
                ).exists()
                if not is_customer_here:
                    return None

            return user

        return None


# ============================================================
# MEMBERSHIP BACKEND  (THE FIX — per-company login)
# ============================================================
class MembershipBackend(ModelBackend):
    """
    Company-profile login: company_username + per-company password.

    Login identifier can be:
      - company_username  (e.g. FEK74039837)
      - user.email
      - user.phone

    Password is checked against Membership.password first.
    Falls back to User.password for super_admin / legacy logins.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        # ---------- 1) Try membership-level login ----------
        membership_qs = (
            Membership.objects
            .select_related('user', 'company', 'branch')
            .filter(is_active=True)
            .filter(
                Q(company_username__iexact=username) |
                Q(user__email__iexact=username) |
                Q(user__phone__iexact=username)
            )
        )

        # If we are on a tenant domain, prefer the membership for THAT company
        current_company = _get_current_company(request)
        if current_company:
            membership_qs = membership_qs.filter(company=current_company)

        for membership in membership_qs:
            if not membership.check_password(password):
                continue

            user = membership.user
            if not self.user_can_authenticate(user):
                continue

            # Attach the matched membership to the user instance so views/
            # session code can read it without another query.
            user.active_membership = membership
            return user

        # ---------- 2) Fallback: global User password ----------
        user = (
            UserModel.objects
            .filter(
                Q(email__iexact=username) |
                Q(username__iexact=username) |
                Q(phone__iexact=username)
            )
            .first()
        )
        if not user:
            UserModel().set_password(password)  # timing-attack mitigation
            return None

        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None

        # Super admins bypass company checks
        if user.is_superuser or user.role == 'super_admin':
            user.active_membership = None
            return user

        # On a tenant domain, verify the user belongs to that company
        if current_company:
            has_membership = Membership.objects.filter(
                user=user, company=current_company, is_active=True,
            ).exists()
            if not has_membership and user.company != current_company:
                return None

        user.active_membership = user.get_primary_membership()
        return user


# ============================================================
# TENANT BACKEND (kept for backward compat / chama logins)
# ============================================================
class TenantAuthBackend(ModelBackend):
    """
    Legacy email-based tenant login. Prefer MembershipBackend for company
    profiles. Kept so existing User-row logins keep working.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        user = UserModel.objects.filter(
            Q(email__iexact=username) |
            Q(username__iexact=username) |
            Q(phone__iexact=username)
        ).first()

        if not user:
            return None

        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None

        # Super admins bypass all company checks
        if user.is_superuser or user.role == 'super_admin':
            return user

        current_company = _get_current_company(request)
        if current_company:
            is_member = Membership.objects.filter(
                user=user, company=current_company, is_active=True,
            ).exists()
            if not is_member and user.company != current_company:
                return None

        return user