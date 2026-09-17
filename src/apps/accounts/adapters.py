import logging
import traceback
import uuid
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter

logger = logging.getLogger(__name__)


def _generate_username(email, first_name='', last_name=''):
    """
    Build a unique username. Tries in order:
      1. The local part of the email (before @)
      2. first_name + last_name slug
      3. <base>_<4-digit suffix> until unique
      4. Fallback: uuid4 hex
    """
    User = get_user_model()

    candidates = []

    if email and '@' in email:
        candidates.append(email.split('@', 1)[0])

    if first_name or last_name:
        name = f'{first_name}_{last_name}'.strip('_')
        slug = slugify(name)
        if slug:
            candidates.append(slug)

    for base in candidates:
        base = slugify(base) or 'user'
        # Try the plain base first
        if not User.objects.filter(username__iexact=base).exists():
            return base
        # Then with numeric suffixes
        for n in range(1, 100):
            candidate = f'{base}{n}'
            if not User.objects.filter(username__iexact=candidate).exists():
                return candidate

    # Fallback — guaranteed unique
    return f'user_{uuid.uuid4().hex[:10]}'


class RonoSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Hook into allauth's social signup so we can attach
    new social users to your Company / tenant system.
    """

    def save_user(self, request, sociallogin, form=None):
        # Ensure a username is set BEFORE the parent tries to save
        user = sociallogin.user
        extra = sociallogin.account.extra_data

        if not user.email:
            user.email = extra.get('email', '')

        if not user.first_name:
            user.first_name = extra.get('given_name') or extra.get('first_name', '')
        if not user.last_name:
            user.last_name = extra.get('family_name') or extra.get('last_name', '')

        if not getattr(user, 'username', None):
            user.username = _generate_username(
                user.email or '',
                user.first_name or '',
                user.last_name or '',
            )

        # Default role for social signups
        if hasattr(user, 'role') and not user.role:
            user.role = 'guest'

        # Save the user (this triggers the UNIQUE check)
        user = super().save_user(request, sociallogin, form)

        return user

    def pre_social_login(self, request, sociallogin):
        """
        If a user with the same email already exists, connect the
        social account to that existing user instead of creating a new one.
        """
        if sociallogin.is_existing:
            return

        email = sociallogin.account.extra_data.get('email')
        if not email:
            return

        User = get_user_model()
        try:
            user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass

    # ------------------------------------------------------------------
    # DEBUG — log the real reason allauth rejected the social login
    # ------------------------------------------------------------------
    def on_authentication_error(self, request, provider_id, error=None,
                                exception=None, extra_context=None):
        logger.error('=' * 70)
        logger.error('SOCIAL LOGIN FAILED')
        logger.error('=' * 70)
        logger.error('Provider: %s', provider_id)
        logger.error('Error:    %s', error)
        logger.error('Exception type: %s', type(exception).__name__ if exception else 'None')
        logger.error('Exception msg:  %s', str(exception) if exception else 'None')
        logger.error('Extra context:  %s', extra_context)

        if exception:
            logger.error('Traceback:')
            logger.error(traceback.format_exc())

        logger.error('=' * 70)


class RonoAccountAdapter(DefaultAccountAdapter):
    """
    Send users to your own dashboard rather than allauth's default.
    """

    def get_login_redirect_url(self, request):
        return '/dashboard/'

    def get_signup_redirect_url(self, request):
        return '/dashboard/'