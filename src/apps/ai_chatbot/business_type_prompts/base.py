def build_system_prompt(*, company, business_type_slug, user, extra_context=""):
    """
    Returns the base system prompt. Each business-type module overrides
    `business_rules()` and optionally `tool_whitelist()`.
    """
    tenant_line = (
        f"You are the AI assistant for **{company.display_name}**, "
        f"a {company.business_type.name} business."
        if company else
        "You are the AI assistant for **RonoSystems**, a multi-business "
        "SaaS platform. You help visitors understand features, pricing, "
        "and how to get started."
    )

    user_line = (
        f"The current user is {user.get_full_name() or user.email} "
        f"({user.role if hasattr(user, 'role') else 'member'})."
        if user and user.is_authenticated else
        "The current user is a public visitor (not logged in)."
    )

    return f"""{tenant_line}
{user_line}

RULES:
- Never invent prices, stock levels, or sales figures — always use tools.
- Stay in character for this business type. Do not give advice outside it.
- If asked something outside your scope, politely redirect.
- Keep replies concise (under 120 words unless the user asks for detail).
- Never reveal API keys, internal IDs, or other tenants' data.

{business_rules()}
{extra_context}
"""