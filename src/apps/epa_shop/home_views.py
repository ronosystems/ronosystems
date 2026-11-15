from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import HomepageFeaturedProduct, Phone, Electronic, Accessory
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .cloudinary_utils import _upload_product_image_to_cloudinary


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
            image = request.FILES.get('image')
            
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
                    item = HomepageFeaturedProduct.objects.create(
                        company=company,
                        section=section,
                        content_type=content_type,
                        object_id=product_id,
                        custom_price=custom_price if custom_price else None,
                        display_order=display_order,
                    )
                    
                    # --- Upload image to Cloudinary ---
                    if image:
                        public_id = _upload_product_image_to_cloudinary(
                            image, 
                            folder=f"homepage/{timezone.now().strftime('%Y/%m')}"
                        )
                        if public_id:
                            item.image = public_id
                            item.save()
                        else:
                            messages.warning(request, "Product added, but the image failed to upload to Cloudinary.")
                    # ---------------------------------------

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

    current_items = HomepageFeaturedProduct.objects.filter(company=company).select_related('content_type')

    sections = {
        'new_arrival': current_items.filter(section='new_arrival'),
        'discounted': current_items.filter(section='discounted'),
        'flash_sale': current_items.filter(section='flash_sale'),
    }

    # ---------------------------------------------------------
    # NEW: Build the banner slider list
    # We only want to show items in the slider if they have an image.
    # ---------------------------------------------------------
    banner_items = []
    for item in current_items:
        # Check if the item has an uploaded image
        if item.image:
            banner_items.append(item)

    context = {
        'phones': phones,
        'electronics': electronics,
        'accessories': accessories,
        'sections': sections,
        'banner_items': banner_items, # Pass to template
    }
    
    return render(request, 'epa/home_set.html', context)