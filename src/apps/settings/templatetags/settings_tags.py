from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key] — safe for missing keys."""
    if not dictionary:
        return ''
    try:
        return dictionary.get(key, key)
    except AttributeError:
        return key