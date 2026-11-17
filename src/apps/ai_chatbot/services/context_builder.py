from apps.ai_chatbot.business_type_prompts.registry import get_prompt_module
from apps.ai_chatbot.business_type_prompts.base import build_system_prompt


def build_context(request):
    """
    Assemble everything the LLM needs for this request:
    - tenant (company or None)
    - business type slug
    - user identity
    - business rules from the prompt registry
    """
    company = getattr(request, 'current_company', None)
    user = request.user if request.user.is_authenticated else None

    # Company already exposes `.business_type_slug` (see models.py) —
    # it returns the registry slug or None.
    business_type_slug = ''
    if company and company.business_type_slug:
        business_type_slug = company.business_type_slug

    mod = get_prompt_module(business_type_slug) if business_type_slug else None

    if mod:
        rules = mod.business_rules()
        tools = mod.tool_whitelist()
    else:
        rules = _generic_rules()
        tools = ['search_products']  # safe default

    system_prompt = build_system_prompt(
        company=company,
        business_type_slug=business_type_slug,
        user=user,
        extra_context=rules,
    )

    return {
        'company': company,
        'business_type_slug': business_type_slug,
        'system_prompt': system_prompt,
        'tool_whitelist': tools,
        'scope': 'company' if company else 'system',
    }


def _generic_rules():
    return (
        "You are a general assistant. If you don't know something, "
        "say so and suggest contacting support."
    )