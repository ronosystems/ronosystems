from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum
from django.conf import settings
import cloudinary
import cloudinary.uploader
from django.db.models import Q 
from .models import (
    Phone, Electronic, Accessory, SaleItem,
    HomepageFeaturedProduct, ProductImage,
)
from django.contrib import messages
from apps.epa_shop.product_views import can_manage_product_images


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
                    
                if item.section in ['discounted', 'flash_sale', 'amazing_deals']:
                    product.original_price = product.selling_price
                
                # 🚀 FIX: Explicitly reject the string "None"
                img_url = None
                raw_url = item.image_url if item.image else None
                
                if raw_url and raw_url != "None":
                    img_url = raw_url
                else:
                    # Fallback to gallery
                    gallery_img = ProductImage.objects.filter(
                        company=company,
                        content_type=item.content_type,
                        object_id=item.object_id,
                        is_active=True
                    ).order_by('-is_primary', 'display_order', 'id').first()
                    
                    if gallery_img:
                        gal_url = gallery_img.image_url
                        if gal_url and gal_url != "None":
                            img_url = gal_url
                            
                    # Fallback to product image
                    if not img_url and getattr(product, 'image', None):
                        prod_url = product.image_url
                        if prod_url and prod_url != "None":
                            img_url = prod_url

                product.override_image_url = img_url
                product.model_type = item.content_type.model
                
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

    # 🚀 NEW: Amazing Deals
    amazing_query = HomepageFeaturedProduct.objects.filter(
        company=company, section='amazing_deals', is_active=True
    ).select_related('content_type')
    amazing_deals = build_list(amazing_query)

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

    # Banner Slider logic
    banner_items = []
    banner_query = HomepageFeaturedProduct.objects.filter(
        company=company, is_active=True
    ).select_related('content_type').order_by('display_order')

    for item in banner_query:
        img_url = None
        raw_url = item.image_url if item.image else None
        
        if raw_url and raw_url != "None":
            img_url = raw_url
        else:
            gallery_img = ProductImage.objects.filter(
                company=company,
                content_type=item.content_type,
                object_id=item.object_id,
                is_active=True
            ).order_by('-is_primary', 'display_order', 'id').first()
            
            if gallery_img:
                gal_url = gallery_img.image_url
                if gal_url and gal_url != "None":
                    img_url = gal_url
                    
            if not img_url:
                product = item.product
                if product and getattr(product, 'image', None):
                    prod_url = product.image_url
                    if prod_url and prod_url != "None":
                        img_url = prod_url

        if img_url:
            product = item.product 
            
            if product and hasattr(product, 'name'):
                real_product_name = product.name
            else:
                real_product_name = "Featured Product"

            if product:
                display_price = item.custom_price if item.custom_price else product.selling_price
                original_price = product.selling_price if item.section in ['discounted', 'flash_sale', 'amazing_deals'] else None
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
        'amazing_deals': amazing_deals,   # 👈 NEW
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

    # 🚀 DYNAMIC IMAGE RESOLUTION
    # Attach the first available gallery image (or fallback to product.image)
    for p in all_products:
        img_url = None
        
        # 1. Check main product image (rejecting the string "None")
        raw_url = p.image_url if getattr(p, 'image', None) else None
        if raw_url and raw_url != "None":
            img_url = raw_url
        else:
            # 2. Fallback to ProductImage gallery
            ctype_model = 'phone' if isinstance(p, Phone) else 'electronic' if isinstance(p, Electronic) else 'accessory'
            gallery_img = ProductImage.objects.filter(
                company=company,
                content_type__model=ctype_model,
                object_id=p.id,
                is_active=True
            ).order_by('-is_primary', 'display_order', 'id').first()
            
            if gallery_img:
                gal_url = gallery_img.image_url
                if gal_url and gal_url != "None":
                    img_url = gal_url

        p.gallery_image_url = img_url

    # 2. HESABU YA CART
    cart = request.session.get('cart_orders_cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())

    # 3. Fetch homepage-featured sections
    homepage_data = get_epa_products(company)

    context = {
        'company': company,
        'products': all_products,
        'total_products': len(all_products),
        'search_query': search_query,
        'cart_count': cart_count,
        'can_manage_images': can_manage_product_images(request.user),
        **homepage_data,
    }
    
    return render(request, 'epa/storefront.html', context)


def public_product_detail(request, product_code):
    """Public facing product detail page for customers."""
    company = getattr(request, 'current_company', None)
    if not company:
        return redirect('/')

    # Try to find the product
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

    featured_item = HomepageFeaturedProduct.objects.filter(
        company=company,
        content_type__model=model_name,
        object_id=product.id,
    ).first()

    display_price = product.selling_price
    original_price = None

    if featured_item:
        if featured_item.custom_price:
            display_price = featured_item.custom_price
            if featured_item.custom_price != product.selling_price:
                original_price = product.selling_price
        if featured_item.section in ['discounted', 'flash_sale', 'amazing_deals']:
            original_price = product.selling_price

    # ------------------------------------------------------------------
    # BUILD GALLERY (ProductImage priority)
    # ------------------------------------------------------------------
    gallery = []

    # 1. Fetch all images from the ProductImage table
    extra_images = ProductImage.objects.filter(
        company=company,
        content_type__model=model_name,
        object_id=product.id,
        is_active=True,
    ).order_by('-is_primary', 'display_order', 'id')

    for img in extra_images:
        url = img.image_url
        if not url:
            continue
        gallery.append({
            'id': img.id,  
            'url': url,
            'alt': img.alt_text or product.name,
        })

    # 2. Fallback to original product.image ONLY if gallery is empty
    if not gallery and getattr(product, 'image', None):
        fallback_url = product.image_url
        if fallback_url:
            gallery.append({
                'id': 'cover',
                'url': fallback_url,
                'alt': product.name,
            })

    # 3. Homepage featured image takes priority
    if featured_item and featured_item.image:
        feat_url = featured_item.image_url
        if feat_url:
            gallery = [g for g in gallery if g['url'] != feat_url]
            gallery.insert(0, {
                'id': 'featured',
                'url': feat_url,
                'alt': product.name,
            })

    display_image = gallery[0]['url'] if gallery else None

    cart = request.session.get('cart_orders_cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())

    # ------------------------------------------------------------------
    # Fetch similar products
    # ------------------------------------------------------------------
    similar_products = []
    raw_similar = []

    if model_name == 'phone':
        raw_similar = list(Phone.objects.filter(company=company, brand__iexact=product.brand, is_active=True).exclude(id=product.id)[:4])
    elif model_name == 'electronic':
        raw_similar = list(Electronic.objects.filter(company=company, brand__iexact=product.brand, is_active=True).exclude(id=product.id)[:4])
    elif model_name == 'accessory':
        raw_similar = list(Accessory.objects.filter(company=company, brand__iexact=product.brand, is_active=True).exclude(id=product.id)[:4])

    # Attach dynamic gallery image to each similar product
    for sp in raw_similar:
        gallery_img = ProductImage.objects.filter(
            company=company,
            content_type__model=model_name,
            object_id=sp.id,
            is_active=True
        ).order_by('-is_primary', 'display_order', 'id').first()
        
        if gallery_img:
            sp.similar_image_url = gallery_img.image_url
        elif getattr(sp, 'image', None):
            sp.similar_image_url = sp.image_url
        else:
            sp.similar_image_url = None
            
        similar_products.append(sp)

    context = {
        'company': company,
        'product': product,
        'product_type': model_name,
        'display_price': display_price,
        'original_price': original_price,
        'display_image': display_image,
        'gallery': gallery,
        'cart_count': cart_count,
        'similar_products': similar_products, 
        'can_manage_images': can_manage_product_images(request.user),
    }

    return render(request, 'epa/public_product_detail.html', context)