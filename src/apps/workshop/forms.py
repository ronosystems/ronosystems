# apps/workshop/forms.py

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model

from .models import (
    JobMaterial,
    JobNote,
    JobPayment,
    TechnicianPayout,
    TechnicianRate,
    WorkshopCustomer,
    WorkshopJob,
)

User = get_user_model()


# ================================================================
# HELPERS
# ================================================================

def _style_widgets(fields, css_class='form-control'):
    """Apply a Bootstrap-ish class to a set of form fields."""
    for field in fields.values():
        widget = field.widget
        if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
            widget.attrs.setdefault('class', 'form-check-input')
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault('class', 'form-select')
        else:
            widget.attrs.setdefault('class', css_class)


def _technicians_for(company):
    """Return the technician queryset for a given company."""
    qs = User.objects.filter(role='company_technician')
    if company is not None:
        qs = qs.filter(company=company)
    return qs.order_by('first_name', 'last_name', 'username')


# ================================================================
# CUSTOMER
# ================================================================

class WorkshopCustomerForm(forms.ModelForm):
    class Meta:
        model = WorkshopCustomer
        fields = ['name', 'phone', 'email', 'address', 'notes']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_widgets(self.fields)


# ================================================================
# JOB
# ================================================================

class WorkshopJobForm(forms.ModelForm):
    """
    Create/edit a job.

    Accepts `company` and `user` kwargs from the view so we can scope
    FK dropdowns (technicians, branches) to the right company.
    """

    class Meta:
        model = WorkshopJob
        fields = [
            # Classification
            'repair_category', 'work_source', 'priority',
            # Customer
            'customer',
            # Device
            'device_name', 'device_brand', 'device_model',
            'device_serial', 'device_password', 'device_accessories',
            # Problem
            'reported_problem', 'diagnosis', 'work_summary',
            # Money — only the fields the template shows:
            #   Amount Customer to Pay   → final_amount
            #   Amount Used for Transport → transport_cost
            #   Amount Cost of Material  → actual_material_cost (read-only, auto)
            'final_amount', 'transport_cost',
            # People
            'assigned_technician', 'branch',
            # Dates
            'expected_delivery',
            # Warranty
            'warranty_days',
            # Notes
            'internal_notes',
        ]
        widgets = {
            'reported_problem': forms.Textarea(attrs={'rows': 3}),
            'diagnosis': forms.Textarea(attrs={'rows': 3}),
            'work_summary': forms.Textarea(attrs={'rows': 3}),
            'device_accessories': forms.Textarea(attrs={'rows': 2}),
            'internal_notes': forms.Textarea(attrs={'rows': 2}),
            'expected_delivery': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, company=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.user = user

        # Scope FK dropdowns
        if company is not None:
            self.fields['customer'].queryset = WorkshopCustomer.objects.filter(
                company=company
            ).order_by('name')

            # Technician pool
            self.fields['assigned_technician'].queryset = _technicians_for(company)

            # Branch pool (guard for app without company FK)
            try:
                from apps.company.models import Branch
                self.fields['branch'].queryset = Branch.objects.filter(
                    company=company
                ).order_by('name')
            except Exception:
                self.fields['branch'].queryset = self.fields['branch'].queryset.none()
        else:
            # Super-admin path: allow everything
            self.fields['customer'].queryset = WorkshopCustomer.objects.all()
            self.fields['assigned_technician'].queryset = User.objects.filter(
                role='company_technician'
            )

        # Make a few fields optional at the form level
        self.fields['customer'].required = False
        self.fields['assigned_technician'].required = False
        self.fields['branch'].required = False

        # Money fields — ensure clean numeric input
        for money_field in ('final_amount', 'transport_cost'):
            if money_field in self.fields:
                self.fields[money_field].required = False
                self.fields[money_field].widget = forms.NumberInput(
                    attrs={
                        'class': 'form-control',
                        'step': '0.01',
                        'min': '0',
                        'placeholder': '0.00',
                    }
                )

        _style_widgets(self.fields)

    def clean(self):
        cleaned = super().clean()

        work_source = cleaned.get('work_source')
        customer = cleaned.get('customer')

        # Customer walk-in requires a customer; store stock doesn't.
        if work_source == 'customer' and not customer:
            self.add_error('customer', 'A customer is required for walk-in repairs.')
        if work_source == 'store_stock' and customer:
            cleaned['customer'] = None

        # Money sanity checks — no negatives
        for field_name in ('final_amount', 'transport_cost'):
            value = cleaned.get(field_name)
            if value is not None and value < Decimal('0.00'):
                self.add_error(field_name, 'Amount cannot be negative.')

        return cleaned


class JobStatusForm(forms.Form):
    """Small form for the status transition POST."""

    status = forms.ChoiceField(choices=WorkshopJob.STATUS_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_widgets(self.fields)


# ================================================================
# MATERIAL
# ================================================================

class JobMaterialForm(forms.ModelForm):
    class Meta:
        model = JobMaterial
        fields = [
            'name', 'description',
            'quantity', 'unit_cost',
            'source', 'fund_source',
            'purchase_receipt',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['fund_source'].required = False
        self.fields['purchase_receipt'].required = False
        _style_widgets(self.fields)

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get('source')
        fund_source = cleaned.get('fund_source')

        # If it came from stock, fund_source must be blank
        if source == 'stock':
            cleaned['fund_source'] = ''

        # If externally purchased, encourage a fund source
        if source == 'external' and not fund_source:
            self.add_error(
                'fund_source',
                'Please specify who paid for this material.'
            )

        return cleaned


# ================================================================
# CUSTOMER PAYMENT
# ================================================================

class JobPaymentForm(forms.ModelForm):
    class Meta:
        model = JobPayment
        fields = ['amount', 'method', 'reference', 'notes', 'received_at']
        widgets = {
            'received_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default received_at to now on create (model default kicks in)
        if not self.instance.pk:
            self.fields['received_at'].initial = None
        self.fields['received_at'].required = False
        self.fields['notes'].required = False
        self.fields['reference'].required = False
        _style_widgets(self.fields)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount is None or amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        return amount


# ================================================================
# JOB NOTE
# ================================================================

class JobNoteForm(forms.ModelForm):
    class Meta:
        model = JobNote
        fields = ['note', 'is_customer_visible']
        widgets = {
            'note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_widgets(self.fields)


# ================================================================
# TECHNICIAN RATE
# ================================================================

class TechnicianRateForm(forms.ModelForm):
    class Meta:
        model = TechnicianRate
        fields = ['technician', 'repair_category', 'percentage', 'basis', 'is_active']

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

        if company is not None:
            self.fields['technician'].queryset = _technicians_for(company)
        else:
            self.fields['technician'].queryset = User.objects.filter(
                role='company_technician'
            )

        # "All categories" is represented by an empty choice
        self.fields['repair_category'].required = False
        self.fields['repair_category'].choices = (
            [('', 'All Categories (default)')] + list(WorkshopJob.REPAIR_CATEGORIES)
        )

        _style_widgets(self.fields)

    def clean_percentage(self):
        pct = self.cleaned_data['percentage']
        if pct < 0 or pct > 100:
            raise forms.ValidationError('Percentage must be between 0 and 100.')
        return pct


# ================================================================
# PAYOUT EDIT / PAY
# ================================================================

class PayoutEditForm(forms.ModelForm):
    """Admin-only: adjust the payout amount."""

    class Meta:
        model = TechnicianPayout
        fields = ['amount', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        _style_widgets(self.fields)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount is None or amount < 0:
            raise forms.ValidationError('Amount must be zero or positive.')
        return amount


class PayoutPayForm(forms.ModelForm):
    """Admin-only: record the payout payment."""

    class Meta:
        model = TechnicianPayout
        fields = ['payment_method', 'payment_reference', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_method'].required = True
        self.fields['payment_reference'].required = False
        self.fields['notes'].required = False
        _style_widgets(self.fields)