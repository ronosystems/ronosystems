# /home/rs/ronosystems/src/apps/cart_orders/staff_views.py
#
# AUTHENTICATED staff views for managing customer orders:
#   order_list → pick → follow-up → confirm (creates Sale)
# Every view requires @login_required.

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.shortcuts import render, redirect
from apps.epa_shop.models import Unit
from decimal import Decimal
from .models import Order
import json



# ============================================
# HELPERS
# ============================================

def _is_admin(user):
    return (
        user.is_superuser
        or getattr(user, 'is_company_admin', False)
        or getattr(user, 'role', '') in ('company_admin', 'super_admin')
        or user.is_staff
    )


def _get_company(request):
    return getattr(request, 'current_company', None)


# ============================================
# 1. ORDER QUEUE
# ============================================

@login_required
def order_list(request):
    """
    Staff view — shows active orders.
    Admins see Fulfilled and Cancelled orders too for tracking.
    """
    company = _get_company(request)
    if not company:
        return redirect('/')

    is_admin = _is_admin(request.user)

    if is_admin:
        # Admins see everything (active, fulfilled, cancelled)
        orders = (
            Order.objects
            .filter(company=company)
            .prefetch_related('items')
            .select_related('assigned_to')
            .order_by('-created_at')
        )
    else:
        # Regular staff only see active orders
        orders = (
            Order.objects
            .filter(company=company)
            .filter(status__in=['new', 'picked', 'confirmed'])
            .prefetch_related('items')
            .select_related('assigned_to')
            .order_by('-created_at')
        )

    context = {
        'orders':        orders,
        'total_pending': orders.filter(status__in=['new', 'picked', 'confirmed']).count(),
        'total_revenue': sum(o.total_amount for o in orders if o.status not in ['cancelled', 'fulfilled']),
        'is_admin':      is_admin,
    }
    return render(request, 'cart_orders/staff_orders.html', context)

# ============================================
# 2. PICK / UNPICK / FOLLOW-UP
# ============================================

@login_required
@require_POST
def pick_order(request, order_id):
    """Assign the order to the current user."""
    company = _get_company(request)
    if not company:
        return JsonResponse({'success': False, 'error': 'No company'}, status=400)

    order = Order.objects.filter(id=order_id, company=company).first()
    if not order:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)

    if order.assigned_to and order.assigned_to != request.user:
        name = order.assigned_to.get_full_name() or order.assigned_to.username
        return JsonResponse(
            {'success': False, 'error': f'Order already picked by {name}'},
            status=409,
        )

    if order.status == 'cancelled':
        return JsonResponse(
            {'success': False, 'error': 'Cannot pick a cancelled order.'},
            status=400,
        )

    order.assigned_to = request.user
    order.assigned_at = timezone.now()
    if order.status == 'new':
        order.status = 'picked'
    order.save(update_fields=['assigned_to', 'assigned_at', 'status'])

    return JsonResponse({
        'success':     True,
        'message':     'Order picked! You are now responsible for following up.',
        'assigned_to': request.user.get_full_name() or request.user.username,
    })


@login_required
@require_POST
def unpick_order(request, order_id):
    """Release the order back to the pool (admin only)."""
    if not _is_admin(request.user):
        return JsonResponse(
            {'success': False, 'error': 'Only admins can unpick orders'},
            status=403,
        )

    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()
    if not order:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)

    order.assigned_to = None
    order.assigned_at = None
    if order.status == 'picked':
        order.status = 'new'
    order.save(update_fields=['assigned_to', 'assigned_at', 'status'])
    return JsonResponse({'success': True, 'message': 'Order released to pool.'})


@login_required
@require_POST
def mark_order_followed_up(request, order_id):
    """Staff contacted the customer — status → 'confirmed'. No Sale yet."""
    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()
    if not order:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)

    if order.assigned_to and order.assigned_to != request.user and not _is_admin(request.user):
        return JsonResponse(
            {'success': False, 'error': 'This order is being handled by someone else.'},
            status=403,
        )

    order.status = 'confirmed'
    order.save(update_fields=['status'])
    return JsonResponse({'success': True, 'message': 'Order marked as followed up!'})


# ============================================
# 3. CONFIRM ORDER → creates the Sale
# ============================================

