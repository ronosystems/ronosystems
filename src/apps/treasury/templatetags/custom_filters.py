from django import template

register = template.Library()

@register.filter(name='get')
def get_item(dictionary, key):
    """Get an item from a dictionary by key"""
    if dictionary is None:
        return None
    return dictionary.get(key, 0)

@register.filter(name='default_if_none')
def default_if_none(value, default):
    """Return default if value is None"""
    if value is None:
        return default
    return value