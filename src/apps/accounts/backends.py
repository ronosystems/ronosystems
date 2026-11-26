# apps/accounts/backends.py

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.contrib.auth.hashers import check_password
from apps.customers.models import Customer
from apps.companies.models import Company
from apps.accounts.models import  Membership

UserModel = get_user_model()


class CustomerDomainBackend(ModelBackend):
    """
    Handles logins for Customers (e.g., end-users of a shop).
    They log in using their Phone Number + PIN, and are isolated to the current company.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not request or not username or not password:
            return None

        current_company = getattr(request, 'company', None) or getattr(request, 'current_company', None)
        if not current_company:
            return None

        # 1. Find the customer profile ONLY within the current domain's company
        customer = Customer.objects.filter(
            company=current_company, 
            phone_number=username
        ).first() 

        if not customer:
            return None

        # 2. Check the PIN saved specifically for THIS company in the Customer model
        if customer.pin and check_password(password, customer.pin):
            return customer.user # Return the linked User to log them in
            
        return None


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

        # 1. Find the global user by phone/email/username safely
        users = UserModel.objects.filter(
            Q(username__iexact=username) | 
            Q(email__iexact=username) |
            Q(phone__iexact=username)
        )

        if not users.exists():
            UserModel().set_password(password) # Timing attack mitigation
            return None

        # 2. Check credentials
        for user in users:
            if user.check_password(password) and self.user_can_authenticate(user):
                
                # If they are a customer, ensure they belong to the current company
                if user.role == 'customer' and request:
                    current_company = getattr(request, 'company', None) or getattr(request, 'current_company', None)
                    
                    if not current_company:
                        return None
                        
                    is_customer_here = Customer.objects.filter(
                        user=user, 
                        company=current_company
                    ).exists()
                    
                    if not is_customer_here:
                        return None 
                        
                return user

        return None


class TenantAuthBackend(ModelBackend):
    """
    The Main Enterprise Backend.
    Jane can log in with her EMAIL. The system checks her Memberships against the Domain.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
            
        # 1. Find the user by Email, Username, or Phone
        user = UserModel.objects.filter(
            Q(email__iexact=username) | 
            Q(username__iexact=username) | 
            Q(phone__iexact=username)
        ).first()

        if not user:
            return None

        # 2. Check password
        if not user.check_password(password):
            return None

        # 3. Super Admins bypass all company checks
        if user.is_superuser or user.role == 'super_admin':
            return user

        # 4. THE BRIDGE: Check Tenant (Company) Match
        if request:
            current_company = getattr(request, 'current_company', None) or getattr(request, 'company', None)
            
            if current_company:
                # User is logging into a specific company domain (e.g., kalwal.localhost)
                # Check if they have an active Membership for THIS company
                is_member = Membership.objects.filter(
                    user=user, 
                    company=current_company, 
                    is_active=True
                ).exists()
                
                # Also check if their global company matches (for backward compatibility)
                if not is_member and user.company != current_company:
                    return None
            else:
                # User is logging into the Mother Domain (localhost:8000)
                # We allow them to pass, the view will handle redirecting them 
                # to the /select-company/ page.
                pass

        return user