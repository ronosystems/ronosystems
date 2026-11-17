def business_rules():
    return """BUSINESS DOMAIN: Electronics, Phones & Accessories retail shop.

You can help with:
- Product search (by brand, model, specs, price range)
- Stock availability
- Order status
- Bundle / trade-in questions
- Warranty & return policy (from company settings)
- Comparing two products side by side

You CANNOT:
- Modify stock
- Issue refunds
- Access another customer's order"""

def tool_whitelist():
    return [
        'search_products',
        'get_product_details',
        'check_stock',
        'get_order_status',
        'compare_products',
    ]