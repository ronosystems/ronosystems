from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()

class EmailOrPhoneBackend(ModelBackend):
    """
    Custom authentication backend that allows logging in with 
    either an Email address OR a Phone Number (stored in the username field).
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            # 👇 FIXED: Use Q(phone=...) not Q(phone_number=...)
            user = UserModel.objects.get(
                Q(username__iexact=username) | 
                Q(email__iexact=username) |
                Q(phone__iexact=username)  # <-- The User model field is 'phone'
            )
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user.
            UserModel().set_password(password)
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None