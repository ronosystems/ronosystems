"""
Business Type Manager - Handles all business type operations
Ensures consistency and provides integration helpers
"""

from django.core.exceptions import ValidationError
from apps.companies.models import BusinessType
from apps.business_types.business_type_registry import BusinessTypeEnum

class BusinessTypeManager:
    """Manager for handling business type operations"""
    
    @staticmethod
    def create_business_type(name, description='', icon=''):
        """
        Create a business type with validation
        Only creates if the name exists in the registry
        """
        # Validate name
        if not BusinessTypeEnum.validate_name(name):
            valid_names = ', '.join(BusinessTypeEnum.get_all_names())
            raise ValidationError(
                f"'{name}' is not a valid business type. Valid types: {valid_names}"
            )
        
        # Check if already exists
        if BusinessType.objects.filter(name=name).exists():
            raise ValidationError(f"Business type '{name}' already exists")
        
        # Get registry data
        business_type_data = BusinessTypeEnum.get_by_name(name)
        if not business_type_data:
            raise ValidationError(f"Could not find registry data for '{name}'")
        
        # Create the business type
        return BusinessType.objects.create(
            name=name,
            description=description or business_type_data.value.get('description', ''),
            icon=icon or business_type_data.value.get('icon', ''),
            is_active=True
        )
    
    @staticmethod
    def get_or_create_business_type(name, description='', icon=''):
        """
        Get or create a business type
        Useful for seeding the database
        """
        try:
            return BusinessType.objects.get(name=name)
        except BusinessType.DoesNotExist:
            return BusinessTypeManager.create_business_type(name, description, icon)
    
    @staticmethod
    def get_integration_for_business_type(business_type_name):
        """
        Get the integration details for a business type
        Returns None if not found
        """
        return BusinessTypeEnum.get_integration(business_type_name)
    
    @staticmethod
    def get_all_available_business_types():
        """
        Get all available business types from the registry
        """
        return BusinessTypeEnum.get_all_active()
    
    @staticmethod
    def validate_company_business_type(company):
        """
        Validate that a company has a valid business type
        """
        if not company.business_type:
            raise ValidationError("Company must have a business type")
        
        if not BusinessTypeEnum.validate_name(company.business_type.name):
            raise ValidationError(
                f"Invalid business type: {company.business_type.name}"
            )
        
        return True
    
    @staticmethod
    def initialize_default_business_types():
        """
        Initialize all default business types in the database
        """
        created = []
        for business_type in BusinessTypeEnum.get_all_active():
            try:
                bt = BusinessTypeManager.get_or_create_business_type(
                    name=business_type['name'],
                    description=business_type.get('description', ''),
                    icon=business_type.get('icon', '')
                )
                created.append(bt)
            except Exception as e:
                print(f"Error creating {business_type['name']}: {e}")
        
        return created

# ============================================
# Business Type Middleware (Optional)
# ============================================

class BusinessTypeMiddleware:
    """
    Middleware to ensure business type consistency
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # You can add business type validation here
        response = self.get_response(request)
        return response
