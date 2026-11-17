from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    """
    Return 'active' if the current URL name matches any of url_names.
    
    Supports BOTH:
      - Plain url names:        {% nav_active 'home' %}
      - Namespaced view names:  {% nav_active 'ai_chatbot:page' %}
      - Multiple fallbacks:     {% nav_active 'support' 'help' 'faq' %}
    """
    request = context.get('request')
    if not request or not request.resolver_match:
        return ''
    
    match = request.resolver_match
    # 'view_name' includes the namespace (e.g. 'ai_chatbot:page')
    # 'url_name' strips it (e.g. 'page')
    current_view_name = match.view_name
    current_url_name = match.url_name
    
    for name in url_names:
        if name == current_view_name or name == current_url_name:
            return 'active'
    return ''