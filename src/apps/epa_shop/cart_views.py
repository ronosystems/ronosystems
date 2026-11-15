# /home/rs/ronosystems/src/apps/epa_shop/cart_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal
import json

from .models import Sale, SaleItem, Customer, Phone, Electronic, Accessory
from django.contrib.contenttypes.models import ContentType


# ============================================
# 1. CART MANAGEMENT (SESSION-BASED)
# ============================================

@require_POST
def add_to_cart(request):
    """Add a product to the session cart via AJAX."""
    try:
        data = json.loads(request.body)
        
        # Initialize cart if it doesn't exist
        if 'epa_cart' not in request.session:
            request.session['epa_cart'] = {}
            
        cart = request.session['epa_cart']
        
        # Create a unique key for this product (e.g., 'phone_12')
        product_key = f"{data['model_type']}_{data['product_id']}"
        
        # Add or update quantity
        if product_key in cart:
            cart[product_key]['quantity'] += 1
        else:
            cart[product_key] = {
                'model_type': data['model_type'],
                'product_id': data['product_id'],
                'name': data['name'],
                'price': float(data['price']),
                'image': data['image'],
                'quantity': 1
            }
            
        request.session.modified = True
        
        return JsonResponse({'status': 'success', 'cart_count': len(cart)})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def view_cart(request):
    """Display the current cart."""
    cart = request.session.get('epa_cart', {})
    total = sum(item['price'] * item['quantity'] for item in cart.values())
    
    context = {
        'cart': cart,
        'total': total,
    }
    return render(request, 'epa/cart.html', context)


