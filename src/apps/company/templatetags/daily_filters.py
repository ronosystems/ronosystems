from django import template
from decimal import Decimal

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return Decimal('0.00')
    # Convert key to string since JSON keys are strings
    key_str = str(key)
    value = dictionary.get(key_str)
    if value is None:
        return Decimal('0.00')
    return value

@register.filter(name='default_balance')
def default_balance(value, default):
    """Return value if it has a valid balance, otherwise return default"""
    if value is None or value == '':
        return default
    return value