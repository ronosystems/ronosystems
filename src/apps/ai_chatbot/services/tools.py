import logging
import inspect
from django.db.models import Q, Sum
from django.urls import reverse

from apps.epa_shop.models import Phone, Electronic, Accessory, BranchStock, ProductImage
from apps.supermarket.models import Product as SMProduct
from apps.kuku_biz.models import Flock, EggProduction
from apps.chama.models import Savings, Loan
from apps.company.models import Branch

logger = logging.getLogger(__name__)


# ============================================
# SHARED HELPERS
# ============================================
def _serialize_product(p):
    """
    Serialize a product for the LLM. 
    STRICTLY excludes purchase_price / cost_amount.
    """
    try:
        stock_qty = p.total_stock()
    except Exception:
        stock_qty = 0

    # 1. Try to get the main image
    img_url = p.image_url

    # 2. If no main image, fall back to the ProductImage gallery
    if not img_url:
        ctype_model = 'phone' if isinstance(p, Phone) else 'electronic' if isinstance(p, Electronic) else 'accessory'
        gallery_img = ProductImage.objects.filter(
            company=p.company,
            content_type__model=ctype_model,
            object_id=p.id,
            is_active=True
        ).order_by('-is_primary', 'display_order', 'id').first()
        
        if gallery_img and gallery_img.image_url:
            img_url = gallery_img.image_url

    return {
        'id': p.id,
        'name': p.name,
        'brand': getattr(p, 'brand', ''),
        'price': float(p.selling_price), # Selling price ONLY
        'in_stock': stock_qty > 0,
        'stock_quantity': stock_qty,
        'image_url': img_url or "",
    }


# ============================================
# EPA SHOP TOOLS
# ============================================
def search_products(company, query, limit=5):
    q = Q(name__icontains=query) | Q(brand__icontains=query)
    phones = Phone.objects.filter(company=company, is_active=True).filter(q)[:limit]
    electronics = Electronic.objects.filter(company=company, is_active=True).filter(q)[:limit]
    accessories = Accessory.objects.filter(company=company, is_active=True).filter(q)[:limit]
    
    results = []
    for p in list(phones) + list(electronics) + list(accessories):
        results.append(_serialize_product(p))
        
    return results


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


def get_order_status(company, phone_number=None, order_number=None):
    """
    Look up a customer's order status via their phone number or the order number.
    """
    from apps.cart_orders.models import Order
    
    if not phone_number and not order_number:
        return {'error': 'Please provide either a phone number or an order number.'}

    qs = Order.objects.filter(company=company)
    
    if order_number:
        qs = qs.filter(order_number__iexact=order_number)
    elif phone_number:
        qs = qs.filter(customer_phone__icontains=phone_number)

    # Return the 3 most recent orders
    orders = qs.order_by('-created_at')[:3]
    
    results = []
    for o in orders:
        results.append({
            'order_number': o.order_number,
            'date': o.created_at.strftime('%Y-%m-%d %H:%M'),
            'status': o.get_status_display(),
            'total_amount': float(o.total_amount),
            'item_count': o.item_count,
        })
        
    if not results:
        return {'error': 'No orders found for that phone number or order number.'}
        
    return results


# ============================================
# COMPANY & BRANCH TOOLS
# ============================================
def get_branches(company):
    """
    Get a list of all active physical branches for the company.
    """
    branches = Branch.objects.filter(company=company, is_active=True)
    results = []
    for b in branches:
        results.append({
            'name': b.name,
            'location': getattr(b, 'location', ''),
            'phone': getattr(b, 'phone', ''),
            'is_main': getattr(b, 'is_main_branch', False)
        })
    return results


# ============================================
# WORKSHOP TOOLS
# ============================================
def get_workshop_jobs(company, phone_number=None):
    """
    Get the status of workshop repairs. If phone_number is provided, filter by customer.
    """
    from apps.workshop.models import WorkshopJob
    jobs = WorkshopJob.objects.filter(company=company).order_by('-created_at')
    
    if phone_number:
        jobs = jobs.filter(customer__phone__icontains=phone_number)
        
    results = []
    for j in jobs[:5]: # Limit to 5 most recent
        results.append({
            'ticket_number': j.ticket_number,
            'device': j.device_name,
            'issue': j.issue_description,
            'status': j.get_status_display(),
            'date_received': str(j.created_at.date())
        })
    return results