@require_POST
def remove_from_cart(request):
    """Remove a single item from the session cart."""
    try:
        data = json.loads(request.body)
        product_key = data.get('product_key')
        
        if 'epa_cart' in request.session and product_key in request.session['epa_cart']:
            del request.session['epa_cart'][product_key]
            request.session.modified = True
            return JsonResponse({'status': 'success', 'cart_count': len(request.session['epa_cart'])})
        
        return JsonResponse({'status': 'error', 'message': 'Item not found in cart'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)




# ============================================
# 2. CHECKOUT & ORDER CREATION
# ============================================

def checkout(request):
    """Handle customer checkout form and order creation."""
    cart = request.session.get('epa_cart', {})
    if not cart:
        messages.warning(request, "Your cart is empty.")
        return redirect('cart-view')

    total = sum(item['price'] * item['quantity'] for item in cart.values())
    company = getattr(request, 'current_company', None)
    
    if not company:
        messages.error(request, "Company domain not found.")
        return redirect('/')

    if request.method == 'POST':
        # 1. Get form data
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        alt_phone = request.POST.get('alternative_phone', '').strip()
        city = request.POST.get('city', '').strip()
        address = request.POST.get('address', '').strip()
        payment_method = request.POST.get('payment_method', 'cash')
        
        # 2. Basic validation
        if not name or not phone:
            messages.error(request, "Name and Phone number are required.")
            return render(request, 'epa/checkout.html', {'cart': cart, 'total': total})

        try:
            # 3. Create or update Customer
            customer, created = Customer.objects.get_or_create(
                company=company, 
                phone=phone,
                defaults={
                    'name': name, 
                    'email': email,
                    'alternative_phone': alt_phone,
                    'city': city,
                    'address': address,
                }
            )
            # If customer already existed, update their details
            if not created:
                customer.name = name
                customer.email = email
                customer.alternative_phone = alt_phone
                customer.city = city
                customer.address = address
                customer.save()

            # 4. Get default branch
            from apps.company.models import Branch
            default_branch = Branch.objects.filter(company=company, is_active=True).first()

            if not default_branch:
                messages.error(request, "No active branch found for this company. Please contact support.")
                return render(request, 'epa/checkout.html', {'cart': cart, 'total': total})

            # 5. Create the Sale
            sale = Sale.objects.create(
                company=company,
                branch=default_branch,
                customer=customer,
                customer_name=name,
                customer_phone=phone,
                customer_email=email,
                total_amount=total,
                net_amount=total,
                payment_status='pending',  # Awaiting payment/follow-up
                payment_method=payment_method,
                sold_by=request.user if request.user.is_authenticated else None,
                sale_date=timezone.now()
            )

            # 6. Move cart items to SaleItems
            for key, item in cart.items():
                model_type = item['model_type'].lower()
                model_map = {'phone': Phone, 'electronic': Electronic, 'accessory': Accessory}
                model_class = model_map.get(model_type)
                
                if not model_class:
                    continue
                    
                content_type = ContentType.objects.get_for_model(model_class)
                
                SaleItem.objects.create(
                    sale=sale,
                    content_type=content_type,
                    object_id=item['product_id'],
                    item_name=item['name'],
                    quantity=item['quantity'],
                    unit_price=Decimal(str(item['price'])),
                    total_price=Decimal(str(item['price'] * item['quantity']))
                )

            # 7. Clear the cart
            request.session['epa_cart'] = {}
            request.session.modified = True

            # 8. Redirect to success page
            messages.success(request, f"Thank you {name}! Your order #{sale.company_sale_id} has been received. We will call you shortly.")
            return redirect('order-success', sale_id=sale.id)

        except Exception as e:
            messages.error(request, f"Error processing order: {str(e)}")
            return render(request, 'epa/checkout.html', {'cart': cart, 'total': total})

    return render(request, 'epa/checkout.html', {'cart': cart, 'total': total})


def order_success(request, sale_id):
    """Thank you page shown to the customer after placing an order."""
    sale = get_object_or_404(Sale, id=sale_id)
    return render(request, 'epa/order_success.html', {'sale': sale})


# ============================================
# 3. ORDER MANAGEMENT (ADMIN)
# ============================================

@login_required
def order_list(request):
    """Admin page to view all pending online orders."""
    company = getattr(request, 'current_company', None)
    if not company:
        return redirect('/')

    # Pata oda zote zilizo pending
    orders = Sale.objects.filter(
        company=company, 
        payment_status='pending'
    ).prefetch_related('items', 'customer').select_related('assigned_to').order_by('-sale_date')
    
    total_pending = orders.count()
    total_revenue = sum(order.net_amount for order in orders)
    
    # 🔥 HAKIKISHA LOGIC HII INAFANYA KAZI 🔥
    user = request.user
    is_admin = (
        user.is_superuser or
        getattr(user, 'is_company_admin', False) or
        getattr(user, 'role', '') == 'company_admin' or
        getattr(user, 'role', '') == 'super_admin' or
        user.is_staff
    )

    context = {
        'orders': orders,
        'total_pending': total_pending,
        'total_revenue': total_revenue,
        'is_admin': is_admin,
    }
    return render(request, 'epa/orders.html', context)


@login_required
@require_POST
def pick_order(request, sale_id):
    """Assign the order to the current user (picked)."""
    company = getattr(request, 'current_company', None)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company'})

    try:
        sale = Sale.objects.get(id=sale_id, company=company)
        
        # Angalia kama oda imekwisha pickiwa
        if sale.assigned_to and sale.assigned_to != request.user:
            return JsonResponse({
                'success': False, 
                'error': f'Order already picked by {sale.assigned_to.get_full_name() or sale.assigned_to.username}'
            })
        
        sale.assigned_to = request.user
        sale.assigned_at = timezone.now()
        sale.save()
        
        return JsonResponse({
            'success': True, 
            'message': 'Order picked! You are now responsible for following up.',
            'assigned_to': request.user.get_full_name() or request.user.username
        })
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'})


@login_required
@require_POST
def unpick_order(request, sale_id):
    """Release the order (admin only)."""
    user = request.user
    if not (user.is_superuser or getattr(user, 'is_company_admin', False) or getattr(user, 'role', '') in ['company_admin', 'super_admin']):
        return JsonResponse({'success': False, 'error': 'Only admins can unpick orders'})

    company = getattr(request, 'current_company', None)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company'})

    try:
        sale = Sale.objects.get(id=sale_id, company=company)
        sale.assigned_to = None
        sale.assigned_at = None
        sale.save()
        return JsonResponse({'success': True, 'message': 'Order released to pool.'})
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'})


@login_required
@require_POST
def mark_order_followed_up(request, sale_id):
    """Mark a picked order as followed up (paid)."""
    company = getattr(request, 'current_company', None)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company'})

    try:
        sale = Sale.objects.get(id=sale_id, company=company)
        
        # Ruhusu tu mtu aliyepick au admin
        user = request.user
        is_admin = (
            user.is_superuser or 
            getattr(user, 'is_company_admin', False) or 
            getattr(user, 'role', '') in ['company_admin', 'super_admin']
        )
        
        if sale.assigned_to and sale.assigned_to != user and not is_admin:
            return JsonResponse({
                'success': False, 
                'error': 'This order is being handled by someone else.'
            })
        
        sale.payment_status = 'paid'
        sale.save()
        
        return JsonResponse({'success': True, 'message': 'Order marked as followed up!'})
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'})