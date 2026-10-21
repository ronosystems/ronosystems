from django import forms
from django.contrib.auth import get_user_model
from .models import (
    MembershipType, Member,
    Savings, Contribution, Fine,
    LoanType, Loan, LoanRepayment,
    Meeting, Attendance, Announcement,
    Account, Transaction, Expense, Project,
    Committee, CommitteeMember,
)

User = get_user_model()


# ============================================================
# HELPER: Get Chama roles only (exclude platform roles)
# ============================================================
def _get_chama_role_choices():
    """
    Return ONLY the official Chama-specific roles.

    Platform roles (super_admin, site_manager, company_admin, etc.)
    are excluded — those should only be assigned from the platform admin.
    """
    chama_role_keys = {
        'chairperson',
        'vice_chairperson',
        'secretary',
        'vice_secretary',
        'treasurer',
        'loan_officer',
        'coopted_member',
        'member',
    }

    # Get ROLE_CHOICES from the User model
    all_choices = getattr(User, 'ROLE_CHOICES', [])

    # Filter to Chama roles only
    filtered = [
        (key, label) for key, label in all_choices
        if key in chama_role_keys
    ]

    # Fallback if ROLE_CHOICES isn't defined on the model
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
    # Virtual field — not saved to Member, saved to User.role
    role = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Assigns the Chama role to this member's linked user account.",
    )

    class Meta:
        model = Member
        fields = [
            'full_name', 'phone', 'email', 'national_id',
            'membership_type', 'status', 'joined_on',
            'passport_photo', 'id_front', 'id_back',
            'kra_certificate', 'good_conduct',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+254...'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'membership_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'joined_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'passport_photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'id_front': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'id_back': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'kra_certificate': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'good_conduct': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter membership types to this company
        if company:
            self.fields['membership_type'].queryset = (
                self.fields['membership_type'].queryset.filter(company=company, is_active=True)
            )
        self.fields['membership_type'].required = False

        # Populate the role dropdown with ONLY Chama roles
        self.fields['role'].choices = [('', '— Select Chama Role —')] + _get_chama_role_choices()

        # Pre-select the current role if editing an existing member with a user
        if self.instance and self.instance.pk and self.instance.user:
            self.fields['role'].initial = self.instance.user.role


# ============================================================
# MEMBERSHIP TYPE FORM
# ============================================================
class MembershipTypeForm(forms.ModelForm):
    class Meta:
        model = MembershipType
        fields = ['name', 'description', 'registration_fee', 'monthly_contribution', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Regular Member'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'registration_fee': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'monthly_contribution': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ============================================================
# SAVINGS FORM
# ============================================================
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
# CONTRIBUTION FORM
# ============================================================
class ContributionForm(forms.ModelForm):
    class Meta:
        model = Contribution
        fields = ['member', 'membership_type', 'amount', 'period', 'date', 'paid']
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'membership_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'period': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026-10'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')
            self.fields['membership_type'].queryset = (
                MembershipType.objects.filter(company=company, is_active=True).order_by('name')
            )
        self.fields['membership_type'].required = False


# ============================================================
# FINE FORM
# ============================================================
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


# ============================================================
# SELF-SERVICE CONTRIBUTION PAYMENT FORM (Members)
# ============================================================
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



# ============================================================
# LOAN TYPE FORM
# ============================================================
class LoanTypeForm(forms.ModelForm):
    class Meta:
        model = LoanType
        fields = ['name', 'interest_rate', 'max_amount', 'max_term_months', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Emergency Loan'}),
            'interest_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
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

        # ── RULE 1: Cannot exceed 3x contributions ──
        if principal > self.member.available_borrowing_power:
            raise forms.ValidationError(
                f'You can only borrow up to KES {self.member.available_borrowing_power:,.2f} '
                f'(3× your contributions of KES {self.member.total_contributions_paid:,.2f}, '
                f'minus outstanding loans of KES {self.member.active_loans_total:,.2f}).'
            )

        # ── RULE 2: Cannot exceed loan_type.max_amount ──
        loan_type = self.cleaned_data.get('loan_type')
        if loan_type and loan_type.max_amount and principal > loan_type.max_amount:
            raise forms.ValidationError(
                f'Amount exceeds the maximum for {loan_type.name} '
                f'(KES {loan_type.max_amount:,.2f}).'
            )

        return principal

# ============================================================
# LOAN REPAYMENT FORM
# ============================================================
class LoanRepaymentForm(forms.ModelForm):
    class Meta:
        model = LoanRepayment
        fields = ['amount', 'date', 'reference']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'M-Pesa code, receipt...'}),
        }

class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ['title', 'scheduled_for', 'location', 'agenda']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Monthly General Meeting'}),
            'scheduled_for': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Main Hall'}),
            'agenda': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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
            self.fields['member'].queryset = Member.objects.filter(company=company, status='active').order_by('full_name')

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'message', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Upcoming AGM'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['name', 'account_type', 'opening_balance', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Equity Bank'}),
            'account_type': forms.Select(attrs={'class': 'form-control'}),
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
            # Only show members who aren't already in this committee
            self.fields['member'].queryset = Member.objects.filter(
                company=company, status='active'
            ).order_by('full_name')