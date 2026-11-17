def business_rules():
    return """BUSINESS DOMAIN: Supermarket / grocery.

You can help with:
- Product & price lookup (by name, category, barcode)
- Current promotions / discounts
- Stock levels
- Aisle / shelf location
- Delivery slots and fees

You CANNOT:
- Process payments
- Change prices"""

def tool_whitelist():
    return [
        'search_products',
        'get_product_details',
        'check_stock',
        'list_promotions',
        'get_shelf_location',
        'get_delivery_slots',
    ]