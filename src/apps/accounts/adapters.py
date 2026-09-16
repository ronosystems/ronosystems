from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter


class RonoSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Hook into allauth's social signup so we can attach
    new social users to your Company / tenant system.
    """

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        # Pull first/last name from provider if we got them
        extra = sociallogin.account.extra_data
        if not user.first_name:
            user.first_name = extra.get('given_name') or extra.get('first_name', '')
        if not user.last_name:
            user.last_name = extra.get('family_name') or extra.get('last_name', '')
        user.save(update_fields=['first_name', 'last_name'])

        # ⬇️ Add your own company-assignment logic here
        # e.g. attach to a default company, send a welcome email, etc.

        return user

    def pre_social_login(self, request, sociallogin):
        """
        If a user with the same email already exists, connect the
        social account to that existing user instead of creating a new one.
        """
        if sociallogin.is_existing:
            return

        email = sociallogin.account.extra_data.get('email')
        if email:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(email__iexact=email)
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass


class RonoAccountAdapter(DefaultAccountAdapter):
    """
    Send users to your own dashboard rather than allauth's default.
    """

    def get_login_redirect_url(self, request):
        return '/dashboard/'

    def get_signup_redirect_url(self, request):
        return '/dashboard/'