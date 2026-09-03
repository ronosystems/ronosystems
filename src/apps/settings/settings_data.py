"""
System Settings - File-based storage that persists between requests
"""

import json
import os
from django.conf import settings

# Default system settings
DEFAULT_SETTINGS = {
    # General Settings
    'SITE_NAME': 'RonoSystems',
    'SITE_TAGLINE': 'Enterprise Management Platform',
    'TIMEZONE': 'Africa/Nairobi',
    'DATE_FORMAT': 'Y-m-d',
    'TIME_FORMAT': 'H:i',
    
    # Branding Settings
    'SITE_LOGO': '',
    'SITE_FAVICON': '',
    'LOGIN_BACKGROUND': '',
    'PRIMARY_COLOR': '#036a77',
    'SECONDARY_COLOR': '#00b4d8',
    'SUCCESS_COLOR': '#48bb78',
    'DANGER_COLOR': '#fc8181',
    
    # Email Settings
    'EMAIL_HOST': 'smtp.gmail.com',
    'EMAIL_PORT': '587',
    'EMAIL_USERNAME': '',
    'EMAIL_PASSWORD': '',
    'EMAIL_FROM': 'noreply@ronosystems.com',
    'EMAIL_TLS': True,
    
    # Payment Settings
    'CURRENCY': 'KES',
    'CURRENCY_SYMBOL': 'KSh',
    'TAX_RATE': 0.0,
    'ENABLE_DISCOUNT': True,
    'ENABLE_TAX': False,
    
    # Language Settings
    'DEFAULT_LANGUAGE': 'en',
    'ENABLE_MULTI_LANGUAGE': False,
    'AVAILABLE_LANGUAGES': ['en', 'sw', 'fr'],
    
    # Security Settings
    'TWO_FACTOR_AUTH': False,
    'SESSION_TIMEOUT': True,
    'SESSION_TIMEOUT_MINUTES': 30,
    'CAPTCHA_ENABLED': False,
    'ALLOW_REGISTRATION': True,
    
    # Preferences
    'NOTIFICATIONS': True,
    'EMAIL_NOTIFICATIONS': True,
    'PUSH_NOTIFICATIONS': False,
    'ITEMS_PER_PAGE': 25,
}

# Path to the settings file
SETTINGS_FILE = os.path.join(settings.BASE_DIR, 'settings_data.json')

