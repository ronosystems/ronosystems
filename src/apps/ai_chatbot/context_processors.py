from .services.context_builder import build_context

def chatbot_available(request):
    """Expose chatbot info to every template."""
    try:
        ctx = build_context(request)
    except Exception:
        return {'chatbot_enabled': False}
    return {
        'chatbot_enabled': True,
        'chatbot_scope': ctx['scope'],
        'chatbot_business_type': ctx['business_type_slug'],
    }