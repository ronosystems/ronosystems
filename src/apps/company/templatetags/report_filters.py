from django import template

register = template.Library()

@register.filter
def sum_attribute(items, attr):
    """
    Sum a specific attribute from a list of objects or dictionaries.
    Usage: {{ items|sum_attribute:'revenue' }}
    """
    if not items:
        return 0
    
    total = 0
    for item in items:
        if hasattr(item, attr):
            val = getattr(item, attr)
            if val is not None:
                total += val
        elif isinstance(item, dict) and attr in item:
            val = item[attr]
            if val is not None:
                total += val
    
    return total