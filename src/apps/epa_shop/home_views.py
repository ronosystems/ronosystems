from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.db.models import Q

# ✅ CRITICAL: Import all models needed
from apps.epa_shop.models import (
    HomepageFeaturedProduct, 
    Phone, 
    Electronic, 
    Accessory, 
    ProductImage
)



@login_required
def search_products_api(request):
    """AJAX endpoint for product search in the homepage manager."""
    company = getattr(request, 'current_company', None)
    if not company:
        return JsonResponse({'results': []})

    query = request.GET.get('q', '').strip()
    ptype = request.GET.get('type', '').strip()

    if len(query) < 1 or not ptype:
        return JsonResponse({'results': []})

    model_map = {'phone': Phone, 'electronic': Electronic, 'accessory': Accessory}
    model = model_map.get(ptype)
    if not model:
        return JsonResponse({'results': []})

    qs = model.objects.filter(company=company, is_active=True)
    qs = qs.filter(
        Q(name__icontains=query) |
        Q(brand__icontains=query) |
        Q(product_code__icontains=query) |
        Q(barcode__icontains=query)
    ).order_by('name')[:10]

    results = []
    for p in qs:
        results.append({
            'id': p.id,
            'name': p.name,
            'brand': p.brand or '',
            'product_code': p.product_code or '',
            'price': str(p.selling_price),
            'type': ptype,
        })

    return JsonResponse({'results': results})


@login_required
def manage_homepage(request):
    company = getattr(request, 'current_company', None)
    if not company:
        messages.error(request, "You must be on a company domain to manage the homepage.")
        return redirect('/')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_product':
            section = request.POST.get('section')
            product_type = request.POST.get('product_type')
            product_id = request.POST.get('product_id')
            custom_price = request.POST.get('custom_price')
            display_order = request.POST.get('display_order', 0)
            
            model_map = {'phone': Phone, 'electronic': Electronic, 'accessory': Accessory}
            
            if product_type in model_map:
                model_class = model_map[product_type]
                content_type = ContentType.objects.get_for_model(model_class)
                
                exists = HomepageFeaturedProduct.objects.filter(
                    company=company, section=section, content_type=content_type, object_id=product_id
                ).exists()
                
                if exists:
                    messages.warning(request, "This product is already in that section.")
                else:
                    HomepageFeaturedProduct.objects.create(
                        company=company,
                        section=section,
                        content_type=content_type,
                        object_id=product_id,
                        custom_price=custom_price if custom_price else None,
                        display_order=display_order,
                    )
                    messages.success(request, "Product added to homepage successfully!")

        elif action == 'delete_product':
            item_id = request.POST.get('item_id')
            HomepageFeaturedProduct.objects.filter(id=item_id, company=company).delete()
            messages.success(request, "Product removed from homepage.")

        return redirect('manage-homepage')

    # ============================================
    # GET Request Logic
    # ============================================
    phones = Phone.objects.filter(company=company, is_active=True)
    electronics = Electronic.objects.filter(company=company, is_active=True)
    accessories = Accessory.objects.filter(company=company, is_active=True)

    # 🚀 1. CRITICAL: Convert to a list so dynamic attributes persist
    current_items = list(HomepageFeaturedProduct.objects.filter(company=company).select_related('content_type'))

    # 🚀 2. Attach the dynamic image to each item
    for item in current_items:
        img_url = None
        
        # Priority 1: Gallery Image (ProductImage)
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
                
        # Priority 2: Original Product Image
        if not img_url:
            product = item.product
            if product and getattr(product, 'image', None):
                prod_url = product.image_url
                if prod_url and prod_url != "None":
                    img_url = prod_url

        # Final safety check
        if img_url == "None":
            img_url = None
            
        item.dynamic_preview_image = img_url

    # 🚀 3. Build sections from the LIST using Python list comprehensions
    sections = {
        'new_arrival': [i for i in current_items if i.section == 'new_arrival'],
        'discounted': [i for i in current_items if i.section == 'discounted'],
        'flash_sale': [i for i in current_items if i.section == 'flash_sale'],
        'amazing_deals': [i for i in current_items if i.section == 'amazing_deals'], 
    }

    banner_items = [item for item in current_items if item.dynamic_preview_image]

    context = {
        'phones': phones,
        'electronics': electronics,
        'accessories': accessories,
        'sections': sections,
        'banner_items': banner_items,
    }
    
    return render(request, 'epa_shop/home_set.html', context)