@login_required
@require_POST
def confirm_order(request, order_id):
    from apps.epa_shop.models import Sale, SaleItem, Customer, BranchStock, Unit
    from apps.epa_shop.sale_views import _snapshot_cogs
    from apps.epa_shop.utils import record_stock_movement

    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()
    
    if not order or order.status not in ('picked', 'confirmed') or order.sale_id:
        return JsonResponse({'success': False, 'error': 'Invalid order.'}, status=400)

    try:
        data = json.loads(request.body)
        payment_status = data.get('payment_status', 'paid')
        selected_units = data.get('selected_units', {})
        submitted_quantities = data.get('quantities', {})  # <-- ADD THIS

        with transaction.atomic():
            customer, _ = Customer.objects.get_or_create(
                company=company, phone=order.customer_phone,
                defaults={'name': order.customer_name, 'email': order.customer_email, 'is_active': True},
            )

            # Recalculate totals based on submitted quantities
            new_subtotal = Decimal('0.00')
            for oi in order.items.select_related('content_type'):
                qty = int(submitted_quantities.get(str(oi.id), oi.quantity))
                new_subtotal += oi.unit_price * qty

            sale = Sale.objects.create(
                company=company, branch=order.branch, customer=customer,
                customer_name=order.customer_name, customer_phone=order.customer_phone,
                customer_email=order.customer_email, total_amount=new_subtotal,
                net_amount=new_subtotal, payment_status=payment_status,
                payment_method=order.payment_method, sold_by=request.user,
                sale_date=timezone.now(),
            )

            running_cogs = Decimal('0.00')

            for oi in order.items.select_related('content_type'):
                product = oi.product
                if product is None:
                    continue

                # Get the submitted quantity for this item
                qty = int(submitted_quantities.get(str(oi.id), oi.quantity))  # <-- USE SUBMITTED QTY

                cat = oi.content_type.model
                
                # Handle Unit selection for Phones/Electronics
                if cat in ('phone', 'electronic'):
                    unit_ids = selected_units.get(str(oi.id), [])
                    if len(unit_ids) != qty:  # <-- CHECK AGAINST SUBMITTED QTY
                        raise Exception(
                            f"Please select exactly {qty} unit(s) for {product.name}. "
                            f"You selected {len(unit_ids)}."
                        )
                    
                    for u_id in unit_ids:
                        unit = Unit.objects.get(id=u_id, status='available')
                        unit.status = 'sold'
                        unit.owner_name = order.customer_name
                        unit.owner_phone = order.customer_phone
                        unit.sold_date = timezone.now()
                        unit.save()
                else:
                    # Bulk accessories
                    product.total_quantity_in_stock = max(0, product.total_quantity_in_stock - qty)

                product.save(update_fields=['total_quantity_in_stock'])

                BranchStock.objects.filter(
                    company=company, branch=order.branch,
                    content_type=oi.content_type, object_id=oi.object_id,
                ).update(quantity_in_stock=F('quantity_in_stock') - qty)  # <-- USE SUBMITTED QTY

                unit_cost, line_cogs = _snapshot_cogs(product, oi.unit_price, qty)  # <-- USE SUBMITTED QTY

                SaleItem.objects.create(
                    sale=sale, content_type=oi.content_type, object_id=oi.object_id,
                    item_name=oi.item_name, quantity=qty,  # <-- USE SUBMITTED QTY
                    unit_price=oi.unit_price, total_price=oi.unit_price * qty,  # <-- USE SUBMITTED QTY
                    unit_cost=unit_cost, cogs_amount=line_cogs,
                )
                running_cogs += line_cogs

            sale.cogs_amount = running_cogs
            sale.save(update_fields=['cogs_amount'])

            order.sale = sale
            order.status = 'fulfilled'
            order.save(update_fields=['sale', 'status'])

        return JsonResponse({'success': True, 'sale_id': sale.id, 'sale_number': sale.company_sale_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



# ============================================
# 4. CANCEL ORDER — requires reason
# ============================================

@login_required
@require_POST
def cancel_order(request, order_id):
    """
    Cancel an order (e.g. customer changed mind).
    Requires a mandatory cancellation reason.
    """
    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()

    if not order:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)

    # Only admins or the person who picked the order can cancel it
    if order.assigned_to and order.assigned_to != request.user and not _is_admin(request.user):
        return JsonResponse(
            {'success': False, 'error': 'You can only cancel orders assigned to you.'},
            status=403,
        )

    if order.status == 'fulfilled':
        return JsonResponse(
            {'success': False, 'error': 'Cannot cancel an order that is already a Sale.'},
            status=400,
        )

    if order.status == 'cancelled':
        return JsonResponse(
            {'success': False, 'error': 'This order is already cancelled.'},
            status=400,
        )

    # ---- Parse mandatory cancel reason ----
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse(
            {'success': False, 'error': 'Invalid request body.'},
            status=400,
        )

    reason = (data.get('reason') or '').strip()
    if not reason:
        return JsonResponse(
            {'success': False, 'error': 'A cancellation reason is required.'},
            status=400,
        )

    order.status = 'cancelled'
    order.cancel_reason = reason
    order.save(update_fields=['status', 'cancel_reason'])

    return JsonResponse({'success': True, 'message': 'Order has been cancelled.'})


@login_required
@require_POST
def delete_order(request, order_id):
    # Add your admin check here
    if not request.user.is_superuser and request.user.role != 'company_admin':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    try:
        order = Order.objects.get(id=order_id)
        order.delete()
        return JsonResponse({'success': True})
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============================================
# 5. DELETE CANCELLED ORDER — admin only
# ============================================

@login_required
@require_POST
def delete_cancelled_order(request, order_id):
    """
    Admin permanently deletes a cancelled order after verification.
    This is the final cleanup step — cancelled orders stay visible
    for admin verification until this is called.
    """
    if not _is_admin(request.user):
        return JsonResponse(
            {'success': False, 'error': 'Only admins can delete orders.'},
            status=403,
        )

    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company, status='cancelled').first()

    if not order:
        return JsonResponse(
            {'success': False, 'error': 'Cancelled order not found.'},
            status=404,
        )

    order_number = order.order_number
    order.delete()

    return JsonResponse({
        'success': True,
        'message': f'Order {order_number} permanently deleted.',
    })


