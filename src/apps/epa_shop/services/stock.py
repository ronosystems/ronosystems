# apps/epa_shop/services/stock.py

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.epa_shop.models import (
    BranchStock,
    DiscontinuedProduct,
    Electronic,
    Phone,
    StockMovement,
    StockTransfer,
    Unit,
)


# ============================================================
# HELPERS
# ============================================================

def _ct(product):
    """ContentType for a product instance."""
    return ContentType.objects.get_for_model(product)


def _live_available_count(product):
    """
    Live available-unit count for a product.

    Phones and Electronics are tracked as Unit rows (status='available').
    Accessories use the cached BranchStock total.

    IMPORTANT: this must stay in sync with _live_stock_for() in the
    inventory views — both must return the same number so the
    discontinue guard and the button state agree.
    """
    if isinstance(product, Phone):
        return Unit.objects.filter(phone=product, status='available').count()
    if isinstance(product, Electronic):
        return Unit.objects.filter(electronic=product, status='available').count()
    return getattr(product, 'total_quantity_in_stock', 0)


def _refresh_total(product):
    """Update the cached company-wide total on the product row."""
    from django.db.models import Sum

    total = (
        BranchStock.objects
        .filter(content_type=_ct(product), object_id=product.pk)
        .aggregate(t=Sum('quantity_in_stock'))['t']
    ) or 0

    # Write directly to the DB to avoid recursive saves.
    type(product).objects.filter(pk=product.pk).update(
        total_quantity_in_stock=total
    )
    product.total_quantity_in_stock = total


# ============================================================
# DISCONTINUE / REACTIVATE
# ============================================================

@transaction.atomic
def discontinue_product(product, user, *, reason='end_of_life', notes='',
                        replacement=None, replacement_code=''):
    """
    Retire a product company-wide. Idempotent.

    replacement: a product instance (Phone/Electronic/Accessory), OR
    replacement_code: a product_code string to look up. If both are
    given, `replacement` wins.

    A replacement is OPTIONAL and purely informational — it does not
    change stock, sales or anything else. It just records "this was
    replaced by X" for reporting.
    """
    company = product.company

    # ── Resolve replacement from a code if one was supplied ──
    if replacement is None and replacement_code:
        for model in (Phone, Electronic, Accessory):
            replacement = model.objects.filter(
                company=company, product_code=replacement_code,
            ).first()
            if replacement:
                break

    # ── Guard: a product cannot replace itself ──
    if replacement is not None and replacement.pk == product.pk \
            and type(replacement) is type(product):
        raise ValueError("A product cannot be its own replacement.")

    # ── Lock + live stock check (unchanged) ──
    product = type(product).objects.select_for_update().get(pk=product.pk)

    remaining = _live_available_count(product)
    if remaining > 0:
        raise ValueError(
            f"Cannot discontinue '{product.name}': {remaining} unit(s) still "
            f"in stock. Sell, write off, or transfer them first."
        )

    record, created = DiscontinuedProduct.objects.get_or_create(
        company=company,
        content_type=_ct(product),
        object_id=product.pk,
        defaults={
            'reason': reason,
            'notes': notes,
            'discontinued_by': user,
            'replacement_content_type': (
                ContentType.objects.get_for_model(replacement)
                if replacement else None
            ),
            'replacement_object_id': replacement.pk if replacement else None,
        },
    )

    # If the record already existed and the caller supplied a
    # replacement now, attach it (idempotent update).
    if not created and replacement and not record.replacement_object_id:
        record.set_replacement(replacement)

    if product.is_active:
        product.is_active = False
        product.save(update_fields=['is_active', 'updated_at'])

    return record


@transaction.atomic
def reactivate_product(product, user):
    """
    Reverse a discontinuation (e.g. you found old stock).
    Removes the DiscontinuedProduct record and re-enables the product.
    """
    DiscontinuedProduct.objects.filter(
        company=product.company,
        content_type=_ct(product),
        object_id=product.pk,
    ).delete()

    product.is_active = True
    product.save(update_fields=['is_active', 'updated_at'])


# ============================================================
# STOCK ADJUSTMENT
# ============================================================

