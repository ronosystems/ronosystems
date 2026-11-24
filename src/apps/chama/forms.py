from django import forms
from django.contrib.auth import get_user_model
import datetime
from django import forms
from django.utils import timezone
from .models import Member, MembershipType
from .models import (
    MembershipType, Member,
    Savings, Contribution, Fine,
    LoanType, Loan, LoanRepayment,
    Meeting, Attendance, Announcement,
    Account, Transaction, Expense, Project,
    Committee, CommitteeMember, Guest,
)

User = get_user_model()


# ============================================================
# HELPER: Get Chama roles only (exclude platform roles)
# ============================================================
def _get_chama_role_choices():
    chama_role_keys = {
        'chairperson', 'vice_chairperson', 'secretary', 'vice_secretary',
        'treasurer', 'loan_officer', 'coopted_member', 'member',
    }

    all_choices = getattr(User, 'ROLE_CHOICES', [])

    filtered = [
        (key, label) for key, label in all_choices
        if key in chama_role_keys
    ]

    if not filtered:
        filtered = [
            ('chairperson', 'Chairperson'),
            ('vice_chairperson', 'Vice Chairperson'),
            ('secretary', 'Secretary'),
            ('vice_secretary', 'Vice Secretary'),
            ('treasurer', 'Treasurer'),
            ('loan_officer', 'Loan Officer'),
            ('coopted_member', 'Co-opted Member'),
            ('member', 'Regular Member'),
        ]

    return filtered


# ============================================================
# MEMBER FORM
# ============================================================

