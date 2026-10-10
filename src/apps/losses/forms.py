from django import forms
from .models import LossReturn


class LossReturnForm(forms.ModelForm):
    class Meta:
        model = LossReturn
        fields = [
            'category',
            'refund_type',
            'product_name',
            'product_model',
            'description',
            'amount',
            'cost_amount',
            'quantity',
            'customer_name',
            'customer_phone',
            'notes',
            # NEW — sale barcode linkage
            'sale',
            'sale_barcode',
        ]
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_category',
            }),
            'refund_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_refund_type',
            }),
            'product_name': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_product_name',
                'placeholder': 'e.g. Samsung Galaxy A15',
            }),
            'product_model': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_product_model',
                'placeholder': 'e.g. SM-A155F',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'id': 'id_description',
                'rows': 3,
                'placeholder': 'Describe the return / loss…',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'id': 'id_amount',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'cost_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'id': 'id_cost_amount',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'readonly': 'readonly',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'id': 'id_quantity',
                'min': '1',
                'value': '1',
            }),
            'customer_name': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_customer_name',
                'placeholder': 'Customer name (if applicable)',
            }),
            'customer_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_customer_phone',
                'placeholder': '07XX XXX XXX',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'id': 'id_notes',
                'rows': 2,
                'placeholder': 'Any additional notes…',
            }),

            # ── NEW: Sale linkage widgets ──
            'sale': forms.HiddenInput(attrs={
                'id': 'id_sale_id',
            }),
            'sale_barcode': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_sale_barcode',
                'placeholder': 'Scan or type barcode (e.g. BAR-20261010-000001)',
                'autocomplete': 'off',
                'autofocus': 'autofocus',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        refund_type = cleaned.get('refund_type')
        amount = cleaned.get('amount') or 0
        cost_amount = cleaned.get('cost_amount') or 0
        quantity = cleaned.get('quantity') or 1

        # ── Existing validation ──
        if category in LossReturn.RETURN_STYLE_CATEGORIES:
            if not amount or amount <= 0:
                self.add_error('amount', 'Enter the selling amount.')

        if category in LossReturn.LOSS_STYLE_CATEGORIES:
            if not cost_amount or cost_amount <= 0:
                self.add_error('cost_amount', 'Cost amount is required for losses.')

        if category in ('refund', 'return') and not refund_type:
            self.add_error('refund_type', 'Select how the customer was compensated.')

        if quantity < 1:
            self.add_error('quantity', 'Quantity must be at least 1.')

        # ── NEW: sale barcode validation ──
        sale = cleaned.get('sale')
        barcode = (cleaned.get('sale_barcode') or '').strip()

        if barcode and not sale:
            self.add_error(
                'sale_barcode',
                f'Barcode "{barcode}" is not linked to any sale. '
                f'Click "Look up" to verify before saving.',
            )

        # If a sale was linked, make sure it belongs to the same company
        # as the LossReturn being saved. (`self.instance.company` is set
        # in the view before form.save(commit=False) is called — but on
        # POST the instance may not yet have a company, so we check
        # defensively against cleaned data.)
        if sale and self.instance.company_id and sale.company_id != self.instance.company_id:
            self.add_error(
                'sale',
                'The linked sale does not belong to this company.',
            )

        return cleaned