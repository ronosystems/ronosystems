# /home/rs/ronosystems/src/apps/cart_orders/client_views.py
#
# CUSTOMER-FACING cart + checkout views. No authentication required.
# Staff / admin order management lives in staff_views.py.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
import json

from .models import Order, OrderItem
from apps.company.models import Branch


CART_SESSION_KEY = 'cart_orders_cart'


# ============================================
# HELPERS
# ============================================

def _get_cart(request):
    """Return the current cart dict from the session."""
    return request.session.get(CART_SESSION_KEY, {})


def _cart_total(cart):
    """Sum price × quantity across all cart lines."""
    return sum(item['price'] * item['quantity'] for item in cart.values())


def _resolve_model(model_type):
    """Map a model_type string to the actual Django model class."""
    from apps.epa_shop.models import Phone, Electronic, Accessory
    return {
        'phone':      Phone,
        'electronic': Electronic,
        'accessory':  Accessory,
    }.get((model_type or '').lower())


def _available_stock(product, model_type):
    """Available units (per-unit for serialized items, qty for accessories)."""
    if model_type in ('phone', 'electronic'):
        return product.units.filter(status='available').count()
    return product.total_quantity_in_stock


# ============================================
# 1. VIEW CART
# ============================================

def view_cart(request):
    """Display the current session cart."""
    cart = _get_cart(request)
    total = _cart_total(cart)
    
    # Calculate total items for the badge
    total_items = sum(item['quantity'] for item in cart.values())

    context = {
        'cart':       cart,
        'total':      total,
        'cart_count': total_items,
    }
    return render(request, 'cart_orders/cart.html', context)


# ============================================
# 2. ADD TO CART (AJAX)
# ============================================

@require_POST
def add_to_cart(request):
    """
    Add a product to the session cart.
    Validates product existence, company ownership, active flag, stock,
    and respects the requested quantity.
    """
    try:
        data = json.loads(request.body)

        model_type = (data.get('model_type') or '').lower()
        product_id = data.get('product_id')
        name       = data.get('name', '')
        price      = data.get('price', 0)
        image      = data.get('image', '')
        original_price = data.get('original_price')
        
        # Safely parse quantity
        try:
            requested_qty = int(data.get('quantity', 1))
            if requested_qty < 1:
                requested_qty = 1
        except (ValueError, TypeError):
            requested_qty = 1

        if not model_type or not product_id:
            return JsonResponse(
                {'status': 'error', 'message': 'Missing product information'},
                status=400,
            )

        model_class = _resolve_model(model_type)
        if not model_class:
            return JsonResponse(
                {'status': 'error', 'message': 'Unknown product type'},
                status=400,
            )

        company = getattr(request, 'current_company', None)
        if not company:
            return JsonResponse(
                {'status': 'error', 'message': 'Company not resolved'},
                status=400,
            )

        product = model_class.objects.filter(
            id=product_id, company=company, is_active=True,
        ).first()
        if not product:
            return JsonResponse(
                {'status': 'error', 'message': 'Product not available'},
                status=404,
            )

        available = _available_stock(product, model_type)

        if CART_SESSION_KEY not in request.session:
            request.session[CART_SESSION_KEY] = {}
        cart = request.session[CART_SESSION_KEY]

        product_key = f"{model_type}_{product_id}"
        current_qty = cart.get(product_key, {}).get('quantity', 0)

        # Check if adding the requested quantity exceeds stock
        if current_qty + requested_qty > available:
            return JsonResponse(
                {
                    'status': 'error',
                    'message': (
                        f'Only {available} in stock. '
                        f'You already have {current_qty} in your cart. '
                        f'Cannot add {requested_qty} more.'
                    ),
                },
                status=400,
            )

        if product_key in cart:
            cart[product_key]['quantity'] += requested_qty
        else:
            cart[product_key] = {
                'model_type': model_type,
                'product_id': product_id,
                'name':       name or product.name,
                'price':      float(price or product.selling_price),
                'image':      image,
                'quantity':   requested_qty,
                'original_price': float(original_price) if original_price else None,
            }

        request.session.modified = True
        
        # Calculate total items for the badge
        total_items = sum(item['quantity'] for item in cart.values())

        return JsonResponse({
            'status':     'success',
            'message':    f'{requested_qty} item(s) added to cart',
            'cart_count': total_items,  
            'product':    name or product.name,
        })

    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid request body'}, status=400,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ============================================
# 3. REMOVE FROM CART (AJAX)
# ============================================