# ============================================
# SUPERMARKET TOOLS
# ============================================
def list_promotions(company):
    from apps.supermarket.models import Discount
    promos = Discount.objects.filter(company=company, is_active=True)[:10]
    return [{'name': p.name, 'percent': float(p.percentage)} for p in promos]


# ============================================
# KUKU BIZ TOOLS
# ============================================
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


# ============================================
# CHAMA TOOLS
# ============================================
def get_my_savings_balance(company, user):
    if not user or not user.is_authenticated:
        return {'error': 'Login required'}
    total = Savings.objects.filter(
        company=company, member__user=user
    ).aggregate(total=Sum('amount'))
    return {'balance': float(total['total'] or 0)}


def get_my_loan_status(company, user):
    if not user or not user.is_authenticated:
        return {'error': 'Login required'}
    loans = Loan.objects.filter(company=company, member__user=user, status='active')
    return [{'amount': float(l.amount), 'outstanding': float(l.outstanding_balance)} for l in loans]


# ============================================
# SYSTEM UTILS (For Links)
# ============================================
def get_system_url(url_name):
    """
    Get the correct Django URL for a given named route.
    """
    valid_routes = {
        'login': 'account_login',
        'signup': 'account_signup',
        'home': 'home',
        'store': 'epa-storefront',
        'cart': 'cart-orders:view-cart',
        'contact': 'contact',
    }
    
    django_name = valid_routes.get(url_name.lower())
    if not django_name:
        return {'error': f"Route '{url_name}' not recognized."}
        
    try:
        path = reverse(django_name)
        return {'url_path': path}
    except Exception as e:
        return {'error': str(e)}


# ============================================
# TOOL MAPS & SCHEMAS
# ============================================
TOOL_IMPLEMENTATIONS = {
    'search_products': search_products,
    'get_product_details': get_product_details,
    'check_stock': check_stock,
    'get_order_status': get_order_status,
    'get_branches': get_branches,
    'get_workshop_jobs': get_workshop_jobs,
    'list_promotions': list_promotions,
    'get_egg_prices': get_egg_prices,
    'get_flock_status': get_flock_status,
    'get_my_savings_balance': get_my_savings_balance,
    'get_my_loan_status': get_my_loan_status,
    'get_system_url': get_system_url,
}

TOOL_SCHEMAS = {
    'search_products': {
        'type': 'function',
        'function': {
            'name': 'search_products',
            'description': 'Search products by name or brand. Returns selling price and stock.',
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
    'check_stock': {
        'type': 'function',
        'function': {
            'name': 'check_stock',
            'description': 'Check the exact stock quantity for a specific product.',
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
    'get_order_status': {
        'type': 'function',
        'function': {
            'name': 'get_order_status',
            'description': 'Check a customer order status using their phone number or order number (e.g. ORD-20261117-0001).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'phone_number': {'type': 'string', 'description': 'Customer phone number (e.g. 0712345678)'},
                    'order_number': {'type': 'string', 'description': 'Order number (e.g. ORD-...)'},
                },
            },
        },
    },
    'get_branches': {
        'type': 'function',
        'function': {
            'name': 'get_branches',
            'description': 'Get a list of all physical branch locations, phone numbers, and main branch status.',
            'parameters': {
                'type': 'object',
                'properties': {},
            },
        },
    },
    'get_workshop_jobs': {
        'type': 'function',
        'function': {
            'name': 'get_workshop_jobs',
            'description': 'Check the status of device repairs in the workshop. Optionally filter by customer phone number.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'phone_number': {'type': 'string', 'description': 'Customer phone number to search for'},
                },
            },
        },
    },
    'get_system_url': {
        'type': 'function',
        'function': {
            'name': 'get_system_url',
            'description': 'Get the exact relative URL path for system pages like login, signup, home, store, or cart.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'url_name': {
                        'type': 'string', 
                        'enum': ['login', 'signup', 'home', 'store', 'cart', 'contact']
                    },
                },
                'required': ['url_name'],
            },
        },
    },
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
    sig = inspect.signature(fn)
    kwargs = dict(args)
    if 'company' in sig.parameters:
        kwargs['company'] = company
    if 'user' in sig.parameters:
        kwargs['user'] = user

    try:
        return fn(**kwargs)
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return {'error': str(e)}