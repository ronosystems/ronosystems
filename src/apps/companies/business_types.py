"""
Business Type Registry - Centralized definition of all business types
This ensures consistent naming and proper integration mapping.

Rule:
- is_active=True  = app + models + dashboard actually exist in the project
- is_active=False = planned for future, do NOT load in dashboard / menus
"""

from enum import Enum

class BusinessTypeEnum(Enum):
    """Official Business Types with their exact spelling and integrations"""

    # ============================================================
    # ACTIVE - These 4 actually exist. Safe to use everywhere.
    # ============================================================

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
            'models': [
                'Category', 'Phone', 'Electronic', 'Accessory',
                'Unit', 'Sale', 'SaleItem', 'PurchaseOrder',
                'PurchaseRecord', 'StockMovement', 'StockTransfer',
                'Repair', 'Warranty', 'Owner', 'Supplier',
                'BranchStock', 'Customer',
            ],
            'dashboard': 'EPADashboardView',
            'dashboard_url_name': 'epa_shop:api_dashboard',
            'web_dashboard_url_name': 'epa_shop:web-dashboard',
        },
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
                'Category', 'Product', 'Inventory', 'Supplier',
                'PurchaseOrder', 'PurchaseOrderItem', 'Sale',
                'SaleItem', 'Customer', 'PriceHistory',
                'Discount', 'ShelfLocation',
            ],
            'dashboard': 'SupermarketDashboardView',
            'dashboard_url_name': 'supermarket:supermarket-dashboard',
            'web_dashboard_url_name': 'supermarket:supermarket-dashboard',
        },
    }

    KUKU_BIZ = {
        'id': 7,
        'name': 'Kuku Biz',
        'slug': 'kuku-biz',
        'description': 'Poultry Farming - Layer Hens and Egg Production',
        'icon': 'fa-drumstick-bite',
        'app': 'apps.kuku_biz',
        'is_active': True,
        'integration': {
            'module': 'kuku_biz',
            'models': [
                'Flock',
                'EggProduction',
                'EggSale',
                'EggSaleItem',
                'Customer',
                'FeedType',
                'FeedRecord',
                'FeedConsumption',
                'HealthRecord',
                'Mortality',
                'Expense',
                'InventoryItem',  # NOT Inventory - real model name
                'PriceHistory',
                'BirdSale',
                'VaccineType',
                # NOTE: No 'Hen' model yet - Flock is the batch model.
                # Add 'Hen' here only after you create apps/kuku_biz/models.py -> Hen
            ],
            'dashboard': 'KukuBizDashboardView',
            'dashboard_url_name': 'kuku_biz:dashboard',
            'web_dashboard_url_name': 'kuku_biz:dashboard',
        },
    }

    CHAMA = {
        'id': 8,
        'name': 'Chama',
        'slug': 'chama',
        'description': 'Chama / Savings Group / SACCO - savings, loans, meetings, welfare',
        'icon': 'fa-hand-holding-usd',
        'app': 'apps.chama',
        'is_active': True,
        'integration': {
            'module': 'chama',
            'models': [
                'MembershipType',
                'Member',
                'Registration',
                'Savings',
                'Contribution',
                'Fine',
                'LoanType',
                'Loan',
                'LoanRepayment',
                'Account',
                'Transaction',
                'Expense',
                'Meeting',
                'Attendance',
                'Committee',
                'CommitteeMember',
                'Announcement',
                'Guest',
                'Project',
            ],
            'dashboard': 'ChamaDashboardView',
            'dashboard_url_name': 'chama:dashboard',
            'web_dashboard_url_name': 'chama:dashboard',
        },
    }

    # ============================================================
    # INACTIVE / PLANNED - Do NOT use until app is built.
    # get_all_active() will skip these automatically.
    # ============================================================

    HEALTHCARE = {
        'id': 2,
        'name': 'Healthcare',
        'slug': 'healthcare',
        'description': 'Healthcare and Medical Services',
        'icon': 'fa-heartbeat',
        'app': 'apps.healthcare',  # DOES NOT EXIST YET
        'is_active': False,
        'integration': {
            'module': 'healthcare',
            'models': ['Patient', 'Appointment', 'MedicalRecord', 'Prescription'],
            'dashboard': 'HealthcareDashboardView',
            'dashboard_url_name': None,
            'web_dashboard_url_name': None,
        },
    }

    EDUCATION = {
        'id': 3,
        'name': 'Education',
        'slug': 'education',
        'description': 'Educational Institutions and Training',
        'icon': 'fa-graduation-cap',
        'app': 'apps.education',  # DOES NOT EXIST YET
        'is_active': False,
        'integration': {
            'module': 'education',
            'models': ['Student', 'Course', 'Enrollment', 'Grade'],
            'dashboard': 'EducationDashboardView',
            'dashboard_url_name': None,
            'web_dashboard_url_name': None,
        },
    }

    RETAIL = {
        'id': 4,
        'name': 'Retail',
        'slug': 'retail',
        'description': 'Retail Stores and Shops',
        'icon': 'fa-shopping-cart',
        'app': 'apps.retail',  # DOES NOT EXIST YET
        'is_active': False,
        'integration': {
            'module': 'retail',
            'models': ['Product', 'Category', 'Sale', 'SaleItem'],
            'dashboard': 'RetailDashboardView',
            'dashboard_url_name': None,
            'web_dashboard_url_name': None,
        },
    }

    RESTAURANT = {
        'id': 5,
        'name': 'Restaurant',
        'slug': 'restaurant',
        'description': 'Restaurants and Food Services',
        'icon': 'fa-utensils',
        'app': 'apps.restaurant',  # DOES NOT EXIST YET
        'is_active': False,
        'integration': {
            'module': 'restaurant',
            'models': ['Menu', 'Order', 'OrderItem', 'Table'],
            'dashboard': 'RestaurantDashboardView',
            'dashboard_url_name': None,
            'web_dashboard_url_name': None,
        },
    }

    # ============================================================
    # Helpers - keep these, don't change the API
    # ============================================================

    @classmethod
    def get_by_name(cls, name):
        """Get business type by exact name (case-insensitive)"""
        if not name:
            return None
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
        if not slug:
            return None
        for member in cls:
            if member.value['slug'] == slug:
                return member
        return None

    @classmethod
    def get_all_active(cls):
        """Get all ACTIVE business types only - safe for dashboard/menus"""
        return [member.value for member in cls if member.value['is_active']]

    @classmethod
    def get_all_names(cls):
        """Get all ACTIVE business type names (for validation)"""
        return [member.value['name'] for member in cls if member.value['is_active']]

    @classmethod
    def validate_name(cls, name):
        """Validate if a business type name exists AND is active"""
        return name in cls.get_all_names()

    @classmethod
    def get_integration(cls, name):
        """Get integration details for a business type"""
        business_type = cls.get_by_name(name)
        if business_type:
            return business_type.value.get('integration')
        return None

    @classmethod
    def get_active_slugs(cls):
        """Get slugs of active types only"""
        return [m.value['slug'] for m in cls if m.value['is_active']]

# ============================================
# Business Type Constants (For use in models)
# ============================================

BUSINESS_TYPE_CHOICES = [
    (m.value['name'], m.value['name'])
    for m in BusinessTypeEnum
    if m.value['is_active']
]

BUSINESS_TYPE_SLUGS = {
    m.value['name']: m.value['slug']
    for m in BusinessTypeEnum
    if m.value['is_active']
}

BUSINESS_TYPE_APPS = {
    m.value['name']: m.value['app']
    for m in BusinessTypeEnum
    if m.value['is_active']
}

BUSINESS_TYPE_INTEGRATIONS = {
    m.value['name']: m.value['integration']
    for m in BusinessTypeEnum
    if m.value['is_active']
}