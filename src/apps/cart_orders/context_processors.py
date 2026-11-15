# apps/cart_orders/context_processors.py
CART_SESSION_KEY = 'cart_orders_cart'

def cart_count(request):
    cart = request.session.get(CART_SESSION_KEY, {})
    # Sum the quantities of all items, instead of just counting unique rows
    total_quantity = sum(item.get('quantity', 1) for item in cart.values())
    return {'cart_count': total_quantity}