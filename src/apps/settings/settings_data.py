import os
import json

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

DEFAULT_SETTINGS = {
    'system_name': 'RonoSystems',
    'company_name': 'RonoSystems',
    'site_logo': '',
    'timezone': 'Africa/Nairobi',
    'currency': 'KES',
    'currency_symbol': 'KSh',
    'receipt_footer': 'Thank you for your business!',
    'tax_rate': '16.00',
    'tax_enabled': True,
    'discount_enabled': True,
    'loyalty_points_enabled': True,
    'points_per_purchase': 1,
    'points_per_currency': 1,
}

CATEGORIES = {
    'general': {'label': 'General', 'icon': 'fas fa-cog', 'color': '#6c757d', 'settings': ['system_name', 'company_name', 'site_logo', 'timezone', 'currency', 'currency_symbol']},
    'receipt': {'label': 'Receipt', 'icon': 'fas fa-receipt', 'color': '#17a2b8', 'settings': ['receipt_footer']},
    'tax': {'label': 'Tax', 'icon': 'fas fa-percent', 'color': '#28a745', 'settings': ['tax_rate', 'tax_enabled']},
    'discount': {'label': 'Discount', 'icon': 'fas fa-tags', 'color': '#fd7e14', 'settings': ['discount_enabled']},
    'loyalty': {'label': 'Loyalty', 'icon': 'fas fa-star', 'color': '#ffc107', 'settings': ['loyalty_points_enabled', 'points_per_purchase', 'points_per_currency']},
    'email': {'label': 'Email', 'icon': 'fas fa-envelope', 'color': '#007bff', 'settings': ['email_host', 'email_port', 'email_username', 'email_password', 'email_from', 'email_tls']}
}

SETTINGS_META = {
    'system_name': {'label': 'System Name', 'type': 'text', 'description': 'The name of your system', 'required': True},
    'company_name': {'label': 'Company Name', 'type': 'text', 'description': 'Your company name', 'required': True},
    'site_logo': {'label': 'Site Logo', 'type': 'image', 'description': 'Upload your company logo', 'required': False},
    'timezone': {'label': 'Timezone', 'type': 'select', 'description': 'System timezone', 'options': ['UTC', 'Africa/Nairobi', 'Africa/Johannesburg'], 'required': True},
    'currency': {'label': 'Currency', 'type': 'select', 'description': 'Default currency', 'options': ['KES', 'USD', 'EUR', 'GBP', 'ZAR'], 'required': True},
    'currency_symbol': {'label': 'Currency Symbol', 'type': 'text', 'description': 'Symbol for the currency', 'required': True},
    'receipt_footer': {'label': 'Receipt Footer', 'type': 'text', 'description': 'Text to show at the bottom of receipts'},
    'tax_rate': {'label': 'Tax Rate (%)', 'type': 'float', 'description': 'Default tax rate as percentage', 'required': True},
    'tax_enabled': {'label': 'Tax Enabled', 'type': 'boolean', 'description': 'Enable tax calculation'},
    'discount_enabled': {'label': 'Discount Enabled', 'type': 'boolean', 'description': 'Enable discount functionality'},
    'loyalty_points_enabled': {'label': 'Loyalty Points Enabled', 'type': 'boolean', 'description': 'Enable loyalty points system'},
    'points_per_purchase': {'label': 'Points per Purchase', 'type': 'integer', 'description': 'Points earned per purchase'},
    'points_per_currency': {'label': 'Points per Currency', 'type': 'integer', 'description': 'Points earned per currency unit'}
}

def get_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings_dict):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings_dict, f, indent=2)
