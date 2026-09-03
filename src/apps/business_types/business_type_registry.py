"""
Business Type Registry - Centralized definition of all business types
This ensures consistent naming and proper integration mapping
"""

from django.db import models
from enum import Enum

class BusinessTypeEnum(Enum):
    """Official Business Types with their exact spelling and integrations"""
    
    EPA_SHOP = {
        'id': 1,
        'name': 'EPA Shop',
        'slug': 'epa-shop',
        'description': 'Electronics, Phones and Accessories Shop',
        'icon': 'fa-store',
        'app': 'apps.epa_shop',
        'is_active': True,
        'integration': {
            'module': 'epa_shop',
            'models': ['Category', 'Electronic', 'Phone', 'Accessory', 'Sale', 'SaleItem', 'Customer'],
            'dashboard': 'EPADashboardView'
        }
    }
    
    HEALTHCARE = {
        'id': 2,
        'name': 'Healthcare',
        'slug': 'healthcare',
        'description': 'Healthcare and Medical Services',
        'icon': 'fa-heartbeat',
        'app': 'apps.healthcare',
        'is_active': True,
        'integration': {
            'module': 'healthcare',
            'models': ['Patient', 'Appointment', 'MedicalRecord', 'Prescription'],
            'dashboard': 'HealthcareDashboardView'
        }
    }
    
    EDUCATION = {
        'id': 3,
        'name': 'Education',
        'slug': 'education',
        'description': 'Educational Institutions and Training',
        'icon': 'fa-graduation-cap',
        'app': 'apps.education',
        'is_active': True,
        'integration': {
            'module': 'education',
            'models': ['Student', 'Course', 'Enrollment', 'Grade'],
            'dashboard': 'EducationDashboardView'
        }
    }
    
    RETAIL = {
        'id': 4,
        'name': 'Retail',
        'slug': 'retail',
        'description': 'Retail Stores and Shops',
        'icon': 'fa-shopping-cart',
        'app': 'apps.retail',
        'is_active': True,
        'integration': {
            'module': 'retail',
            'models': ['Product', 'Category', 'Sale', 'SaleItem'],
            'dashboard': 'RetailDashboardView'
        }
    }
    
    RESTAURANT = {
        'id': 5,
        'name': 'Restaurant',
        'slug': 'restaurant',
        'description': 'Restaurants and Food Services',
        'icon': 'fa-utensils',
        'app': 'apps.restaurant',
        'is_active': True,
        'integration': {
            'module': 'restaurant',
            'models': ['Menu', 'Order', 'OrderItem', 'Table'],
            'dashboard': 'RestaurantDashboardView'
        }
    }
    
    SUPERMARKET = {
        'id': 6,
        'name': 'Supermarket',
        'slug': 'supermarket',
        'description': 'Supermarket and Grocery Store',
        'icon': 'fa-shopping-basket',
        'app': 'apps.supermarket',
        'is_active': True,
        'integration': {
            'module': 'supermarket',
            'models': [
                'Category',           # Product categories (Dairy, Meat, Produce, etc.)
                'Product',            # Individual products with barcodes
                'Inventory',          # Stock management
                'Supplier',           # Product suppliers
                'PurchaseOrder',      # Orders from suppliers
                'PurchaseOrderItem',  # Items in purchase orders
                'Sale',               # Customer sales
                'SaleItem',           # Items in sales
                'Customer',           # Customer profiles
                'PriceHistory',       # Price change tracking
                'Discount',           # Promotions and discounts
                'ShelfLocation'       # Store shelf/aisle locations
            ],
            'dashboard': 'SupermarketDashboardView'
        }
    }
    
    @classmethod
    def get_by_name(cls, name):
        """Get business type by exact name"""
        for member in cls:
            if member.value['name'].lower() == name.lower():
                return member
        return None
    
    @classmethod
    def get_by_id(cls, type_id):
        """Get business type by ID"""
        for member in cls:
            if member.value['id'] == type_id:
                return member
        return None
    
    @classmethod
    def get_by_slug(cls, slug):
        """Get business type by slug"""
        for member in cls:
            if member.value['slug'] == slug:
                return member
        return None
    
    @classmethod
    def get_all_active(cls):
        """Get all active business types"""
        return [member.value for member in cls if member.value['is_active']]
    
    @classmethod
    def get_all_names(cls):
        """Get all business type names (for validation)"""
        return [member.value['name'] for member in cls if member.value['is_active']]
    
    @classmethod
    def validate_name(cls, name):
        """Validate if a business type name exists"""
        return name in cls.get_all_names()
    
    @classmethod
    def get_integration(cls, name):
        """Get integration details for a business type"""
        business_type = cls.get_by_name(name)
        if business_type:
            return business_type.value.get('integration')
        return None

# ============================================
# Business Type Constants (For use in models)
# ============================================

BUSINESS_TYPE_CHOICES = [
    (type_enum.value['name'], type_enum.value['name'])
    for type_enum in BusinessTypeEnum
    if type_enum.value['is_active']
]

BUSINESS_TYPE_SLUGS = {
    type_enum.value['name']: type_enum.value['slug']
    for type_enum in BusinessTypeEnum
    if type_enum.value['is_active']
}

BUSINESS_TYPE_APPS = {
    type_enum.value['name']: type_enum.value['app']
    for type_enum in BusinessTypeEnum
    if type_enum.value['is_active']
}

BUSINESS_TYPE_INTEGRATIONS = {
    type_enum.value['name']: type_enum.value['integration']
    for type_enum in BusinessTypeEnum
    if type_enum.value['is_active']
}
