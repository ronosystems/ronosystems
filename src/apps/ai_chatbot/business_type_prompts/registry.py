from apps.companies.business_types import BusinessTypeEnum
from . import epa_shop, supermarket, kuku_biz, chama

_PROMPTS = {
    'epa-shop': epa_shop,
    'supermarket': supermarket,
    'kuku-biz': kuku_biz,
    'chama': chama,
}

def get_prompt_module(slug):
    """Return the business-type prompt module, or None."""
    return _PROMPTS.get(slug)

def get_tool_whitelist(slug):
    mod = get_prompt_module(slug)
    return mod.tool_whitelist() if mod else []