from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    """
    Return 'active' if the current URL name matches any of url_names.
    Usage: {% nav_active 'home' %}  or  {% nav_active 'support' 'help' 'faq' %}
    """
    request = context.get('request')
    if not request or not request.resolver_match:
        return ''
    current = request.resolver_match.url_name
    return 'active' if current in url_names else ''