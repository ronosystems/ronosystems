# /home/rs/ronosystems/src/apps/epa_shop/cart_views.py
#
# STAFF-FACING views only. Customers never hit this file —
# they use apps/cart_orders/views.py.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from .models import (
    Sale, SaleItem, Customer,
    BranchStock, Order,                     # ← Order lives in epa_shop/models.py (Path B)
)


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
    """Staff view — shows all open (not fulfilled/cancelled) online orders."""
    company = _get_company(request)
    if not company:
        return redirect('/')

    orders = (
        Order.objects
        .filter(company=company)
        .exclude(status__in=('fulfilled', 'cancelled'))
        .prefetch_related('items')
        .select_related('assigned_to')
        .order_by('-created_at')
    )

    context = {
        'orders': orders,
        'total_pending': orders.count(),
        'total_revenue': sum(o.total_amount for o in orders),
        'is_admin': _is_admin(request.user),
    }
    return render(request, 'epa/orders.html', context)


# ============================================
# 2. PICK / UNPICK / FOLLOW-UP
# ============================================

@login_required
@require_POST
def pick_order(request, order_id):
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

    order.assigned_to = request.user
    order.assigned_at = timezone.now()
    if order.status == 'new':
        order.status = 'picked'
    order.save(update_fields=['assigned_to', 'assigned_at', 'status'])

    return JsonResponse({
        'success': True,
        'message': 'Order picked! You are now responsible for following up.',
        'assigned_to': request.user.get_full_name() or request.user.username,
    })


@login_required
@require_POST
def unpick_order(request, order_id):
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
    """Staff reached the customer — sets status='confirmed'. No Sale yet."""
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
# 3. CONFIRM → creates the Sale (the ONLY place this happens)
# ============================================

@login_required
@require_POST
def confirm_order(request, order_id):
    from .sale_views import _snapshot_cogs
    from .utils import record_stock_movement
    from django.db.models import F

    company = _get_company(request)
    order = Order.objects.filter(id=order_id, company=company).first()
    if not order:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)

    if order.status not in ('picked', 'confirmed'):
        return JsonResponse(
            {'success': False, 'error': 'Order must be picked/confirmed first.'},
            status=400,
        )

    if order.sale_id:
        return JsonResponse(
            {'success': False,
             'error': f'Order already converted to sale {order.sale.company_sale_id}.'},
            status=400,
        )

    try:
        with transaction.atomic():
            # 1. Customer (upsert by phone)
            customer, _ = Customer.objects.get_or_create(
                company=company,
                phone=order.customer_phone,
                defaults={
                    'name': order.customer_name,
                    'email': order.customer_email,
                    'alternative_phone': order.alternative_phone,
                    'city': order.customer_city,
                    'address': order.customer_address,
                    'is_active': True,
                },
            )

            # 2. Sale
            sale = Sale.objects.create(
                company=company,
                branch=order.branch,
                customer=customer,
                customer_name=order.customer_name,
                customer_phone=order.customer_phone,
                customer_email=order.customer_email,
                total_amount=order.subtotal,
                net_amount=order.total_amount,
                payment_status='paid',
                payment_method=order.payment_method,
                sold_by=request.user,
                sale_date=timezone.now(),
            )

            # 3. Items + stock mutation + COGS snapshot
            running_cogs = Decimal('0.00')
            for oi in order.items.select_related('content_type'):
                product = oi.product
                if product is None:
                    continue

                cat = oi.content_type.model  # 'phone' | 'electronic' | 'accessory'

                # -- previous stock snapshot
                if cat in ('phone', 'electronic'):
                    prev_qty = product.units.filter(status='available').count()
                else:
                    prev_qty = product.total_quantity_in_stock

                # -- decrement product total
                if cat in ('phone', 'electronic'):
                    product.total_quantity_in_stock = max(0, prev_qty - oi.quantity)
                else:
                    product.total_quantity_in_stock = max(
                        0, product.total_quantity_in_stock - oi.quantity
                    )
                product.save(update_fields=['total_quantity_in_stock'])

                # -- decrement branch stock (atomic)
                BranchStock.objects.filter(
                    company=company,
                    branch=order.branch,
                    content_type=oi.content_type,
                    object_id=oi.object_id,
                ).update(quantity_in_stock=F('quantity_in_stock') - oi.quantity)

                # -- freeze COGS for this line
                unit_cost, line_cogs = _snapshot_cogs(product, oi.unit_price, oi.quantity)

                SaleItem.objects.create(
                    sale=sale,
                    content_type=oi.content_type,
                    object_id=oi.object_id,
                    item_name=oi.item_name,
                    quantity=oi.quantity,
                    unit_price=oi.unit_price,
                    total_price=oi.total_price,
                    unit_cost=unit_cost,
                    cogs_amount=line_cogs,
                )
                running_cogs += line_cogs

                # -- movement log
                record_stock_movement(
                    product=product,
                    movement_type='sale',
                    quantity=-oi.quantity,
                    previous_quantity=prev_qty,
                    new_quantity=product.total_quantity_in_stock,
                    branch=order.branch,
                    notes=f"Online order {order.order_number}",
                    performed_by=request.user,
                )

            # 4. Roll up sale COGS + link order
            sale.cogs_amount = running_cogs
            sale.save(update_fields=['cogs_amount'])

            order.sale = sale
            order.status = 'fulfilled'
            order.save(update_fields=['sale', 'status'])

        return JsonResponse({
            'success': True,
            'sale_id': sale.id,
            'sale_number': sale.company_sale_id,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)