def get_settings():
    """Get settings from file or create default"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved_settings = json.load(f)
                # Merge with defaults to ensure all keys exist
                settings_dict = DEFAULT_SETTINGS.copy()
                settings_dict.update(saved_settings)
                return settings_dict
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings_dict):
    """Save settings to file"""
    try:
        # Convert boolean values to JSON serializable format
        json_data = {}
        for key, value in settings_dict.items():
            if isinstance(value, bool):
                json_data[key] = value
            elif isinstance(value, (int, float)):
                json_data[key] = value
            else:
                json_data[key] = str(value)
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(json_data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

# Category configuration
CATEGORIES = {
    'general': {
        'label': 'General',
        'icon': 'cog',
        'color': 'primary',
        'settings': [
            'SITE_NAME', 'SITE_TAGLINE', 'TIMEZONE', 'DATE_FORMAT', 'TIME_FORMAT'
        ]
    },
    'branding': {
        'label': 'Branding & Design',
        'icon': 'paint-brush',
        'color': 'info',
        'settings': [
            'SITE_LOGO', 'SITE_FAVICON', 'LOGIN_BACKGROUND',
            'PRIMARY_COLOR', 'SECONDARY_COLOR', 'SUCCESS_COLOR', 'DANGER_COLOR'
        ]
    },
    'email': {
        'label': 'Email Settings',
        'icon': 'envelope',
        'color': 'success',
        'settings': [
            'EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_USERNAME', 'EMAIL_PASSWORD',
            'EMAIL_FROM', 'EMAIL_TLS'
        ]
    },
    'payment': {
        'label': 'Payment Settings',
        'icon': 'credit-card',
        'color': 'warning',
        'settings': [
            'CURRENCY', 'CURRENCY_SYMBOL', 'TAX_RATE', 
            'ENABLE_DISCOUNT', 'ENABLE_TAX'
        ]
    },
    'language': {
        'label': 'Language Settings',
        'icon': 'language',
        'color': 'danger',
        'settings': [
            'DEFAULT_LANGUAGE', 'ENABLE_MULTI_LANGUAGE', 'AVAILABLE_LANGUAGES'
        ]
    },
    'security': {
        'label': 'Security Settings',
        'icon': 'shield-alt',
        'color': 'dark',
        'settings': [
            'TWO_FACTOR_AUTH', 'SESSION_TIMEOUT', 'SESSION_TIMEOUT_MINUTES',
            'CAPTCHA_ENABLED', 'ALLOW_REGISTRATION'
        ]
    },
    'preferences': {
        'label': 'Preferences',
        'icon': 'sliders-h',
        'color': 'info',
        'settings': [
            'NOTIFICATIONS', 'EMAIL_NOTIFICATIONS', 'PUSH_NOTIFICATIONS',
            'ITEMS_PER_PAGE'
        ]
    },
}

# Settings metadata for each setting
SETTINGS_META = {
    'SITE_NAME': {
        'label': 'Site Name',
        'type': 'text',
        'description': 'The name of your application',
        'help_text': 'This name will appear throughout the application',
        'required': True
    },
    'SITE_TAGLINE': {
        'label': 'Site Tagline',
        'type': 'text',
        'description': 'A short description of your application',
        'help_text': 'This appears in the header',
        'required': False
    },
    'TIMEZONE': {
        'label': 'Default Timezone',
        'type': 'select',
        'description': 'The default timezone for the application',
        'options': ['UTC', 'Africa/Nairobi', 'America/New_York', 'Europe/London', 'Asia/Dubai'],
        'required': True
    },
    'DATE_FORMAT': {
        'label': 'Date Format',
        'type': 'select',
        'description': 'Format for displaying dates',
        'options': ['Y-m-d', 'd/m/Y', 'm/d/Y', 'd M Y'],
        'required': True
    },
    'TIME_FORMAT': {
        'label': 'Time Format',
        'type': 'select',
        'description': 'Format for displaying time',
        'options': ['H:i', 'h:i A', 'H:i:s'],
        'required': True
    },
    'SITE_LOGO': {
        'label': 'Site Logo',
        'type': 'image',
        'description': 'Upload your logo (PNG, JPG, SVG)',
        'help_text': 'Recommended size: 200x60px',
        'required': False
    },
    'SITE_FAVICON': {
        'label': 'Favicon',
        'type': 'image',
        'description': 'Upload favicon (ICO, PNG)',
        'help_text': 'Recommended size: 32x32px or 64x64px',
        'required': False
    },
    'LOGIN_BACKGROUND': {
        'label': 'Login Background',
        'type': 'image',
        'description': 'Background image for login page',
        'help_text': 'Recommended size: 1920x1080px',
        'required': False
    },
    'PRIMARY_COLOR': {
        'label': 'Primary Color',
        'type': 'color',
        'description': 'Main brand color',
        'help_text': 'Used for buttons, headers, and primary elements',
        'required': False
    },
    'SECONDARY_COLOR': {
        'label': 'Secondary Color',
        'type': 'color',
        'description': 'Secondary brand color',
        'help_text': 'Used for highlights and secondary elements',
        'required': False
    },
    'SUCCESS_COLOR': {
        'label': 'Success Color',
        'type': 'color',
        'description': 'Color for success messages and status',
        'required': False
    },
    'DANGER_COLOR': {
        'label': 'Danger Color',
        'type': 'color',
        'description': 'Color for error messages and warnings',
        'required': False
    },
    'EMAIL_HOST': {
        'label': 'SMTP Host',
        'type': 'text',
        'description': 'SMTP server hostname',
        'required': True
    },
    'EMAIL_PORT': {
        'label': 'SMTP Port',
        'type': 'integer',
        'description': 'SMTP server port',
        'help_text': 'Common ports: 587 (TLS), 465 (SSL)',
        'required': True
    },
    'EMAIL_USERNAME': {
        'label': 'SMTP Username',
        'type': 'text',
        'description': 'Email address for SMTP authentication',
        'required': False
    },
    'EMAIL_PASSWORD': {
        'label': 'SMTP Password',
        'type': 'password',
        'description': 'Password for SMTP authentication',
        'required': False
    },
    'EMAIL_FROM': {
        'label': 'From Email',
        'type': 'email',
        'description': 'Default sender email address',
        'required': True
    },
    'EMAIL_TLS': {
        'label': 'Enable TLS',
        'type': 'boolean',
        'description': 'Enable TLS encryption for email',
        'help_text': 'Recommended for security',
        'required': False
    },
    'CURRENCY': {
        'label': 'Default Currency',
        'type': 'select',
        'description': 'Default currency for the system',
        'options': ['KES', 'USD', 'EUR', 'GBP', 'NGN', 'ZAR'],
        'required': True
    },
    'CURRENCY_SYMBOL': {
        'label': 'Currency Symbol',
        'type': 'text',
        'description': 'Symbol for the currency',
        'required': False
    },
    'TAX_RATE': {
        'label': 'Default Tax Rate',
        'type': 'float',
        'description': 'Default tax rate (%)',
        'help_text': 'Enter as decimal (e.g., 16 for 16%)',
        'required': False
    },
    'ENABLE_DISCOUNT': {
        'label': 'Enable Discounts',
        'type': 'boolean',
        'description': 'Enable discount functionality',
        'required': False
    },
    'ENABLE_TAX': {
        'label': 'Enable Tax',
        'type': 'boolean',
        'description': 'Enable tax calculations',
        'required': False
    },
    'DEFAULT_LANGUAGE': {
        'label': 'Default Language',
        'type': 'select',
        'description': 'Default language for the system',
        'options': ['en', 'sw', 'fr', 'es', 'de', 'pt'],
        'required': True
    },
    'ENABLE_MULTI_LANGUAGE': {
        'label': 'Enable Multi-language',
        'type': 'boolean',
        'description': 'Allow users to switch languages',
        'required': False
    },
    'AVAILABLE_LANGUAGES': {
        'label': 'Available Languages',
        'type': 'textarea',
        'description': 'List of available languages (one per line)',
        'help_text': 'Example: en, sw, fr',
        'required': False
    },
    'TWO_FACTOR_AUTH': {
        'label': 'Enable Two-Factor Authentication',
        'type': 'boolean',
        'description': 'Enable 2FA for all users',
        'required': False
    },
    'SESSION_TIMEOUT': {
        'label': 'Enable Session Timeout',
        'type': 'boolean',
        'description': 'Automatically timeout idle sessions',
        'required': False
    },
    'SESSION_TIMEOUT_MINUTES': {
        'label': 'Session Timeout',
        'type': 'integer',
        'description': 'Session timeout in minutes',
        'help_text': 'Only applies if Session Timeout is enabled',
        'required': False
    },
    'CAPTCHA_ENABLED': {
        'label': 'Enable CAPTCHA on Login',
        'type': 'boolean',
        'description': 'Require CAPTCHA for login attempts',
        'required': False
    },
    'ALLOW_REGISTRATION': {
        'label': 'Allow Registration',
        'type': 'boolean',
        'description': 'Allow new user registration',
        'required': False
    },
    'NOTIFICATIONS': {
        'label': 'Enable Notifications',
        'type': 'boolean',
        'description': 'Enable system notifications',
        'required': False
    },
    'EMAIL_NOTIFICATIONS': {
        'label': 'Enable Email Notifications',
        'type': 'boolean',
        'description': 'Send email notifications for important events',
        'required': False
    },
    'PUSH_NOTIFICATIONS': {
        'label': 'Enable Push Notifications',
        'type': 'boolean',
        'description': 'Enable browser push notifications',
        'required': False
    },
    'ITEMS_PER_PAGE': {
        'label': 'Items Per Page',
        'type': 'select',
        'description': 'Default number of items per page',
        'options': ['10', '25', '50', '100'],
        'required': True
    },
}