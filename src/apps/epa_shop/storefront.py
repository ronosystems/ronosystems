from django.shortcuts import render
from django.db.models import Sum
from django.conf import settings
import cloudinary
import cloudinary.uploader
from django.db.models import Q 
from .models import Phone, Electronic, Accessory, SaleItem, HomepageFeaturedProduct

# ============================================
# CLOUDINARY CONFIGURATION
# ============================================
def _cloudinary_configure():
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )

# ============================================
# HOMEPAGE / STOREFRONT FETCHER 
# ============================================
def get_epa_products(company):
    if not company:
        return {}

    def build_list(query):
        items = []
        for item in query:
            product = item.product
            if product:
                if item.custom_price:
                    product.display_price = item.custom_price
                else:
                    product.display_price = product.selling_price
                    
                if item.section in ['discounted', 'flash_sale']:
                    product.original_price = product.selling_price
                
                # FIX: Use override_image_url so we don't overwrite the read-only @property
                if item.image:
                    product.override_image_url = item.image_url
                
                items.append(product)
        return items

    new_arrivals_query = HomepageFeaturedProduct.objects.filter(
        company=company, section='new_arrival', is_active=True
    ).select_related('content_type')
    new_arrivals = build_list(new_arrivals_query)

    discounted_query = HomepageFeaturedProduct.objects.filter(
        company=company, section='discounted', is_active=True
    ).select_related('content_type')
    discounted_products = build_list(discounted_query)

    flash_query = HomepageFeaturedProduct.objects.filter(
        company=company, section='flash_sale', is_active=True
    ).select_related('content_type')
    flash_sales = build_list(flash_query)

    top_selling_data = SaleItem.objects.filter(sale__company=company).values('content_type', 'object_id').annotate(total_sold=Sum('quantity')).order_by('-total_sold')[:6]
    
    top_selling = []
    for data in top_selling_data:
        try:
            model = data['content_type'].model_class()
            product = model.objects.get(id=data['object_id'])
            product.display_price = product.selling_price
            top_selling.append(product)
        except Exception:
            pass

    return {
        'new_arrivals': new_arrivals,
        'discounted_products': discounted_products,
        'flash_sales': flash_sales,
        'top_selling': top_selling,
    }


def epa_storefront(request):
    """Public storefront: shows ALL products with search and cart count"""
    
    company = getattr(request, 'current_company', None)
    
    if not company:
        return render(request, 'epa_shop/storefront.html', {
            'error': 'No company specified. Please access this store via a valid company domain.'
        })

    # 1. Search logic
    search_query = request.GET.get('q', '').strip()

    phones = Phone.objects.filter(company=company, is_active=True)
    electronics = Electronic.objects.filter(company=company, is_active=True)
    accessories = Accessory.objects.filter(company=company, is_active=True)

    if search_query:
        phones = phones.filter(
            Q(name__icontains=search_query) |
            Q(brand__icontains=search_query) |
            Q(model__icontains=search_query) |
            Q(product_code__icontains=search_query)
        )
        electronics = electronics.filter(
            Q(name__icontains=search_query) |
            Q(brand__icontains=search_query) |
            Q(model_number__icontains=search_query) |
            Q(product_code__icontains=search_query)
        )
        accessories = accessories.filter(
            Q(name__icontains=search_query) |
            Q(brand__icontains=search_query) |
            Q(model__icontains=search_query) |
            Q(product_code__icontains=search_query)
        )

    all_products = list(phones) + list(electronics) + list(accessories)
    all_products.sort(key=lambda p: p.name)

    # 2. HESABU YA CART (NEW)
    cart = request.session.get('epa_cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())

    context = {
        'company': company,
        'products': all_products,
        'total_products': len(all_products),
        'search_query': search_query,
        'cart_count': cart_count, 
    }
    
    return render(request, 'epa/storefront.html', context)



