from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.contrib.auth.hashers import check_password
from apps.customers.models import Customer

UserModel = get_user_model()

class CustomerDomainBackend(ModelBackend):
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
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        # 1. Find the global user by phone/email safely
        users = UserModel.objects.filter(
            Q(username__iexact=username) | 
            Q(email__iexact=username) |
            Q(phone__iexact=username)
        )

        if not users.exists():
            UserModel().set_password(password) # Timing attack mitigation
            return None

        # 2. Check credentials and domain permissions safely
        for user in users:
            if user.check_password(password) and self.user_can_authenticate(user):
                
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
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
            
        # Using .first() instead of .get() to prevent MultipleObjectsReturned
        user = UserModel.objects.filter(
            Q(email__iexact=username) | 
            Q(username__iexact=username) | 
            Q(phone__iexact=username)
        ).first()

        if not user:
            return None

        # 1. Check password
        if not user.check_password(password):
            return None

        # 2. Check Tenant (Company) Match ONLY FOR STAFF
        if request and user.role != 'customer':
            current_company = getattr(request, 'current_company', None) or getattr(request, 'company', None)
            
            if current_company and user.company != current_company:
                if not user.is_superuser:
                    return None

        return user