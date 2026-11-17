from apps.epa_shop.models import Phone, Electronic, Accessory
from apps.supermarket.models import Product as SMProduct
from apps.kuku_biz.models import Flock, EggProduction
from apps.chama.models import Savings, Loan
from django.db.models import Q


# --- shared helpers ---------------------------------------------------------
def _serialize_product(p):
    return {
        'id': p.id,
        'name': p.name,
        'brand': getattr(p, 'brand', ''),
        'price': float(p.selling_price),
        'in_stock': getattr(p, 'stock_quantity', 0) > 0,
    }


# --- EPA SHOP ---------------------------------------------------------------
def search_products(company, query, limit=5):
    q = Q(name__icontains=query) | Q(brand__icontains=query)
    phones = Phone.objects.filter(company=company, is_active=True).filter(q)[:limit]
    electronics = Electronic.objects.filter(company=company, is_active=True).filter(q)[:limit]
    accessories = Accessory.objects.filter(company=company, is_active=True).filter(q)[:limit]
    return [_serialize_product(p) for p in list(phones) + list(electronics) + list(accessories)]


def get_product_details(company, product_id, model_type):
    model_map = {'phone': Phone, 'electronic': Electronic, 'accessory': Accessory}
    Model = model_map.get(model_type)
    if not Model:
        return {'error': 'Unknown model type'}
    try:
        p = Model.objects.get(company=company, id=product_id)
    except Model.DoesNotExist:
        return {'error': 'Product not found'}
    return _serialize_product(p)


def check_stock(company, product_id, model_type):
    d = get_product_details(company, product_id, model_type)
    if 'error' in d:
        return d
    return {'in_stock': d['in_stock'], 'quantity': d.get('stock_quantity', 0)}


# --- SUPERMARKET ------------------------------------------------------------
def list_promotions(company):
    from apps.supermarket.models import Discount
    promos = Discount.objects.filter(company=company, is_active=True)[:10]
    return [{'name': p.name, 'percent': float(p.percentage)} for p in promos]


# --- KUKU BIZ ---------------------------------------------------------------
def get_egg_prices(company):
    from apps.kuku_biz.models import PriceHistory
    latest = PriceHistory.objects.filter(company=company).order_by('-effective_date')[:5]
    return [{'tray_price': float(p.price_per_tray), 'date': str(p.effective_date)} for p in latest]


def get_flock_status(company):
    flocks = Flock.objects.filter(company=company, is_active=True)
    return [{
        'name': f.name,
        'count': f.current_count,
        'age_weeks': f.age_weeks,
        'breed': f.breed,
    } for f in flocks]


# --- CHAMA ------------------------------------------------------------------
def get_my_savings_balance(company, user):
    """Only the requesting user's own balance."""
    if not user or not user.is_authenticated:
        return {'error': 'Login required'}
    total = Savings.objects.filter(
        company=company, member__user=user
    ).aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('amount'))
    return {'balance': float(total['total'] or 0)}


def get_my_loan_status(company, user):
    if not user or not user.is_authenticated:
        return {'error': 'Login required'}
    loans = Loan.objects.filter(company=company, member__user=user, status='active')
    return [{'amount': float(l.amount), 'outstanding': float(l.outstanding_balance)} for l in loans]


# --- TOOL SCHEMA MAP --------------------------------------------------------
# Maps the tool name that the LLM sees → the Python callable + JSON schema
TOOL_IMPLEMENTATIONS = {
    'search_products': search_products,
    'get_product_details': get_product_details,
    'check_stock': check_stock,
    'list_promotions': list_promotions,
    'get_egg_prices': get_egg_prices,
    'get_flock_status': get_flock_status,
    'get_my_savings_balance': get_my_savings_balance,
    'get_my_loan_status': get_my_loan_status,
}

TOOL_SCHEMAS = {
    'search_products': {
        'type': 'function',
        'function': {
            'name': 'search_products',
            'description': 'Search products by name or brand.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 5},
                },
                'required': ['query'],
            },
        },
    },
    'get_product_details': {
        'type': 'function',
        'function': {
            'name': 'get_product_details',
            'description': 'Get full details for one product.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'product_id': {'type': 'integer'},
                    'model_type': {'type': 'string', 'enum': ['phone', 'electronic', 'accessory']},
                },
                'required': ['product_id', 'model_type'],
            },
        },
    },
    # ...add the rest following the same shape
}


def build_tool_schemas(whitelist):
    """Return only the schemas the tenant is allowed to use."""
    return [TOOL_SCHEMAS[name] for name in whitelist if name in TOOL_SCHEMAS]


def dispatch_tool(name, args, *, company, user):
    """Execute a tool, injecting tenant + user automatically."""
    fn = TOOL_IMPLEMENTATIONS.get(name)
    if not fn:
        return {'error': f'Unknown tool: {name}'}

    # Inject company/user when the signature requires it
    import inspect
    sig = inspect.signature(fn)
    kwargs = dict(args)
    if 'company' in sig.parameters:
        kwargs['company'] = company
    if 'user' in sig.parameters:
        kwargs['user'] = user

    try:
        return fn(**kwargs)
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return {'error': str(e)}