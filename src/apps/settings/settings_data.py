import os
import json
from django.conf import settings

# Default settings
DEFAULT_SETTINGS = {
    # General
    'SITE_NAME': 'RonoSystems',
    'SITE_TAGLINE': 'Enterprise Management Platform',
    'TIMEZONE': 'Africa/Nairobi',
    'DATE_FORMAT': 'Y-m-d',
    'ITEMS_PER_PAGE': 25,
    
    # Branding
    'PRIMARY_COLOR': '#036a77',
    'SECONDARY_COLOR': '#00b4d8',
    'SITE_LOGO': '',
    'SITE_FAVICON': '',
    'LOGIN_BACKGROUND': '',
    
    # Email
    'EMAIL_HOST': 'smtp.gmail.com',
    'EMAIL_PORT': 587,
    'EMAIL_USERNAME': '',
    'EMAIL_PASSWORD': '',
    'EMAIL_FROM': 'noreply@example.com',
    'EMAIL_TLS': True,
    
    # Payment
    'CURRENCY': 'KES',
    'CURRENCY_SYMBOL': 'KSh',
    'TAX_RATE': 0,
    'ENABLE_DISCOUNT': True,
    'ENABLE_TAX': False,
    
    # Preferences
    'NOTIFICATIONS': True,
    'EMAIL_NOTIFICATIONS': True,
    'PUSH_NOTIFICATIONS': False,
}

# Settings metadata
SETTINGS_META = {
    'SITE_NAME': {
        'label': 'Site Name',
        'type': 'text',
        'category': 'general',
        'required': True,
        'description': 'The name of your site',
    },
    'SITE_TAGLINE': {
        'label': 'Tagline',
        'type': 'text',
        'category': 'general',
        'description': 'A short tagline for your site',
    },
    'TIMEZONE': {
        'label': 'Timezone',
        'type': 'select',
        'category': 'general',
        'options': [
            {'value': 'UTC', 'label': 'UTC'},
            {'value': 'Africa/Nairobi', 'label': 'Africa/Nairobi'},
            {'value': 'America/New_York', 'label': 'America/New_York'},
            {'value': 'Europe/London', 'label': 'Europe/London'},
            {'value': 'Asia/Dubai', 'label': 'Asia/Dubai'},
        ],
    },
    'DATE_FORMAT': {
        'label': 'Date Format',
        'type': 'select',
        'category': 'general',
        'options': [
            {'value': 'Y-m-d', 'label': 'YYYY-MM-DD'},
            {'value': 'd/m/Y', 'label': 'DD/MM/YYYY'},
            {'value': 'm/d/Y', 'label': 'MM/DD/YYYY'},
            {'value': 'd M Y', 'label': 'DD Mon YYYY'},
        ],
    },
    'ITEMS_PER_PAGE': {
        'label': 'Items Per Page',
        'type': 'select',
        'category': 'general',
        'options': [
            {'value': '10', 'label': '10'},
            {'value': '25', 'label': '25'},
            {'value': '50', 'label': '50'},
            {'value': '100', 'label': '100'},
        ],
    },
    'PRIMARY_COLOR': {
        'label': 'Primary Color',
        'type': 'color',
        'category': 'branding',
        'description': 'Main brand color',
    },
    'SECONDARY_COLOR': {
        'label': 'Secondary Color',
        'type': 'color',
        'category': 'branding',
        'description': 'Secondary brand color',
    },
    'SITE_LOGO': {
        'label': 'Site Logo',
        'type': 'image',
        'category': 'branding',
        'description': 'Upload your site logo',
        'help_text': 'Recommended size: 200x60px',
    },
    'SITE_FAVICON': {
        'label': 'Favicon',
        'type': 'image',
        'category': 'branding',
        'description': 'Upload your favicon',
        'help_text': 'Recommended size: 32x32px',
    },
    'LOGIN_BACKGROUND': {
        'label': 'Login Background',
        'type': 'image',
        'category': 'branding',
        'description': 'Login page background image',
        'help_text': 'Recommended size: 1920x1080px',
    },
    'EMAIL_HOST': {
        'label': 'SMTP Host',
        'type': 'text',
        'category': 'email',
        'help_text': 'e.g., smtp.gmail.com',
    },
    'EMAIL_PORT': {
        'label': 'SMTP Port',
        'type': 'integer',
        'category': 'email',
        'help_text': 'e.g., 587',
    },
    'EMAIL_USERNAME': {
        'label': 'SMTP Username',
        'type': 'text',
        'category': 'email',
    },
    'EMAIL_PASSWORD': {
        'label': 'SMTP Password',
        'type': 'password',
        'category': 'email',
    },
    'EMAIL_FROM': {
        'label': 'From Email',
        'type': 'email',
        'category': 'email',
        'help_text': 'Email address used for sending emails',
    },
    'EMAIL_TLS': {
        'label': 'Enable TLS',
        'type': 'boolean',
        'category': 'email',
        'description': 'Use TLS for email connections',
    },
    'CURRENCY': {
        'label': 'Default Currency',
        'type': 'select',
        'category': 'payment',
        'options': [
            {'value': 'KES', 'label': 'Kenyan Shilling (KES)'},
            {'value': 'USD', 'label': 'US Dollar (USD)'},
            {'value': 'EUR', 'label': 'Euro (EUR)'},
            {'value': 'GBP', 'label': 'British Pound (GBP)'},
        ],
    },
    'CURRENCY_SYMBOL': {
        'label': 'Currency Symbol',
        'type': 'text',
        'category': 'payment',
        'help_text': 'Symbol for the currency (e.g., KSh, $, €)',
    },
    'TAX_RATE': {
        'label': 'Tax Rate (%)',
        'type': 'float',
        'category': 'payment',
        'help_text': 'Default tax rate percentage',
    },
    'ENABLE_DISCOUNT': {
        'label': 'Enable Discounts',
        'type': 'boolean',
        'category': 'payment',
        'description': 'Allow discounts on sales',
    },
    'ENABLE_TAX': {
        'label': 'Enable Tax',
        'type': 'boolean',
        'category': 'payment',
        'description': 'Enable tax calculation',
    },
    'NOTIFICATIONS': {
        'label': 'Notifications',
        'type': 'boolean',
        'category': 'preferences',
        'description': 'Enable system notifications',
    },
    'EMAIL_NOTIFICATIONS': {
        'label': 'Email Notifications',
        'type': 'boolean',
        'category': 'preferences',
        'description': 'Send notifications via email',
    },
    'PUSH_NOTIFICATIONS': {
        'label': 'Push Notifications',
        'type': 'boolean',
        'category': 'preferences',
        'description': 'Send push notifications',
    },
}

