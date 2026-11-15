from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum
from django.conf import settings
import cloudinary
import cloudinary.uploader
from django.db.models import Q 
from .models import Phone, Electronic, Accessory, SaleItem, HomepageFeaturedProduct
from django.contrib import messages


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
                
                # Use override_image_url so we don't overwrite the read-only @property
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

    # 👇 Build banner slider items as explicit dictionaries
    banner_items = []
    banner_query = HomepageFeaturedProduct.objects.filter(
        company=company, is_active=True
    ).exclude(image='').exclude(image__isnull=True).order_by('display_order')

    for item in banner_query:
        img_url = item.image_url 
        if img_url:
            # Fetch the actual product via GenericForeignKey
            product = item.product 
            
            # Safely get the name directly from the product object
            if product and hasattr(product, 'name'):
                real_product_name = product.name
            else:
                real_product_name = "Featured Product"

            # Determine the price to display
            if product:
                display_price = item.custom_price if item.custom_price else product.selling_price
                original_price = product.selling_price if item.section in ['discounted', 'flash_sale'] else None
            else:
                display_price = "N/A"
                original_price = None

            banner_items.append({
                'image_url': img_url,
                'product_name': real_product_name, 
                'section': item.section, 
                'display_price': display_price,   
                'original_price': original_price, 
                'product_url': f"/epa_shop/shop/product/{product.product_code}/" if product and getattr(product, 'product_code', None) else "#"
            })

    return {
        'new_arrivals': new_arrivals,
        'discounted_products': discounted_products,
        'flash_sales': flash_sales,
        'top_selling': top_selling,
        'banner_items': banner_items,
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

    # 2. HESABU YA CART
    cart = request.session.get('epa_cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())

    # 3. Fetch homepage-featured sections
    homepage_data = get_epa_products(company)

    context = {
        'company': company,
        'products': all_products,
        'total_products': len(all_products),
        'search_query': search_query,
        'cart_count': cart_count,
        **homepage_data,
    }
    
    return render(request, 'epa/storefront.html', context)


def public_product_detail(request, product_code):
    """Public facing product detail page for customers."""
    company = getattr(request, 'current_company', None)
    if not company:
        return redirect('/')

    # Try to find the product in Phones, Electronics, or Accessories
    product = None
    model_name = None
    
    try:
        product = Phone.objects.get(company=company, product_code=product_code, is_active=True)
        model_name = 'phone'
    except Phone.DoesNotExist:
        pass
        
    if not product:
        try:
            product = Electronic.objects.get(company=company, product_code=product_code, is_active=True)
            model_name = 'electronic'
        except Electronic.DoesNotExist:
            pass
            
    if not product:
        try:
            product = Accessory.objects.get(company=company, product_code=product_code, is_active=True)
            model_name = 'accessory'
        except Accessory.DoesNotExist:
            pass

    if not product:
        messages.error(request, "Product not found or unavailable.")
        return redirect('epa-storefront')

    # Check if this product is featured on the homepage (to get custom image/price)
    featured_item = HomepageFeaturedProduct.objects.filter(
        company=company, 
        content_type__model=model_name, 
        object_id=product.id
    ).first()

    # Determine the correct image and price to display
    display_price = product.selling_price
    original_price = None
    display_image = product.image_url if hasattr(product, 'image_url') else None

    if featured_item:
        if featured_item.custom_price:
            display_price = featured_item.custom_price
            # Show original price if the custom price is different from the standard price
            if featured_item.custom_price != product.selling_price:
                original_price = product.selling_price
                
        # Also show original price if it's in a sale section
        if featured_item.section in ['discounted', 'flash_sale']:
            original_price = product.selling_price

        if featured_item.image:
            display_image = featured_item.image_url

    # Calculate Cart Count
    cart = request.session.get('epa_cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())

    context = {
        'company': company,
        'product': product,
        'product_type': model_name,
        'display_price': display_price,     
        'original_price': original_price,
        'display_image': display_image,     
        'cart_count': cart_count,
    }
    
    return render(request, 'epa/public_product_detail.html', context)