@require_POST
def remove_from_cart(request):
    """Remove a single line from the session cart."""
    try:
        data = json.loads(request.body)
        product_key = data.get('product_key')

        if not product_key:
            return JsonResponse(
                {'status': 'error', 'message': 'product_key is required'},
                status=400,
            )

        cart = request.session.get(CART_SESSION_KEY, {})
        if product_key in cart:
            del cart[product_key]
            request.session[CART_SESSION_KEY] = cart
            request.session.modified = True
            
            total_items = sum(item['quantity'] for item in cart.values())
            
            return JsonResponse({
                'status':     'success',
                'cart_count': total_items,  
                'message':    'Item removed',
            })

        return JsonResponse(
            {'status': 'error', 'message': 'Item not found in cart'},
            status=404,
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid request body'}, status=400,
        )
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ============================================
# 4. CHECKOUT — creates Order, NOT Sale
# ============================================

def checkout(request):
    """
    GET  → render checkout form.
    POST → create Order + OrderItems (does NOT create a Sale).

    Sale creation happens later in staff_views.confirm_order().
    """
    cart = _get_cart(request)
    if not cart:
        messages.warning(request, "Your cart is empty.")
        return redirect('cart-orders:view-cart')

    total   = _cart_total(cart)
    company = getattr(request, 'current_company', None)

    if not company:
        messages.error(request, "Company domain not found.")
        return redirect('/')

    if request.method != 'POST':
        # Fetch active branches for the "Shop Near You" dropdown
        branches = Branch.objects.filter(company=company, is_active=True)
        
        return render(request, 'cart_orders/checkout.html', {
            'cart': cart, 
            'total': total,
            'branches': branches,
        })

    name           = request.POST.get('name', '').strip()
    email          = request.POST.get('email', '').strip()
    phone          = request.POST.get('phone', '').strip()
    alt_phone      = request.POST.get('alternative_phone', '').strip()
    city           = request.POST.get('city', '').strip()
    address        = request.POST.get('address', '').strip()
    payment_method = request.POST.get('payment_method', 'cash').strip()
    branch_id      = request.POST.get('branch_id') # Capture selected branch

    if not name or not phone:
        messages.error(request, "Name and Phone number are required.")
        # Fetch branches again for re-rendering
        branches = Branch.objects.filter(company=company, is_active=True)
        return render(request, 'cart_orders/checkout.html', {
            'cart': cart, 'total': total, 'branches': branches,
        })

    # Resolve branch
    selected_branch = None
    if branch_id:
        selected_branch = Branch.objects.filter(id=branch_id, company=company).first()
    
    if not selected_branch:
        # Fallback to first active branch if none selected or invalid
        selected_branch = Branch.objects.filter(company=company, is_active=True).first()

    if not selected_branch:
        messages.error(
            request,
            "No active branch found for this company. Please contact support.",
        )
        branches = Branch.objects.filter(company=company, is_active=True)
        return render(request, 'cart_orders/checkout.html', {
            'cart': cart, 'total': total, 'branches': branches,
        })

    try:
        with transaction.atomic():

            order = Order.objects.create(
                company=company,
                branch=selected_branch, # Use the selected branch
                customer_name=name,
                customer_phone=phone,
                customer_email=email,
                alternative_phone=alt_phone,
                customer_city=city,
                customer_address=address,
                subtotal=total,
                total_amount=total,
                payment_method=payment_method,
                status='new',
            )

            for item in cart.values():
                model_class = _resolve_model(item['model_type'])
                if not model_class:
                    continue

                ct  = ContentType.objects.get_for_model(model_class)
                qty = int(item['quantity'])
                up  = Decimal(str(item['price']))

                OrderItem.objects.create(
                    order=order,
                    content_type=ct,
                    object_id=item['product_id'],
                    item_name=item['name'],
                    quantity=qty,
                    unit_price=up,
                    total_price=up * qty,
                )

        request.session[CART_SESSION_KEY] = {}
        request.session.modified = True

        messages.success(
            request,
            f"Thank you {name}! Your order {order.order_number} has been received. "
            f"We will call you on {phone} shortly.",
        )
        return redirect('cart-orders:order-success', order_number=order.order_number)

    except Exception as e:
        messages.error(request, f"Error processing order: {str(e)}")
        # Fetch branches again for re-rendering
        branches = Branch.objects.filter(company=company, is_active=True)
        return render(request, 'cart_orders/checkout.html', {
            'cart': cart, 'total': total, 'branches': branches,
        })


# ============================================
# 5. ORDER SUCCESS
# ============================================

def order_success(request, order_number):
    """
    Thank-you page. Scoped by current_company to prevent enumeration
    across tenants. Uses order_number, not PK.
    """
    company = getattr(request, 'current_company', None)
    if not company:
        messages.error(request, "Company domain not found.")
        return redirect('/')

    order = get_object_or_404(
        Order, order_number=order_number, company=company,
    )
    return render(request, 'cart_orders/order_success.html', {'order': order})