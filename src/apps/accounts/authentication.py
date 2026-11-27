# apps/accounts/authentication.py

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import Membership
from apps.companies.models import Company


class MembershipJWTAuthentication(JWTAuthentication):
    """
    Reads membership_id / company_id from the JWT (set at login/switch)
    and attaches them to the request so views can use request.membership
    and request.company without extra DB lookups.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result

        membership_id = token.get('membership_id')
        company_id = token.get('company_id')

        # Don't overwrite whatever TenantMiddleware already set
        if getattr(request, 'membership', None) is None and membership_id:
            request.membership = (
                Membership.objects
                .select_related('company', 'branch')
                .filter(pk=membership_id, user=user, is_active=True)
                .first()
            )

        if getattr(request, 'company', None) is None:
            if company_id:
                request.company = Company.objects.filter(pk=company_id).first()
            elif request.membership:
                request.company = request.membership.company

        return user, token