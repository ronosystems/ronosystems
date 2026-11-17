from apps.ai_chatbot.business_type_prompts.registry import get_prompt_module
from apps.ai_chatbot.business_type_prompts.base import build_system_prompt


def build_context(request):
    """
    Assemble everything the LLM needs for this request:
    - tenant (company or None)
    - business type slug
    - user identity
    - business rules from the prompt registry
    - live company contact info
    - live branch locations (prevents hallucination)
    """
    company = getattr(request, 'current_company', None)
    user = request.user if request.user.is_authenticated else None

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

    # --- Build Company Contact Info Context ---
    contact_info = ""
    if company:
        contact_info = (
            f"\nCOMPANY CONTACT INFO:\n"
            f"- Email: {company.email or 'Not provided'}\n"
            f"- Phone: {company.phone or 'Not provided'}\n"
            f"- Address: {company.address or 'Not provided'}\n"
            f"If the user asks for contact details, provide these directly.\n"
        )

    # --- Build Live Branch Info Context ---
    branches_info = ""
    if company:
        try:
            from apps.company.models import Branch
            branches = Branch.objects.filter(company=company, is_active=True)
            if branches.exists():
                branches_info = "\nBRANCHES (live from database — use this, do not guess):\n"
                for b in branches:
                    main_tag = " (MAIN)" if getattr(b, 'is_main_branch', False) else ""
                    branches_info += (
                        f"- {b.name}{main_tag} | "
                        f"Location: {getattr(b, 'location', 'N/A')} | "
                        f"Phone: {getattr(b, 'phone', 'N/A')}\n"
                    )
                branches_info += (
                    "If the user asks about branches or locations, "
                    "quote this list directly. Do not invent branches.\n"
                )
        except Exception:
            pass

    system_prompt = build_system_prompt(
        company=company,
        business_type_slug=business_type_slug,
        user=user,
        extra_context=rules + contact_info + branches_info,
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