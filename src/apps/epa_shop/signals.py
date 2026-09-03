from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Sale
from .finance_views import update_cogs_from_sale


@receiver(post_save, sender=Sale)
def sale_post_save_handler(sender, instance, created, **kwargs):
    """
    When a sale is created or updated, update the COGS balance.
    """
    if instance.payment_status == 'paid':
        # Skip if this sale already has a COGS transaction
        if instance.cogs_transactions.exists():
            return
        
        # Update COGS from this sale
        update_cogs_from_sale(instance)