# Categories with their settings
CATEGORIES = {
    'general': {
        'label': 'General',
        'icon': 'fas fa-cog',
        'color': '#6c757d',
        'settings': ['SITE_NAME', 'SITE_TAGLINE', 'TIMEZONE', 'DATE_FORMAT', 'ITEMS_PER_PAGE']
    },
    'branding': {
        'label': 'Branding & Design',
        'icon': 'fas fa-paint-brush',
        'color': '#6f42c1',
        'settings': ['PRIMARY_COLOR', 'SECONDARY_COLOR', 'SITE_LOGO', 'SITE_FAVICON', 'LOGIN_BACKGROUND']
    },
    'email': {
        'label': 'Email Settings',
        'icon': 'fas fa-envelope',
        'color': '#0d6efd',
        'settings': ['EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_USERNAME', 'EMAIL_PASSWORD', 'EMAIL_FROM', 'EMAIL_TLS']
    },
    'payment': {
        'label': 'Payment Settings',
        'icon': 'fas fa-credit-card',
        'color': '#198754',
        'settings': ['CURRENCY', 'CURRENCY_SYMBOL', 'TAX_RATE', 'ENABLE_DISCOUNT', 'ENABLE_TAX']
    },
    'preferences': {
        'label': 'Preferences',
        'icon': 'fas fa-sliders-h',
        'color': '#ffc107',
        'settings': ['NOTIFICATIONS', 'EMAIL_NOTIFICATIONS', 'PUSH_NOTIFICATIONS']
    },
}

# Settings file path
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')


def get_settings():
    """Get current settings from database or JSON file"""
    try:
        # Try to get from database
        from .models import SystemSetting
        settings_dict = {}
        for setting in SystemSetting.objects.all():
            settings_dict[setting.key] = setting.get_value()
        
        # Merge with defaults for missing keys
        for key, default_value in DEFAULT_SETTINGS.items():
            if key not in settings_dict:
                settings_dict[key] = default_value
        
        return settings_dict
        
    except Exception as e:
        print(f"Error loading settings from database: {e}")
        # Fallback to JSON file
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    file_settings = json.load(f)
                    # Merge with defaults
                    for key, default_value in DEFAULT_SETTINGS.items():
                        if key not in file_settings:
                            file_settings[key] = default_value
                    return file_settings
        except Exception:
            pass
        return DEFAULT_SETTINGS.copy()


def save_settings(settings_dict):
    """Save settings to database"""
    try:
        from .models import SystemSetting
        
        for key, value in settings_dict.items():
            # Get or create the setting
            setting, created = SystemSetting.objects.get_or_create(key=key)
            
            # Determine the setting type
            setting_type = SETTINGS_META.get(key, {}).get('type', 'text')
            
            # For boolean, convert to string for storage
            if setting_type == 'boolean':
                value = str(value).lower()
            elif isinstance(value, (int, float)):
                value = str(value)
            
            setting.value = value
            setting.setting_type = setting_type
            setting.label = SETTINGS_META.get(key, {}).get('label', key.replace('_', ' ').title())
            setting.category = SETTINGS_META.get(key, {}).get('category', 'general')
            setting.save()
        
        # Also save to JSON file as backup
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_dict, f, indent=2)
        
        return True
        
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False