@transaction.atomic
def adjust_stock(product, branch, delta, user, movement_type='adjustment',
                 reference_id='', notes='', min_level=None, max_level=None):
    """
    Atomically change stock at a branch and log the movement.

    delta > 0 -> receipt
    delta < 0 -> issue (raises if insufficient)
    """
    ct = _ct(product)

    # Lock the row (or create it) so concurrent adjustments can't race.
    stock = (
        BranchStock.objects
        .select_for_update()
        .filter(branch=branch, content_type=ct, object_id=product.pk)
        .first()
    )
    if stock is None:
        stock = BranchStock.objects.create(
            company=product.company,
            branch=branch,
            content_type=ct,
            object_id=product.pk,
            quantity_in_stock=0,
            minimum_stock_level=(min_level if min_level is not None else 2),
            maximum_stock_level=(max_level if max_level is not None else 100),
        )

    prev = stock.quantity_in_stock
    new = prev + delta
    if new < 0:
        raise ValueError(
            f"Insufficient stock for {product} at {branch}. "
            f"Have {prev}, need {-delta}."
        )

    stock.quantity_in_stock = new
    if min_level is not None:
        stock.minimum_stock_level = min_level
    if max_level is not None:
        stock.maximum_stock_level = max_level
    stock.save(update_fields=[
        'quantity_in_stock',
        'minimum_stock_level',
        'maximum_stock_level',
        'updated_at',
    ])

    StockMovement.objects.create(
        company=product.company,
        branch=branch,
        content_type=ct,
        object_id=product.pk,
        movement_type=movement_type,
        quantity=delta,
        previous_quantity=prev,
        new_quantity=new,
        reference_id=reference_id,
        notes=notes,
        performed_by=user,
    )

    _refresh_total(product)
    return stock


# ============================================================
# TRANSFERS
# ============================================================

@transaction.atomic
def initiate_transfer(product, from_branch, to_branch, quantity, user, notes=''):
    """
    Takes stock OUT of the source branch and creates a pending transfer.
    The destination branch does NOT receive the stock yet.
    """
    if quantity <= 0:
        raise ValueError("Transfer quantity must be positive.")
    if from_branch == to_branch:
        raise ValueError("Source and destination branches must differ.")

    # 1. Deduct from source immediately.
    adjust_stock(
        product, from_branch, -quantity, user,
        movement_type='transfer_out',
        notes=f"Transfer to {to_branch.name} (In Transit)",
    )

    # 2. Create the pending transfer record.
    transfer = StockTransfer.objects.create(
        company=product.company,
        from_branch=from_branch,
        to_branch=to_branch,
        content_type=_ct(product),
        object_id=product.pk,
        quantity=quantity,
        status='in_transit',
        notes=notes,
        created_by=user,
    )
    return transfer


@transaction.atomic
def receive_transfer(transfer, user):
    """
    Completes a pending transfer by adding stock to the destination branch.
    """
    if transfer.status != 'in_transit':
        raise ValueError(f"Transfer {transfer.transfer_number} is not in transit.")

    product = transfer.product

    # 1. Add to destination.
    adjust_stock(
        product, transfer.to_branch, +transfer.quantity, user,
        movement_type='transfer_in',
        notes=f"Received from {transfer.from_branch.name}",
    )

    # 2. Mark transfer as completed.
    transfer.status = 'completed'
    transfer.completed_by = user
    transfer.completed_at = timezone.now()
    transfer.save(update_fields=['status', 'completed_by', 'completed_at'])
    return transfer


@transaction.atomic
def _complete_transfer(transfer, user):
    """Legacy pending -> completed path (single-step transfer)."""
    if transfer.status != 'pending':
        raise ValueError(f"Transfer {transfer.transfer_number} is not pending.")

    product = transfer.product

    # 1. Issue from source.
    adjust_stock(
        product, transfer.from_branch, -transfer.quantity, user,
        movement_type='transfer',
        reference_id=transfer.transfer_number,
        notes=f"Transfer to {transfer.to_branch}",
    )
    # 2. Receive at destination.
    adjust_stock(
        product, transfer.to_branch, +transfer.quantity, user,
        movement_type='transfer',
        reference_id=transfer.transfer_number,
        notes=f"Transfer from {transfer.from_branch}",
    )

    transfer.status = 'completed'
    transfer.completed_by = user
    transfer.completed_at = timezone.now()
    transfer.save(update_fields=['status', 'completed_by', 'completed_at'])


def complete_transfer(transfer, user):
    """Public entry point for approving a pending transfer later."""
    with transaction.atomic():
        _complete_transfer(transfer, user)
    return transfer


# ============================================================
# RECEIPTS & SALES
# ============================================================

@transaction.atomic
def receive_stock(product, branch, quantity, user, unit_cost=None,
                  reference_id='', notes=''):
    """Purchase receipt / initial stock load at a branch."""
    return adjust_stock(
        product, branch, +quantity, user,
        movement_type='purchase',
        reference_id=reference_id,
        notes=notes,
    )


@transaction.atomic
def sell_from_branch(product, branch, quantity, sale, user):
    """
    Issue stock for a sale. Call this inside the Sale creation transaction.
    Raises if the branch doesn't have enough.
    """
    return adjust_stock(
        product, branch, -quantity, user,
        movement_type='sale',
        reference_id=sale.company_sale_id,
        notes=f"Sale to {sale.customer_name}",
    )