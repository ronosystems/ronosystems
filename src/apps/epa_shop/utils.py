# apps/epa_shop/utils.py

from django.contrib.contenttypes.models import ContentType
from .models import StockMovement
import uuid

def record_stock_movement(product, movement_type, quantity, previous_quantity, new_quantity, 
                          branch=None, unit=None, reference_id=None, reference_model=None, 
                          notes="", performed_by=None):
    """
    Record a stock movement for any product type.
    
    Args:
        product: The product instance (Phone, Electronic, or Accessory)
        movement_type: One of StockMovement.MOVEMENT_TYPES
        quantity: The quantity moved (positive for in, negative for out)
        previous_quantity: Quantity before the movement
        new_quantity: Quantity after the movement
        branch: Branch object (optional)
        unit: Unit object (optional)
        reference_id: Reference ID (e.g., sale_id, purchase_order_id)
        reference_model: Reference model name (e.g., 'Sale', 'PurchaseOrder')
        notes: Additional notes
        performed_by: User who performed the action
    """
    if not product or not product.company:
        return
    
    # Get content type for the product
    content_type = ContentType.objects.get_for_model(product)
    
    # Generate reference_id if not provided
    if not reference_id:
        reference_id = f"{movement_type}_{uuid.uuid4().hex[:8]}"
    
    # Set reference_model if not provided
    if not reference_model:
        reference_model = product.__class__.__name__
    
    # Create the stock movement
    movement = StockMovement.objects.create(
        company=product.company,
        branch=branch or getattr(product, 'branch', None),
        content_type=content_type,
        object_id=product.id,
        product=product,
        unit=unit,
        movement_type=movement_type,
        quantity=quantity,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        reference_id=reference_id,
        reference_model=reference_model,
        notes=notes,
        performed_by=performed_by
    )
    
    return movement