class MemberForm(forms.ModelForm):
    # Explicitly define the field to override the default required=True
    custom_loan_limit = forms.DecimalField(
        required=False, 
        initial=0,
        max_digits=12, 
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'step': '0.01',
            'placeholder': '0.00'
        }),
        help_text="Leave as 0 to use the default 3x contribution limit."
    )

    # We also need to handle the password field manually since it's not a direct model field
    default_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Leave blank to use default'
        }),
        help_text="Leave blank to use the default company password."
    )

    # Hidden field to pass the role
    role = forms.ChoiceField(
        choices=[
            ('member', 'Member'),
            ('chairperson', 'Chairperson'),
            ('vice_chairperson', 'Vice Chairperson'),
            ('treasurer', 'Treasurer'),
            ('secretary', 'Secretary'),
            ('vice_secretary', 'Vice Secretary'),
            ('loan_officer', 'Loan Officer'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Member
        fields = [
            'full_name', 'phone', 'email', 'national_id', 
            'membership_type', 'status', 'joined_on',
            'custom_loan_limit', # Added here
            'passport_photo', 'id_front', 'id_back', 
            'kra_certificate', 'good_conduct'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. John Doe'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0712345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g. john@example.com'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 12345678'}),
            'membership_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'joined_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        # Extract custom kwargs passed from the view
        self.company = kwargs.pop('company', None)
        fallback_password = kwargs.pop('fallback_password', '')
        
        super().__init__(*args, **kwargs)

        # 1. Filter Membership Types by Company
        if self.company:
            self.fields['membership_type'].queryset = MembershipType.objects.filter(
                company=self.company
            )
            
        # 2. Handle default password placeholder logic
        if fallback_password:
            self.fields['default_password'].widget.attrs['placeholder'] = f"Default: {fallback_password}"

        # 3. If EDITING an existing member, update the loan limit label
        if self.instance and self.instance.pk:
            self.fields['custom_loan_limit'].help_text = (
                f"Current limit: KES {self.instance.custom_loan_limit:,.2f}. "
                "Set to 0 to revert to the 3x contribution limit."
            )
            
        # 4. Ensure required fields match your form layout
        self.fields['full_name'].required = True
        self.fields['phone'].required = True
        
        # 5. Clean up date input formats
        self.fields['joined_on'].input_formats = ['%Y-%m-%d']

    def clean_custom_loan_limit(self):
        """Ensure that if the field is left blank, it saves as 0."""
        limit = self.cleaned_data.get('custom_loan_limit')
        if limit is None:
            return 0
        return limit

    def clean_phone(self):
        """Ensure phone number formatting and uniqueness if needed."""
        phone = self.cleaned_data.get('phone')
        if phone:
            # Standardize phone format (optional)
            phone = phone.strip()
            
            # Check for duplicates in the same company (excluding self on edit)
            qs = Member.objects.filter(company=self.company, phone=phone)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("A member with this phone number already exists.")
        return phone


# ============================================================
# MEMBERSHIP TYPE FORM
# ============================================================
class MembershipTypeForm(forms.ModelForm):
    class Meta:
        model = MembershipType
        fields = ['name', 'description', 'registration_fee', 'monthly_contribution', 'is_active']
        widgets = {
            'name': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'registration_fee': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'monthly_contribution': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ============================================================
# TREASURY FORM
# ============================================================
class ContributionForm(forms.ModelForm):
    period = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Month of Contribution'
    )

    class Meta:
        model = Contribution
        fields = ['member', 'amount', 'period', 'date', 'paid']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)

        current_year = datetime.date.today().year
        month_choices = [('', '— Select Month —')]
        months = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]

        for year in [current_year - 1, current_year, current_year + 1]:
            for i, month_name in enumerate(months, start=1):
                value = f"{year}-{i:02d}"
                label = f"{month_name} {year}"
                month_choices.append((value, label))

        self.fields['period'].choices = month_choices

        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')


class FineForm(forms.ModelForm):
    class Meta:
        model = Fine
        fields = ['member', 'reason', 'amount', 'date', 'is_paid']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Late attendance, missed meeting'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')


class SelfServiceContributionForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Enter amount'}),
        label='Amount (KES)',
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0712345678'}),
        label='M-Pesa Phone Number',
    )


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['name', 'account_type', 'purpose', 'opening_balance', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Equity Bank - Welfare'}),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
            'purpose': forms.Select(attrs={'class': 'form-control'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['account', 'transaction_type', 'amount', 'date', 'description', 'reference', 'project']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'project': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['account'].queryset = Account.objects.filter(company=company, is_active=True)
            self.fields['project'].queryset = Project.objects.filter(company=company, is_active=True)
        self.fields['project'].required = False


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['account', 'title', 'amount', 'date', 'category', 'notes']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['account'].queryset = Account.objects.filter(company=company, is_active=True)
        self.fields['account'].required = False


class SavingsForm(forms.ModelForm):
    class Meta:
        model = Savings
        fields = ['member', 'amount', 'date', 'reference', 'notes']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. M-Pesa code, receipt no.'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')


# ============================================================
# LOAN TYPE FORM
# ============================================================
class LoanTypeForm(forms.ModelForm):
    class Meta:
        model = LoanType
        fields = [
            'name', 'interest_rate', 'processing_fee_percentage',
            'max_term_months', 'is_active',
        ]
        widgets = {
            'name': forms.Select(attrs={'class': 'form-control'}),
            'interest_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'processing_fee_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_term_months': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ============================================================
# LOAN FORM (Officer Manual Entry)
# ============================================================
class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = [
            'member', 'loan_type', 'principal', 'interest_rate',
            'term_months', 'status', 'requested_on', 'purpose'
        ]
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'loan_type': forms.Select(attrs={'class': 'form-control'}),
            'principal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'interest_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'term_months': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'requested_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'purpose': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')
            self.fields['loan_type'].queryset = LoanType.objects.filter(
                company=company, is_active=True
            ).order_by('name')
        self.fields['loan_type'].required = False


# ============================================================
# SELF-SERVICE LOAN APPLICATION FORM (Members)
# ============================================================
class SelfServiceLoanForm(forms.Form):
    loan_type = forms.ModelChoiceField(
        queryset=LoanType.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Loan Type',
    )
    principal = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Amount Requested (KES)',
    )
    term_months = forms.IntegerField(
        min_value=1, max_value=60,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label='Term (Months)',
    )
    purpose = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Purpose of Loan',
    )

    def __init__(self, *args, company=None, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        if company:
            self.fields['loan_type'].queryset = LoanType.objects.filter(
                company=company, is_active=True
            ).order_by('name')

    def clean_principal(self):
        principal = self.cleaned_data['principal']

        if not self.member:
            return principal

        if principal > self.member.available_borrowing_power:
            raise forms.ValidationError(
                f'You can only borrow up to KES {self.member.available_borrowing_power:,.2f} '
                f'(3× your contributions of KES {self.member.total_contributions_paid:,.2f}, '
                f'minus outstanding loans of KES {self.member.active_loans_total:,.2f}).'
            )

        return principal


class LoanRepaymentForm(forms.ModelForm):
    class Meta:
        model = LoanRepayment
        fields = ['amount', 'date', 'reference']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'M-Pesa code, receipt...'}),
        }


# ============================================================
# GENERAL FORM
# ============================================================
class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            'title', 'scheduled_for', 'start_time', 'end_time',
            'meeting_type', 'target_audience', 'location', 'agenda'
        ]
        widgets = {
            'scheduled_for': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'agenda': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'meeting_type': forms.Select(attrs={'class': 'form-control'}),
            'target_audience': forms.Select(attrs={'class': 'form-control'}),
        }


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['member', 'status']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'message', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Upcoming AGM'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CommitteeForm(forms.ModelForm):
    class Meta:
        model = Committee
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Finance Committee'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CommitteeMemberForm(forms.ModelForm):
    class Meta:
        model = CommitteeMember
        fields = ['member', 'role_in_committee']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'role_in_committee': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Chairperson, Secretary'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'target_amount', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'target_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ============================================================
# GUEST FORM (For External Loans)
# ============================================================
class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = [
            'full_name', 'phone', 'email', 'national_id', 'address',
            'passport_photo', 'id_front', 'id_back', 'mpesa_statement',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full legal name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0712345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 12345678'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'passport_photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'id_front': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'id_back': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'mpesa_statement': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
        }