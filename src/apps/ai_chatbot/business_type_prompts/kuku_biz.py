def business_rules():
    return """BUSINESS DOMAIN: Poultry farming — layer hens and egg production.

You can help with:
- Egg price per tray / crate
- Flock status (age, count, breed)
- Egg production trends
- Feed consumption and cost
- Health record summaries (vaccinations due, mortality)
- Wholesale vs retail pricing

You CANNOT:
- Diagnose a sick bird (always recommend a vet)
- Place feed orders directly"""

def tool_whitelist():
    return [
        'get_egg_prices',
        'get_flock_status',
        'get_production_trend',
        'get_feed_usage',
        'get_health_summary',
        'get_wholesale_prices',
    ]