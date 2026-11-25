from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from apps.companies.models import Company
from decimal import Decimal

User = get_user_model()


class Order(models.Model):
    STATUS_CHOICES = (
        ('new', 'New'),
        ('picked', 'Picked'),
        ('confirmed', 'Confirmed'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cart_orders')
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.CASCADE, related_name='cart_orders'
    )

    order_number = models.CharField(max_length=50, unique=True, blank=True, editable=False)

    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20, db_index=True)
    customer_email = models.EmailField(blank=True)
    alternative_phone = models.CharField(max_length=20, blank=True)
    customer_city = models.CharField(max_length=100, blank=True)
    customer_address = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_method = models.CharField(max_length=20, default='cash')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    cancel_reason = models.TextField(blank=True, default='')

    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_cart_orders',
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    # PROTECT, not SET_NULL — a Sale must not disappear out from under a fulfilled order.
    sale = models.OneToOneField(
        'epa_shop.Sale', on_delete=models.PROTECT, null=True, blank=True,
        related_name='source_order',
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cart_orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'customer_phone']),
            models.Index(fields=['order_number']),
        ]

    def __str__(self):
        return f"{self.order_number} — {self.customer_name}"

    def save(self, *args, **kwargs):
        if self.order_number:
            return super().save(*args, **kwargs)

        from django.db import IntegrityError

        date_str = timezone.localdate().strftime('%Y%m%d')
        prefix = f'ORD-{date_str}-'

        last_error = None
        for attempt in range(10):
            last = (
                Order.objects
                .filter(company=self.company, order_number__startswith=prefix)
                .order_by('-order_number')
                .first()
            )

            next_num = 1
            if last:
                try:
                    next_num = int(last.order_number.rsplit('-', 1)[-1]) + 1 + attempt
                except (ValueError, IndexError):
                    next_num = 1 + attempt

            self.order_number = f"{prefix}{str(next_num).zfill(4)}"

            try:
                return super().save(*args, **kwargs)
            except IntegrityError as exc:
                last_error = exc
                self.order_number = ''
                continue

        raise last_error

    @property
    def item_count(self):
        from django.db.models import Sum
        return self.items.aggregate(t=Sum('quantity'))['t'] or 0


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE,
        limit_choices_to={
            'app_label': 'epa_shop',
            'model__in': ['phone', 'electronic', 'accessory'],
        },
    )
    object_id = models.PositiveIntegerField(db_index=True)
    product = GenericForeignKey('content_type', 'object_id')

    item_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'cart_order_items'
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return f"{self.quantity}× {self.item_name}"