@login_required
@require_POST
def approve_cancellation(request, order_id):
    """Admin approves a cancellation and permanently deletes the order."""
    if not _is_admin(request.user):
        return JsonResponse(
            {'success': False, 'error': 'Only admins can approve cancellations.'},
            status=403,
        )

    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company, status='cancelled').first()

    if not order:
        return JsonResponse(
            {'success': False, 'error': 'Cancelled order not found.'},
            status=404,
        )

    order_number = order.order_number
    order.delete()

    return JsonResponse({
        'success': True,
        'message': f'Cancellation approved. Order {order_number} has been removed.',
    })



@login_required
def search_units_api(request):
    """AJAX endpoint to search available units by IMEI/Serial"""
    query = request.GET.get('q', '').strip()
    company = _get_company(request)
    
    if len(query) < 2 or not company:
        return JsonResponse({'results': []})

    # Search across both Phone and Electronic units
    units = Unit.objects.filter(
        Q(identifier__icontains=query) | Q(identifier__istartswith=query),
        status='available'
    ).select_related('phone', 'electronic')[:20] # Limit to 20 results

    results = []
    for u in units:
        # Filter by company to prevent cross-tenant data leaks
        if (u.phone and u.phone.company == company) or (u.electronic and u.electronic.company == company):
            product_name = u.phone.name if u.phone else u.electronic.name
            results.append({
                'id': u.id,
                'text': f"{u.identifier} - {product_name}"
            })

    return JsonResponse({'results': results})


@login_required
def link_sale_page(request, order_id):
    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()
    
    if not order or order.status not in ('picked', 'confirmed') or order.sale_id:
        return redirect('cart-orders:order-list')

    items_data = []
    for oi in order.items.select_related('content_type'):
        product = oi.product
        available_units = []
        available_stock = 0
        
        if oi.content_type.model in ('phone', 'electronic'):
            if oi.content_type.model == 'phone':
                available_units = Unit.objects.filter(phone=product, status='available')
            else:
                available_units = Unit.objects.filter(electronic=product, status='available')
            available_stock = available_units.count()
        else:
            available_stock = product.total_quantity_in_stock
            
        items_data.append({
            'order_item': oi,
            'product': product,
            'is_serialized': oi.content_type.model in ('phone', 'electronic'),
            'available_units': available_units,
            'available_stock': available_stock,
        })

    context = {
        'order': order,
        'items_data': items_data,
    }
    return render(request, 'cart_orders/link_sale.html', context)


@login_required
@require_POST
def pay_pending_order(request, order_id):
    """
    Mark a 'Pay on Delivery' order as Paid.
    Updates the linked Sale to 'paid' and clears the pending flag.
    """
    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()

    if not order or not order.sale:
        return JsonResponse({'success': False, 'error': 'Order or linked Sale not found.'}, status=404)

    # Ensure it's actually a pending sale
    if order.sale.payment_status != 'pending':
        return JsonResponse({'success': False, 'error': 'This sale is already paid.'}, status=400)

    try:
        with transaction.atomic():
            # Update the Sale
            order.sale.payment_status = 'paid'
            order.sale.save(update_fields=['payment_status'])
            
            # Optional: Change order status so it's no longer "Fulfilled (Pending)"
            # If you want a distinct status for fulfilled+paid, you can use 'fulfilled'
            # The template will now see sale.payment_status == 'paid' and show "Completed Order"
            order.save()

        return JsonResponse({'success': True, 'message': 'Order marked as PAID.'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



@login_required
def order_archive_detail(request, order_id):
    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company, status='fulfilled').first()
    
    if not order:
        return redirect('cart-orders:order-list')

    context = {
        'order': order,
        'sale': order.sale,  # The linked Sale object
    }
    return render(request, 'cart_orders/order_archive.html', context)


    