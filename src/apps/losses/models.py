from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from apps.companies.models import Company

User = get_user_model()


# ============================================
# LOSS / RETURN RECORD
# ============================================

class LossReturn(models.Model):
    """
    Unified record for customer returns, refunds, discounts,
    write-offs, damages, and shrinkage.

    Two flavours of entry:
      • RETURN_STYLE  (refund, return, discount, writeoff)
            → uses `amount` (what the customer paid / was owed)
            → has `refund_type` for refunds & returns
      • LOSS_STYLE    (damage, shrinkage)
            → uses `cost_amount` (auto-filled from product purchase_price)
    """

    # ─────────────────────────────────────────────
    # CATEGORY
    # ─────────────────────────────────────────────
    CATEGORY_CHOICES = (
        ('refund',     'Refund — Pesa uliyomrudishia mteja'),
        ('return',     'Return — Bidhaa iliyorudishwa'),
        ('discount',   'Discount / Allowance — Punguzo ulilotoa'),
        ('writeoff',   'Write-off — Deni lililoshindikana kulipwa'),
        ('damage',     'Damage / Spoilage — Bidhaa iliyoharibika'),
        ('shrinkage',  'Shrinkage — Wizi / Upotevu wa stock'),
    )

    # Categories that use selling price (customer-facing)
    RETURN_STYLE_CATEGORIES = ('refund', 'return', 'discount', 'writeoff')

    # Categories that use cost price (internal loss)
    LOSS_STYLE_CATEGORIES = ('damage', 'shrinkage')

    # ─────────────────────────────────────────────
    # REFUND SUB-TYPE (only for refund & return)
    # ─────────────────────────────────────────────
    REFUND_TYPE_CHOICES = (
        ('product_replacement', 'Product Replacement'),
        ('amount_refunded',     'Amount Refunded'),
    )

    # ─────────────────────────────────────────────
    # CORE FIELDS
    # ─────────────────────────────────────────────
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='loss_return_records',
    )
    branch = models.ForeignKey(
        'company.Branch',
        on_delete=models.CASCADE,
        related_name='loss_return_records',
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
    )

    # For refunds/returns, this tells us HOW the customer was compensated
    refund_type = models.CharField(
        max_length=25,
        choices=REFUND_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Only for Refund / Return categories",
    )

    # ─────────────────────────────────────────────
    # PRODUCT (optional — used for refunds/returns/damages/shrinkage)
    # ─────────────────────────────────────────────
    product_name = models.CharField(max_length=200, blank=True)
    product_model = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    # ─────────────────────────────────────────────
    # AMOUNTS
    # ─────────────────────────────────────────────
    # For return-style: what the customer paid OR what was refunded
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Selling amount (for refunds/returns/discounts/writeoffs)",
    )

    # For loss-style: purchase cost of the lost/damaged item
    cost_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Purchase cost (for damages/shrinkage)",
    )

    quantity = models.PositiveIntegerField(default=1)

    # ─────────────────────────────────────────────
    # CUSTOMER (optional — used for refunds/discounts/writeoffs)
    # ─────────────────────────────────────────────
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)

    # ─────────────────────────────────────────────
    # META
    # ─────────────────────────────────────────────
    reference = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated on save",
    )
    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loss_return_records',
    )


    # ============================================
    # VERIFICATION / LOCK
    # ============================================
    is_verified = models.BooleanField(
        default=False,
        help_text="Set to True by company admin / stock controller to lock the record.",
    )
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_loss_returns',
        help_text="User who verified and locked this record.",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the record was verified.",
    )
    verification_notes = models.TextField(
        blank=True,
        help_text="Optional notes added during verification.",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'losses_loss_return'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'branch', 'created_at']),
            models.Index(fields=['company', 'category']),
            models.Index(fields=['reference']),
        ]
        verbose_name = 'Loss / Return Record'
        verbose_name_plural = 'Loss / Return Records'

    def __str__(self):
        return f"{self.get_category_display()} — {self.reference} — KES {self.effective_amount:,.2f}"

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────
    @property
    def is_return_style(self):
        return self.category in self.RETURN_STYLE_CATEGORIES

    @property
    def is_loss_style(self):
        return self.category in self.LOSS_STYLE_CATEGORIES

    @property
    def effective_amount(self):
        """Return whichever amount is relevant for this category."""
        if self.is_loss_style:
            return self.cost_amount * self.quantity
        return self.amount * self.quantity

    def save(self, *args, **kwargs):
        # Auto-generate reference like LR-20261003-0001
        if not self.reference:
            prefix = 'LR'
            date_str = timezone.now().strftime('%Y%m%d')
            last = LossReturn.objects.filter(
                company=self.company,
                reference__startswith=f'{prefix}-{date_str}'
            ).order_by('-reference').first()

            if last:
                try:
                    n = int(last.reference.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            else:
                n = 1

            self.reference = f'{prefix}-{date_str}-{n:04d}'

        super().save(*args, **kwargs)