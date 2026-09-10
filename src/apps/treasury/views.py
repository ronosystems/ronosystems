from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import json
import csv
from django.http import HttpResponse

from apps.companies.models import Company
from apps.epa_shop.models import Branch
from .models import (
    Treasury, BankAccount, MpesaAccount, DailyRecord, 
    DailyBankBalance, DailyMpesaBalance, Movement, 
    TreasurySummary, TreasuryTransactionLog
)
from .utils import create_boost_movement, create_transfer_movement, create_daily_record, update_daily_balances

# ============================================
# HELPER FUNCTIONS - User Role Checks
# ============================================

def is_admin_or_manager(user):
    """Check if user is admin, manager, or super admin"""
    return user.role in ['super_admin', 'company_admin', 'company_manager']


def is_cashier(user):
    """Check if user is a cashier"""
    return user.role == 'company_cashier'


def is_agent(user):
    """Check if user is an agent"""
    return user.role == 'company_agent'


def is_staff(user):
    """Check if user is staff"""
    return user.role == 'company_staff'


def get_user_branch(user):
    """Get the user's branch"""
    if hasattr(user, 'branch') and user.branch:
        return user.branch
    return None

def get_user_company(request, company_id):
    """Get company and check if user belongs to it"""
    company = get_object_or_404(Company, id=company_id)
    
    # Check if user belongs to this company
    if request.user.company_id != company.id and request.user.role != 'super_admin':
        messages.error(request, 'You do not have access to this company')
        return None
    
    return company


def get_treasury(company, branch):
    """Get or create treasury for a branch"""
    treasury, created = Treasury.objects.get_or_create(
        company=company,
        branch=branch
    )
    return treasury


def log_transaction(treasury, transaction_type, changes, description, user=None):
    """Log treasury transaction"""
    TreasuryTransactionLog.objects.create(
        company=treasury.company,
        treasury=treasury,
        transaction_type=transaction_type,
        bank_change=changes.get('bank', 0),
        mpesa_change=changes.get('mpesa', 0),
        cash_change=changes.get('cash', 0),
        credit_change=changes.get('credit', 0),
        net_change=changes.get('net', 0),
        description=description,
        performed_by=user
    )


# ============================================
# DECORATORS
# ============================================

def company_required(view_func):
    """Decorator to check if user belongs to the company"""
    from functools import wraps
    
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        company_id = kwargs.get('company_id')
        if not company_id:
            messages.error(request, 'Company not specified')
            return redirect('dashboard')
        
        company = get_object_or_404(Company, id=company_id)
        
        # Check if user belongs to this company or is super_admin
        if request.user.company_id != company.id and request.user.role != 'super_admin':
            messages.error(request, 'You do not have access to this company')
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def branch_access_required(view_func):
    """Decorator to check if user has access to the branch"""
    from functools import wraps
    
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        company_id = kwargs.get('company_id')
        branch_id = kwargs.get('branch_id')
        
        if not company_id or not branch_id:
            messages.error(request, 'Company or branch not specified')
            return redirect('dashboard')
        
        company = get_object_or_404(Company, id=company_id)
        branch = get_object_or_404(Branch, id=branch_id, company=company)
        
        # Check company access
        if request.user.company_id != company.id and request.user.role != 'super_admin':
            messages.error(request, 'You do not have access to this company')
            return redirect('dashboard')
        
        # Check branch access for non-admin users
        if not is_admin_or_manager(request.user):
            user_branch = get_user_branch(request.user)
            if user_branch and user_branch.id != branch.id:
                messages.error(request, 'You do not have access to this branch')
                return redirect('treasury:dashboard', company_id=company.id)
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# ============================================
# TREASURY DASHBOARD
# ============================================

@login_required
@company_required
def treasury_dashboard(request, company_id=None):
    """Main treasury dashboard view"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branches to show
    branches = None
    
    # Super admin and company admin can see all branches
    if request.user.role in ['super_admin', 'company_admin']:
        branches = Branch.objects.filter(company=company, is_active=True)
    else:
        # Other roles can only see their own branch
        if user_branch:
            branches = Branch.objects.filter(id=user_branch.id, company=company, is_active=True)
        else:
            branches = Branch.objects.none()
            messages.warning(request, 'You are not assigned to any branch.')
    
    # Get treasury data for the filtered branches
    treasury_data = []
    total_net = 0
    
    for branch in branches:
        treasury, created = Treasury.objects.get_or_create(
            company=company,
            branch=branch
        )
        
        # Get today's record
        today_record = DailyRecord.objects.filter(
            company=company,
            branch=branch,
            date=timezone.now().date()
        ).first()
        
        # Get recent movements (last 5)
        recent_movements = Movement.objects.filter(
            company=company,
            branch=branch
        ).order_by('-created_at')[:5]
        
        # Get bank accounts with their current balances
        bank_accounts = BankAccount.objects.filter(
            company=company,
            branch=branch,
            is_active=True
        )
        
        # Get M-Pesa accounts with their current balances
        mpesa_accounts = MpesaAccount.objects.filter(
            company=company,
            branch=branch,
            is_active=True
        )
        
        total_net += treasury.net_balance
        
        treasury_data.append({
            'branch': branch,
            'treasury': treasury,
            'today_record': today_record,
            'recent_movements': recent_movements,
            'bank_accounts': bank_accounts,
            'mpesa_accounts': mpesa_accounts,
        })
    
    # Get overall company totals (only for branches the user can see)
    total_bank = sum(t['treasury'].total_bank_balance for t in treasury_data)
    total_mpesa = sum(t['treasury'].total_mpesa_balance for t in treasury_data)
    total_cash = sum(t['treasury'].cash_balance for t in treasury_data)
    total_credit = sum(t['treasury'].credit_balance for t in treasury_data)
    
    # Get recent movements across all visible branches
    recent_movements_all = Movement.objects.filter(
        company=company,
        branch__in=branches
    ).order_by('-created_at')[:10]
    
    # Determine if user is admin
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branches': branches,
        'treasury_data': treasury_data,
        'total_bank': total_bank,
        'total_mpesa': total_mpesa,
        'total_cash': total_cash,
        'total_credit': total_credit,
        'total_net': total_net,
        'recent_movements_all': recent_movements_all,
        'today': timezone.now().date(),
        'is_admin': is_admin,
        'is_agent': is_agent(request.user),
        'user_branch': user_branch,
        'show_all_branches': is_admin,  # Flag to show/hide all branches in template
    }
    return render(request, 'treasury/dashboard.html', context)

# ============================================
# BRANCH TREASURY VIEW
# ============================================

@login_required
@branch_access_required
def branch_treasury(request, company_id=None, branch_id=None):
    """View treasury details for a specific branch"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    branch = get_object_or_404(Branch, id=branch_id, company=company)
    treasury = get_treasury(company, branch)
    
    # Get daily records (paginated)
    daily_records = DailyRecord.objects.filter(
        company=company,
        branch=branch
    ).order_by('-date')
    
    paginator = Paginator(daily_records, 30)
    page = request.GET.get('page', 1)
    daily_records_page = paginator.get_page(page)
    
    # Get movements (paginated)
    movements = Movement.objects.filter(
        company=company,
        branch=branch
    ).order_by('-created_at')
    
    paginator_movements = Paginator(movements, 20)
    page_movements = request.GET.get('page_movements', 1)
    movements_page = paginator_movements.get_page(page_movements)
    
    # Get bank accounts
    bank_accounts = BankAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    )
    
    # Get M-Pesa accounts
    mpesa_accounts = MpesaAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    )
    
    # Get today's record with all balances
    today_record = DailyRecord.objects.filter(
        company=company,
        branch=branch,
        date=timezone.now().date()
    ).first()
    
    # Get today's bank balances
    today_bank_balances = []
    today_mpesa_balances = []
    
    if today_record:
        today_bank_balances = DailyBankBalance.objects.filter(
            daily_record=today_record
        ).select_related('bank_account')
        
        today_mpesa_balances = DailyMpesaBalance.objects.filter(
            daily_record=today_record
        ).select_related('mpesa_account')
    
    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'daily_records': daily_records_page,
        'movements': movements_page,
        'bank_accounts': bank_accounts,
        'mpesa_accounts': mpesa_accounts,
        'today_record': today_record,
        'today_bank_balances': today_bank_balances,
        'today_mpesa_balances': today_mpesa_balances,
        'today': timezone.now().date(),
        'is_admin': is_admin_or_manager(request.user),
        'is_agent': is_agent(request.user),
    }
    return render(request, 'treasury/branch_treasury.html', context)



# ============================================
# BANK ACCOUNT CRUD
# ============================================

@login_required
@branch_access_required
def bank_account_create(request, company_id=None, branch_id=None):
    """Create a bank account for a branch"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            # If no branch specified, use first active branch
            branch = Branch.objects.filter(company=company, is_active=True).first()
        
        if not branch:
            messages.error(request, 'No branch available. Please create a branch first.')
            return redirect('treasury:dashboard', company_id=company.id)
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        # If branch_id in URL doesn't match user's branch, redirect to user's branch
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only create bank accounts for your assigned branch: {user_branch.name}')
            return redirect('treasury:bank_account_create', company_id=company.id, branch_id=user_branch.id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available. Please create a branch first.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    treasury = get_treasury(company, branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can create bank accounts.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        bank_type = request.POST.get('bank_type')
        account_name = request.POST.get('account_name')
        account_number = request.POST.get('account_number')
        branch_code = request.POST.get('branch_code', '')
        swift_code = request.POST.get('swift_code', '')
        is_primary = request.POST.get('is_primary') == 'on'
        notes = request.POST.get('notes', '')
        
        # Validate
        if not bank_type or not account_name or not account_number:
            messages.error(request, 'Bank type, account name, and account number are required')
            return redirect('treasury:bank_account_create', company_id=company.id, branch_id=branch.id)
        
        # Check if account already exists
        if BankAccount.objects.filter(
            company=company, 
            branch=branch, 
            account_name=account_name,
            account_number=account_number
        ).exists():
            messages.error(request, f'Bank account {account_name} ({account_number}) already exists for this branch')
            return redirect('treasury:bank_account_create', company_id=company.id, branch_id=branch.id)
        
        # Create bank account
        bank_account = BankAccount.objects.create(
            company=company,
            branch=branch,
            treasury=treasury,
            bank_type=bank_type,
            account_name=account_name,
            account_number=account_number,
            branch_code=branch_code,
            swift_code=swift_code,
            is_primary=is_primary,
            notes=notes,
            current_balance=0
        )
        
        messages.success(request, f'Bank account {account_name} created successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'bank_types': BankAccount.BankType.choices,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/bank_account_form.html', context)


@login_required
@branch_access_required
def bank_account_edit(request, company_id=None, branch_id=None, account_id=None):
    """Edit a bank account"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            branch = user_branch or Branch.objects.filter(company=company, is_active=True).first()
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only edit bank accounts for your assigned branch: {user_branch.name}')
            return redirect('treasury:bank_account_edit', company_id=company.id, branch_id=user_branch.id, account_id=account_id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    bank_account = get_object_or_404(BankAccount, id=account_id, company=company, branch=branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can edit bank accounts.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        bank_account.bank_type = request.POST.get('bank_type')
        bank_account.account_name = request.POST.get('account_name')
        bank_account.account_number = request.POST.get('account_number')
        bank_account.branch_code = request.POST.get('branch_code', '')
        bank_account.swift_code = request.POST.get('swift_code', '')
        bank_account.is_primary = request.POST.get('is_primary') == 'on'
        bank_account.notes = request.POST.get('notes', '')
        bank_account.is_active = request.POST.get('is_active') == 'on'
        bank_account.save()
        
        messages.success(request, f'Bank account {bank_account.account_name} updated successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'bank_account': bank_account,
        'bank_types': BankAccount.BankType.choices,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/bank_account_form.html', context)


@login_required
@branch_access_required
def bank_account_delete(request, company_id=None, branch_id=None, account_id=None):
    """Delete a bank account"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            branch = user_branch or Branch.objects.filter(company=company, is_active=True).first()
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only delete bank accounts for your assigned branch: {user_branch.name}')
            return redirect('treasury:bank_account_delete', company_id=company.id, branch_id=user_branch.id, account_id=account_id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    bank_account = get_object_or_404(BankAccount, id=account_id, company=company, branch=branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can delete bank accounts.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        account_name = bank_account.account_name
        bank_account.delete()
        messages.success(request, f'Bank account {account_name} deleted successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'bank_account': bank_account,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/confirm_delete.html', context)
    

# ============================================
# MPESA ACCOUNT CRUD
# ============================================

@login_required
def mpesa_account_create(request, company_id=None, branch_id=None):
    """Create an M-Pesa account for a branch"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            # If no branch specified, use first active branch
            branch = Branch.objects.filter(company=company, is_active=True).first()
        
        if not branch:
            messages.error(request, 'No branch available. Please create a branch first.')
            return redirect('treasury:dashboard', company_id=company.id)
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        # If branch_id in URL doesn't match user's branch, redirect to user's branch
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only create M-Pesa accounts for your assigned branch: {user_branch.name}')
            return redirect('treasury:mpesa_account_create', company_id=company.id, branch_id=user_branch.id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available. Please create a branch first.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    treasury = get_treasury(company, branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can create M-Pesa accounts.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        till_name = request.POST.get('till_name')
        till_number = request.POST.get('till_number')
        store_number = request.POST.get('store_number', '')
        account_type = request.POST.get('account_type')
        is_primary = request.POST.get('is_primary') == 'on'
        notes = request.POST.get('notes', '')
        
        # Validate
        if not till_name or not till_number or not account_type:
            messages.error(request, 'Till name, till number, and account type are required')
            return redirect('treasury:mpesa_account_create', company_id=company.id, branch_id=branch.id)
        
        # Check if account already exists
        if MpesaAccount.objects.filter(
            company=company, 
            branch=branch, 
            till_name=till_name,
            till_number=till_number
        ).exists():
            messages.error(request, f'M-Pesa account {till_name} ({till_number}) already exists for this branch')
            return redirect('treasury:mpesa_account_create', company_id=company.id, branch_id=branch.id)
        
        # Create M-Pesa account
        mpesa_account = MpesaAccount.objects.create(
            company=company,
            branch=branch,
            treasury=treasury,
            till_name=till_name,
            till_number=till_number,
            store_number=store_number,
            account_type=account_type,
            is_primary=is_primary,
            notes=notes,
            current_balance=0
        )
        
        messages.success(request, f'M-Pesa account {till_name} created successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'mpesa_types': MpesaAccount.MpesaType.choices,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/mpesa_account_form.html', context)


@login_required
def mpesa_account_edit(request, company_id=None, branch_id=None, account_id=None):
    """Edit an M-Pesa account"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            branch = user_branch or Branch.objects.filter(company=company, is_active=True).first()
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only edit M-Pesa accounts for your assigned branch: {user_branch.name}')
            return redirect('treasury:mpesa_account_edit', company_id=company.id, branch_id=user_branch.id, account_id=account_id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    mpesa_account = get_object_or_404(MpesaAccount, id=account_id, company=company, branch=branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can edit M-Pesa accounts.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        mpesa_account.till_name = request.POST.get('till_name')
        mpesa_account.till_number = request.POST.get('till_number')
        mpesa_account.store_number = request.POST.get('store_number', '')
        mpesa_account.account_type = request.POST.get('account_type')
        mpesa_account.is_primary = request.POST.get('is_primary') == 'on'
        mpesa_account.notes = request.POST.get('notes', '')
        mpesa_account.is_active = request.POST.get('is_active') == 'on'
        mpesa_account.save()
        
        messages.success(request, f'M-Pesa account {mpesa_account.till_name} updated successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'mpesa_account': mpesa_account,
        'mpesa_types': MpesaAccount.MpesaType.choices,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/mpesa_account_form.html', context)


@login_required
def mpesa_account_delete(request, company_id=None, branch_id=None, account_id=None):
    """Delete an M-Pesa account"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            branch = user_branch or Branch.objects.filter(company=company, is_active=True).first()
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only delete M-Pesa accounts for your assigned branch: {user_branch.name}')
            return redirect('treasury:mpesa_account_delete', company_id=company.id, branch_id=user_branch.id, account_id=account_id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    mpesa_account = get_object_or_404(MpesaAccount, id=account_id, company=company, branch=branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can delete M-Pesa accounts.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        till_name = mpesa_account.till_name
        mpesa_account.delete()
        messages.success(request, f'M-Pesa account {till_name} deleted successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'mpesa_account': mpesa_account,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/confirm_delete.html', context)

    

# ============================================
# DAILY RECORD CRUD
# ============================================

@login_required
def daily_record_create(request, company_id=None, branch_id=None):
    """Create a daily record with individual account balances"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            # If no branch specified, use first active branch
            branch = Branch.objects.filter(company=company, is_active=True).first()
        
        if not branch:
            messages.error(request, 'No branch available. Please create a branch first.')
            return redirect('treasury:dashboard', company_id=company.id)
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        # If branch_id in URL doesn't match user's branch, redirect to user's branch
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only record balances for your assigned branch: {user_branch.name}')
            return redirect('treasury:daily_record_create', company_id=company.id, branch_id=user_branch.id)
        
        branch = user_branch
    
    treasury = get_treasury(company, branch)
    
    # Get all active bank and M-Pesa accounts for this branch
    bank_accounts = BankAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    ).order_by('bank_type', 'account_name')
    
    mpesa_accounts = MpesaAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    ).order_by('till_name')
    
    if request.method == 'POST':
        date = request.POST.get('date', timezone.now().date())
        cash_balance = Decimal(request.POST.get('cash_balance', 0))
        credit_balance = Decimal(request.POST.get('credit_balance', 0))
        notes = request.POST.get('notes', '')
        
        # Check if record exists for this date
        existing = DailyRecord.objects.filter(
            company=company,
            branch=branch,
            date=date
        ).first()
        
        if existing:
            messages.error(request, f'Record for {date} already exists. Please edit it instead.')
            return redirect('treasury:daily_record_edit', 
                          company_id=company.id, 
                          branch_id=branch.id, 
                          record_id=existing.id)
        
        # Collect bank balances from form
        bank_balances = {}
        for bank in bank_accounts:
            balance_key = f'bank_{bank.id}'
            if balance_key in request.POST:
                balance = Decimal(request.POST.get(balance_key, 0))
                bank_balances[bank.id] = balance
        
        # Collect M-Pesa balances from form
        mpesa_balances = {}
        for mpesa in mpesa_accounts:
            balance_key = f'mpesa_{mpesa.id}'
            if balance_key in request.POST:
                balance = Decimal(request.POST.get(balance_key, 0))
                mpesa_balances[mpesa.id] = balance
        
        with transaction.atomic():
            # Create daily record
            daily_record = DailyRecord.objects.create(
                company=company,
                branch=branch,
                treasury=treasury,
                date=date,
                cash_balance=cash_balance,
                credit_balance=credit_balance,
                notes=notes,
                created_by=request.user
            )
            
            # Create daily bank balances
            for bank in bank_accounts:
                balance = bank_balances.get(bank.id, 0)
                DailyBankBalance.objects.create(
                    daily_record=daily_record,
                    bank_account=bank,
                    closing_balance=balance
                )
                # Update account current balance
                bank.current_balance = balance
                bank.save()
            
            # Create daily M-Pesa balances
            for mpesa in mpesa_accounts:
                balance = mpesa_balances.get(mpesa.id, 0)
                DailyMpesaBalance.objects.create(
                    daily_record=daily_record,
                    mpesa_account=mpesa,
                    closing_balance=balance
                )
                # Update account current balance
                mpesa.current_balance = balance
                mpesa.save()
            
            # Update treasury aggregated balances
            treasury.total_bank_balance = daily_record.total_bank_balance
            treasury.total_mpesa_balance = daily_record.total_mpesa_balance
            treasury.cash_balance = cash_balance
            treasury.credit_balance = credit_balance
            treasury.save()
            
            # Log transaction
            log_transaction(
                treasury,
                'daily_record',
                {
                    'bank': daily_record.total_bank_balance,
                    'mpesa': daily_record.total_mpesa_balance,
                    'cash': cash_balance,
                    'credit': credit_balance,
                    'net': daily_record.net_balance
                },
                f"Daily record for {date} created",
                request.user
            )
        
        messages.success(request, f'✅ Daily record for {date} created successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get today's date
    today = timezone.now().date()
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'bank_accounts': bank_accounts,
        'mpesa_accounts': mpesa_accounts,
        'today': today,
        'record': None,
        'today_record': None,
        'is_admin': is_admin,
        'user_branch': user_branch,
        'all_branches': all_branches,
    }
    return render(request, 'treasury/daily_record_form.html', context)
    

@login_required
def daily_record_edit(request, company_id=None, branch_id=None, record_id=None):
    """Edit a daily record with individual account balances"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            branch = user_branch or Branch.objects.filter(company=company, is_active=True).first()
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only edit records for your assigned branch: {user_branch.name}')
            return redirect('treasury:daily_record_edit', company_id=company.id, branch_id=user_branch.id, record_id=record_id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    daily_record = get_object_or_404(DailyRecord, id=record_id, company=company, branch=branch)
    treasury = get_treasury(company, branch)
    
    # Get all active bank and M-Pesa accounts
    bank_accounts = BankAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    ).order_by('bank_type', 'account_name')
    
    mpesa_accounts = MpesaAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    ).order_by('till_name')
    
    # Get existing balances for this record
    bank_balances = DailyBankBalance.objects.filter(
        daily_record=daily_record
    ).select_related('bank_account')
    
    mpesa_balances = DailyMpesaBalance.objects.filter(
        daily_record=daily_record
    ).select_related('mpesa_account')
    
    # Create lookup dicts
    bank_balance_dict = {b.bank_account_id: b.closing_balance for b in bank_balances}
    mpesa_balance_dict = {m.mpesa_account_id: m.closing_balance for m in mpesa_balances}
    
    # Build (account, balance) rows for the template so edit shows saved values
    bank_account_rows = [
        (bank, bank_balance_dict.get(bank.id, bank.current_balance))
        for bank in bank_accounts
    ]
    mpesa_account_rows = [
        (mpesa, mpesa_balance_dict.get(mpesa.id, mpesa.current_balance))
        for mpesa in mpesa_accounts
    ]
    
    if request.method == 'POST':
        cash_balance = Decimal(request.POST.get('cash_balance', 0))
        credit_balance = Decimal(request.POST.get('credit_balance', 0))
        notes = request.POST.get('notes', '')
        
        # Collect bank balances from form
        bank_balance_updates = {}
        for bank in bank_accounts:
            balance_key = f'bank_{bank.id}'
            if balance_key in request.POST:
                balance = Decimal(request.POST.get(balance_key, 0))
                bank_balance_updates[bank.id] = balance
        
        # Collect M-Pesa balances from form
        mpesa_balance_updates = {}
        for mpesa in mpesa_accounts:
            balance_key = f'mpesa_{mpesa.id}'
            if balance_key in request.POST:
                balance = Decimal(request.POST.get(balance_key, 0))
                mpesa_balance_updates[mpesa.id] = balance
        
        with transaction.atomic():
            # Update daily record
            daily_record.cash_balance = cash_balance
            daily_record.credit_balance = credit_balance
            daily_record.notes = notes
            daily_record.save()
            
            # Update bank balances
            for bank in bank_accounts:
                balance = bank_balance_updates.get(bank.id, 0)
                DailyBankBalance.objects.update_or_create(
                    daily_record=daily_record,
                    bank_account=bank,
                    defaults={'closing_balance': balance}
                )
                # Update account current balance
                bank.current_balance = balance
                bank.save()
            
            # Update M-Pesa balances
            for mpesa in mpesa_accounts:
                balance = mpesa_balance_updates.get(mpesa.id, 0)
                DailyMpesaBalance.objects.update_or_create(
                    daily_record=daily_record,
                    mpesa_account=mpesa,
                    defaults={'closing_balance': balance}
                )
                # Update account current balance
                mpesa.current_balance = balance
                mpesa.save()
            
            # Update treasury aggregated balances
            treasury = daily_record.treasury
            treasury.total_bank_balance = daily_record.total_bank_balance
            treasury.total_mpesa_balance = daily_record.total_mpesa_balance
            treasury.cash_balance = cash_balance
            treasury.credit_balance = credit_balance
            treasury.save()
            
            # Log transaction
            log_transaction(
                treasury,
                'daily_record',
                {
                    'bank': daily_record.total_bank_balance,
                    'mpesa': daily_record.total_mpesa_balance,
                    'cash': cash_balance,
                    'credit': credit_balance,
                    'net': daily_record.net_balance
                },
                f"Daily record for {daily_record.date} updated",
                request.user
            )
        
        messages.success(request, f'✅ Daily record for {daily_record.date} updated successfully!')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'bank_accounts': bank_accounts,
        'mpesa_accounts': mpesa_accounts,
        'bank_account_rows': bank_account_rows,
        'mpesa_account_rows': mpesa_account_rows,
        'record': daily_record,
        'bank_balance_dict': bank_balance_dict,
        'mpesa_balance_dict': mpesa_balance_dict,
        'today': timezone.now().date(),
        'is_admin': is_admin,
        'user_branch': user_branch,
        'all_branches': all_branches,
    }
    return render(request, 'treasury/daily_record_form.html', context)

@login_required
def daily_record_delete(request, company_id=None, branch_id=None, record_id=None):
    """Delete a daily record"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            branch = user_branch or Branch.objects.filter(company=company, is_active=True).first()
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only delete records for your assigned branch: {user_branch.name}')
            return redirect('treasury:daily_record_delete', company_id=company.id, branch_id=user_branch.id, record_id=record_id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    record = get_object_or_404(DailyRecord, id=record_id, company=company, branch=branch)
    
    # Check if user has permission (admin or manager only)
    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can delete daily records.')
        return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
    
    if request.method == 'POST':
        date = record.date
        
        # Get treasury before deleting
        treasury = record.treasury
        
        with transaction.atomic():
            # Delete bank balances
            record.bank_balances.all().delete()
            # Delete M-Pesa balances
            record.mpesa_balances.all().delete()
            # Delete record
            record.delete()
            
            # Update treasury to use latest record or zero
            latest_record = DailyRecord.objects.filter(
                company=company,
                branch=branch
            ).first()
            
            if latest_record:
                treasury.total_bank_balance = latest_record.total_bank_balance
                treasury.total_mpesa_balance = latest_record.total_mpesa_balance
                treasury.cash_balance = latest_record.cash_balance
                treasury.credit_balance = latest_record.credit_balance
            else:
                treasury.total_bank_balance = 0
                treasury.total_mpesa_balance = 0
                treasury.cash_balance = 0
                treasury.credit_balance = 0
            treasury.save()
        
        messages.success(request, f'✅ Daily record for {date} deleted successfully!')
        return redirect('treasury:daily_records_list', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'record': record,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/confirm_delete.html', context)

# ============================================
# DAILY RECORDS LIST
# ============================================

@login_required
def daily_records_list(request, company_id=None, branch_id=None):
    """List all daily records for a branch (with branch selector for admins)"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')

    # Get the user's branch
    user_branch = get_user_branch(request.user)

    # Determine which branch to use
    branch = None

    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            # If no branch specified, use first active branch
            branch = Branch.objects.filter(company=company, is_active=True).first()

        if not branch:
            messages.error(request, 'No branch available. Please create a branch first.')
            return redirect('treasury:dashboard', company_id=company.id)
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)

        # If branch_id in URL doesn't match user's branch, redirect to user's branch
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only view records for your assigned branch: {user_branch.name}')
            return redirect('treasury:daily_records_list', company_id=company.id, branch_id=user_branch.id)

        branch = user_branch

    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)

    treasury = get_treasury(company, branch)

    # Get date filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    records = DailyRecord.objects.filter(
        company=company,
        branch=branch
    )

    if date_from:
        records = records.filter(date__gte=date_from)
    if date_to:
        records = records.filter(date__lte=date_to)

    records = records.order_by('-date')

    paginator = Paginator(records, 30)
    page = request.GET.get('page', 1)
    records_page = paginator.get_page(page)

    # Calculate summary stats
    record_count = records.count()

    # Get the most recent record (first one since ordered by -date)
    latest_record = records.first()

    # Get the last day's closing balance (net balance of the most recent record)
    total_net = latest_record.net_balance if latest_record else 0

    # Calculate total bank, mpesa, cash, credit from the latest record
    total_bank = latest_record.total_bank_balance if latest_record else 0
    total_mpesa = latest_record.total_mpesa_balance if latest_record else 0
    total_cash = latest_record.cash_balance if latest_record else 0
    total_credit = latest_record.credit_balance if latest_record else 0

    # Calculate average net balance across all records
    avg_net = 0
    if record_count > 0:
        total_net_sum = 0
        for record in records:
            total_net_sum += record.net_balance
        avg_net = total_net_sum / record_count

    # Get the first and last record for comparison
    first_record = records.last()  # Oldest record

    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)

    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']

    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'records': records_page,
        'total_records': record_count,
        'avg_net': avg_net,
        'total_net': total_net,
        'total_bank': total_bank,
        'total_mpesa': total_mpesa,
        'total_cash': total_cash,
        'total_credit': total_credit,
        'date_from': date_from,
        'date_to': date_to,
        'is_admin': is_admin,
        'latest_record': latest_record,
        'first_record': first_record,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/daily_records_list.html', context)



    
# ============================================
# DAILY RECORD DETAIL VIEW
# ============================================

@login_required
@branch_access_required
def daily_record_detail(request, company_id=None, branch_id=None, record_id=None):
    """View detailed daily record with all account balances"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    branch = get_object_or_404(Branch, id=branch_id, company=company)
    record = get_object_or_404(DailyRecord, id=record_id, company=company, branch=branch)
    
    # Get bank balances
    bank_balances = DailyBankBalance.objects.filter(
        daily_record=record
    ).select_related('bank_account')
    
    # Get M-Pesa balances
    mpesa_balances = DailyMpesaBalance.objects.filter(
        daily_record=record
    ).select_related('mpesa_account')
    
    context = {
        'company': company,
        'branch': branch,
        'record': record,
        'bank_balances': bank_balances,
        'mpesa_balances': mpesa_balances,
        'total_bank': record.total_bank_balance,
        'total_mpesa': record.total_mpesa_balance,
        'net_balance': record.net_balance,
        'is_admin': is_admin_or_manager(request.user),
    }
    return render(request, 'treasury/daily_record_detail.html', context)


# ============================================
# MOVEMENTS (BOOST & TRANSFER)
# ============================================

@login_required
def movement_create(request, company_id=None, branch_id=None):
    """Create a movement (BOOST or Transfer)"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    # Get the user's branch
    user_branch = get_user_branch(request.user)
    
    # Determine which branch to use
    branch = None
    
    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            # If no branch specified, use first active branch
            branch = Branch.objects.filter(company=company, is_active=True).first()
        
        if not branch:
            messages.error(request, 'No branch available. Please create a branch first.')
            return redirect('treasury:dashboard', company_id=company.id)
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)
        
        # If branch_id in URL doesn't match user's branch, redirect to user's branch
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only create movements for your assigned branch: {user_branch.name}')
            return redirect('treasury:movement_create', company_id=company.id, branch_id=user_branch.id)
        
        branch = user_branch
    
    if not branch:
        messages.error(request, 'No branch available. Please create a branch first.')
        return redirect('treasury:dashboard', company_id=company.id)
    
    treasury = get_treasury(company, branch)
    
    # Get bank and M-Pesa accounts for selection
    bank_accounts = BankAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    )
    
    mpesa_accounts = MpesaAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    )
    
    if request.method == 'POST':
        print("=" * 50)
        print("POST DATA:", request.POST)
        print("=" * 50)
        
        movement_type = request.POST.get('movement_type')
        amount = request.POST.get('amount', 0)
        reason = request.POST.get('reason', '')
        
        # Convert amount to Decimal
        try:
            amount = Decimal(amount)
        except:
            amount = Decimal('0')
        
        if amount <= 0:
            messages.error(request, 'Amount must be greater than 0')
            return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
        
        try:
            with transaction.atomic():
                if movement_type == 'BOOST':
                    # BOOST - external money injection
                    boost_source = request.POST.get('boost_source')
                    boost_destination = request.POST.get('boost_destination')
                    boost_reference = request.POST.get('boost_reference', '')
                    boost_notes = request.POST.get('boost_notes', '')
                    
                    print(f"BOOST - Source: {boost_source}, Destination: {boost_destination}")
                    
                    if not boost_source:
                        messages.error(request, 'Please select a boost source')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    if not boost_destination:
                        messages.error(request, 'Please select a destination account')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    # Validate destination account
                    valid_accounts = ['BANK', 'MPESA', 'CASH', 'CREDIT']
                    if boost_destination not in valid_accounts:
                        messages.error(request, f'Invalid destination account. Must be one of: {", ".join(valid_accounts)}')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    # Create boost movement
                    movement = Movement.objects.create(
                        company=company,
                        branch=branch,
                        treasury=treasury,
                        movement_type=Movement.MovementType.BOOST,
                        from_account=Movement.AccountType.EXTERNAL,
                        to_account=boost_destination,
                        amount=amount,
                        reason=reason or f"BOOST from {dict(Movement.BoostSource.choices).get(boost_source, boost_source)}",
                        boost_source=boost_source,
                        boost_reference=boost_reference,
                        boost_notes=boost_notes,
                        created_by=request.user,
                        status=Movement.Status.COMPLETED
                    )
                    
                    # Update treasury balance
                    balance_map = {
                        'BANK': 'total_bank_balance',
                        'MPESA': 'total_mpesa_balance',
                        'CASH': 'cash_balance',
                        'CREDIT': 'credit_balance',
                    }
                    
                    field = balance_map.get(boost_destination)
                    if field:
                        setattr(treasury, field, getattr(treasury, field) + amount)
                        treasury.save()
                        messages.success(request, f'✅ BOOST of KES {amount:,.2f} injected successfully into {movement.get_to_account_display()}!')
                    else:
                        messages.error(request, f'Error updating balance for {boost_destination}')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                elif movement_type == 'TRANSFER':
                    # Transfer between accounts
                    transfer_from = request.POST.get('transfer_from')
                    transfer_to = request.POST.get('transfer_to')
                    
                    print(f"TRANSFER - From: {transfer_from}, To: {transfer_to}")
                    
                    if not transfer_from or not transfer_to:
                        messages.error(request, 'Please select source and destination accounts')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    if transfer_from == transfer_to:
                        messages.error(request, 'Cannot transfer to the same account')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    # Validate accounts
                    valid_accounts = ['BANK', 'MPESA', 'CASH', 'CREDIT']
                    if transfer_from not in valid_accounts:
                        messages.error(request, f'Invalid source account: {transfer_from}')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    if transfer_to not in valid_accounts:
                        messages.error(request, f'Invalid destination account: {transfer_to}')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    # Check sufficient balance
                    balance_map = {
                        'BANK': treasury.total_bank_balance,
                        'MPESA': treasury.total_mpesa_balance,
                        'CASH': treasury.cash_balance,
                        'CREDIT': treasury.credit_balance,
                    }
                    
                    available_balance = balance_map.get(transfer_from, 0)
                    if available_balance < amount:
                        messages.error(request, f'Insufficient {transfer_from} balance. Available: KES {available_balance:,.2f}, Required: KES {amount:,.2f}')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                    # Create transfer movement
                    movement = Movement.objects.create(
                        company=company,
                        branch=branch,
                        treasury=treasury,
                        movement_type=Movement.MovementType.TRANSFER,
                        from_account=transfer_from,
                        to_account=transfer_to,
                        amount=amount,
                        reason=reason or f"Transfer from {transfer_from} to {transfer_to}",
                        created_by=request.user,
                        status=Movement.Status.COMPLETED
                    )
                    
                    # Update treasury balances
                    from_balance_map = {
                        'BANK': 'total_bank_balance',
                        'MPESA': 'total_mpesa_balance',
                        'CASH': 'cash_balance',
                        'CREDIT': 'credit_balance',
                    }
                    
                    to_balance_map = {
                        'BANK': 'total_bank_balance',
                        'MPESA': 'total_mpesa_balance',
                        'CASH': 'cash_balance',
                        'CREDIT': 'credit_balance',
                    }
                    
                    from_field = from_balance_map.get(transfer_from)
                    to_field = to_balance_map.get(transfer_to)
                    
                    if from_field and to_field:
                        setattr(treasury, from_field, getattr(treasury, from_field) - amount)
                        setattr(treasury, to_field, getattr(treasury, to_field) + amount)
                        treasury.save()
                        messages.success(request, f'✅ Successfully transferred KES {amount:,.2f} from {movement.get_from_account_display()} to {movement.get_to_account_display()}!')
                    else:
                        messages.error(request, 'Error updating balances')
                        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                    
                else:
                    messages.error(request, f'Invalid movement type: {movement_type}')
                    return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
                
                # Log transaction
                log_transaction(
                    treasury,
                    'movement' if movement_type == 'TRANSFER' else 'boost',
                    {'net': amount},
                    movement.reason,
                    request.user
                )
                
                # Redirect to branch treasury on success
                return redirect('treasury:branch_treasury', company_id=company.id, branch_id=branch.id)
                
        except ValueError as e:
            messages.error(request, f'Error: {str(e)}')
            print(f"VALUE ERROR: {str(e)}")
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            import traceback
            traceback.print_exc()
            print(f"EXCEPTION: {str(e)}")
        
        # If we get here, there was an error - stay on the form page
        return redirect('treasury:movement_create', company_id=company.id, branch_id=branch.id)
    
    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)
    
    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']
    
    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'account_types': Movement.AccountType.choices,
        'movement_types': Movement.MovementType.choices,
        'boost_sources': Movement.BoostSource.choices,
        'bank_accounts': bank_accounts,
        'mpesa_accounts': mpesa_accounts,
        'today': timezone.now().date(),
        'is_admin': is_admin,
        'user_branch': user_branch,
        'all_branches': all_branches,
    }
    return render(request, 'treasury/movement_form.html', context)

    
# ============================================
# MOVEMENTS LIST
# ============================================

# ============================================
# MOVEMENTS LIST
# ============================================

# ============================================
# MOVEMENTS LIST
# ============================================

@login_required
def movements_list(request, company_id=None, branch_id=None):
    """List all movements for a branch (with branch selector for admins)"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')

    # Get the user's branch
    user_branch = get_user_branch(request.user)

    # Determine which branch to use
    branch = None

    # Super admin and company admin can access any branch
    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, company=company)
        else:
            # If no branch specified, use first active branch
            branch = Branch.objects.filter(company=company, is_active=True).first()

        if not branch:
            messages.error(request, 'No branch available. Please create a branch first.')
            return redirect('treasury:dashboard', company_id=company.id)
    else:
        # Other roles must use their own branch
        if not user_branch:
            messages.error(request, 'You are not assigned to any branch. Please contact your administrator.')
            return redirect('treasury:dashboard', company_id=company.id)

        # If branch_id in URL doesn't match user's branch, redirect to user's branch
        if branch_id and int(branch_id) != user_branch.id:
            messages.error(request, f'You can only view movements for your assigned branch: {user_branch.name}')
            return redirect('treasury:movements_list', company_id=company.id, branch_id=user_branch.id)

        branch = user_branch

    if not branch:
        messages.error(request, 'No branch available.')
        return redirect('treasury:dashboard', company_id=company.id)

    treasury = get_treasury(company, branch)

    # Get filters
    movement_type = request.GET.get('movement_type')
    from_account = request.GET.get('from_account')
    to_account = request.GET.get('to_account')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    movements = Movement.objects.filter(
        company=company,
        branch=branch
    )

    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if from_account:
        movements = movements.filter(from_account=from_account)
    if to_account:
        movements = movements.filter(to_account=to_account)
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)

    movements = movements.order_by('-created_at')

    paginator = Paginator(movements, 30)
    page = request.GET.get('page', 1)
    movements_page = paginator.get_page(page)

    # Summary stats
    total_boost = movements.filter(movement_type=Movement.MovementType.BOOST).aggregate(
        total=Sum('amount')
    )['total'] or 0

    total_transfers = movements.filter(movement_type=Movement.MovementType.TRANSFER).aggregate(
        total=Sum('amount')
    )['total'] or 0

    # ============================================
    # CURRENT NET BALANCE - based on last day's report
    # ============================================
    # Use the most recent DailyRecord's net_balance as the true "current" balance.
    # Fall back to treasury.net_balance if no daily record exists yet.
    latest_record = DailyRecord.objects.filter(
        company=company,
        branch=branch
    ).order_by('-date').first()

    if latest_record:
        total_net = latest_record.net_balance
    else:
        total_net = treasury.net_balance

    # Get all branches for the branch selector (for admins)
    all_branches = Branch.objects.filter(company=company, is_active=True)

    # Determine if user is admin (can switch branches)
    is_admin = request.user.role in ['super_admin', 'company_admin']

    context = {
        'company': company,
        'branch': branch,
        'treasury': treasury,
        'movements': movements_page,
        'total_boost': total_boost,
        'total_transfers': total_transfers,
        'total_net': total_net,
        'latest_record': latest_record,
        'movement_types': Movement.MovementType.choices,
        'account_types': Movement.AccountType.choices,
        'selected_movement_type': movement_type,
        'selected_from_account': from_account,
        'selected_to_account': to_account,
        'date_from': date_from,
        'date_to': date_to,
        'is_admin': is_admin,
        'all_branches': all_branches,
        'user_branch': user_branch,
    }
    return render(request, 'treasury/movements_list.html', context)


    
# ============================================
# API ENDPOINTS
# ============================================

@login_required
@branch_access_required
def api_get_balances(request, company_id=None, branch_id=None):
    """API endpoint to get current balances for a branch"""
    company = get_user_company(request, company_id)
    if not company:
        return JsonResponse({'error': 'Company not found'}, status=404)
    
    branch = get_object_or_404(Branch, id=branch_id, company=company)
    treasury = get_treasury(company, branch)
    
    # Get all bank accounts with current balances
    bank_accounts = BankAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    )
    
    # Get all M-Pesa accounts with current balances
    mpesa_accounts = MpesaAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    )
    
    data = {
        'branch': {
            'id': branch.id,
            'name': branch.name,
            'code': branch.code,
        },
        'treasury': {
            'total_bank': float(treasury.total_bank_balance),
            'total_mpesa': float(treasury.total_mpesa_balance),
            'cash': float(treasury.cash_balance),
            'credit': float(treasury.credit_balance),
            'net_balance': float(treasury.net_balance),
            'liquid_balance': float(treasury.liquid_balance),
        },
        'bank_accounts': [
            {
                'id': bank.id,
                'name': bank.account_name,
                'bank_type': bank.get_bank_type_display(),
                'balance': float(bank.current_balance),
            }
            for bank in bank_accounts
        ],
        'mpesa_accounts': [
            {
                'id': mpesa.id,
                'name': mpesa.till_name,
                'till_number': mpesa.till_number,
                'balance': float(mpesa.current_balance),
            }
            for mpesa in mpesa_accounts
        ],
        'updated_at': treasury.updated_at.isoformat() if treasury.updated_at else None,
    }
    return JsonResponse(data)


@login_required
@branch_access_required
def api_get_daily_record(request, company_id=None, branch_id=None, date=None):
    """API endpoint to get daily record for a specific date"""
    company = get_user_company(request, company_id)
    if not company:
        return JsonResponse({'error': 'Company not found'}, status=404)
    
    branch = get_object_or_404(Branch, id=branch_id, company=company)
    
    if not date:
        date = timezone.now().date()
    
    daily_record = DailyRecord.objects.filter(
        company=company,
        branch=branch,
        date=date
    ).first()
    
    if not daily_record:
        return JsonResponse({'error': 'No record found for this date'}, status=404)
    
    # Get bank balances
    bank_balances = DailyBankBalance.objects.filter(
        daily_record=daily_record
    ).select_related('bank_account')
    
    # Get M-Pesa balances
    mpesa_balances = DailyMpesaBalance.objects.filter(
        daily_record=daily_record
    ).select_related('mpesa_account')
    
    data = {
        'date': daily_record.date.isoformat(),
        'cash_balance': float(daily_record.cash_balance),
        'credit_balance': float(daily_record.credit_balance),
        'total_bank': float(daily_record.total_bank_balance),
        'total_mpesa': float(daily_record.total_mpesa_balance),
        'net_balance': float(daily_record.net_balance),
        'notes': daily_record.notes,
        'bank_accounts': [
            {
                'account_name': b.bank_account.account_name,
                'bank_type': b.bank_account.get_bank_type_display(),
                'closing_balance': float(b.closing_balance),
            }
            for b in bank_balances
        ],
        'mpesa_accounts': [
            {
                'till_name': m.mpesa_account.till_name,
                'till_number': m.mpesa_account.till_number,
                'closing_balance': float(m.closing_balance),
            }
            for m in mpesa_balances
        ],
    }
    return JsonResponse(data)


# ============================================
# EXPORT FUNCTIONS (CSV)
# ============================================

@login_required
@branch_access_required
def export_daily_records_csv(request, company_id=None, branch_id=None):
    """Export daily records to CSV"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    branch = get_object_or_404(Branch, id=branch_id, company=company)
    
    records = DailyRecord.objects.filter(
        company=company,
        branch=branch
    ).order_by('-date')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="daily_records_{branch.code}_{timezone.now().date()}.csv"'
    
    writer = csv.writer(response)
    
    # Header
    headers = ['Date', 'Cash', 'Credit', 'Total Bank', 'Total M-Pesa', 'Net Balance', 'Notes']
    
    # Get all bank account names for headers
    bank_accounts = BankAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    ).order_by('account_name')
    
    mpesa_accounts = MpesaAccount.objects.filter(
        company=company,
        branch=branch,
        is_active=True
    ).order_by('till_name')
    
    for bank in bank_accounts:
        headers.append(f'Bank: {bank.account_name}')
    
    for mpesa in mpesa_accounts:
        headers.append(f'M-Pesa: {mpesa.till_name}')
    
    writer.writerow(headers)
    
    # Data rows
    for record in records:
        row = [
            record.date,
            float(record.cash_balance),
            float(record.credit_balance),
            float(record.total_bank_balance),
            float(record.total_mpesa_balance),
            float(record.net_balance),
            record.notes
        ]
        
        # Add bank balances
        bank_balances = {b.bank_account_id: b.closing_balance for b in record.bank_balances.all()}
        for bank in bank_accounts:
            row.append(float(bank_balances.get(bank.id, 0)))
        
        # Add M-Pesa balances
        mpesa_balances = {m.mpesa_account_id: m.closing_balance for m in record.mpesa_balances.all()}
        for mpesa in mpesa_accounts:
            row.append(float(mpesa_balances.get(mpesa.id, 0)))
        
        writer.writerow(row)
    
    return response


@login_required
@branch_access_required
def export_movements_csv(request, company_id=None, branch_id=None):
    """Export movements to CSV"""
    company = get_user_company(request, company_id)
    if not company:
        return redirect('dashboard')
    
    branch = get_object_or_404(Branch, id=branch_id, company=company)
    
    movements = Movement.objects.filter(
        company=company,
        branch=branch
    ).order_by('-created_at')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="movements_{branch.code}_{timezone.now().date()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Type', 'From', 'To', 'Amount', 'Reason', 'Boost Source'])
    
    for m in movements:
        writer.writerow([
            m.created_at.strftime('%Y-%m-%d %H:%M'),
            m.movement_type,
            m.get_from_account_display(),
            m.get_to_account_display(),
            float(m.amount),
            m.reason,
            m.get_boost_source_display() if m.boost_source else ''
        ])
    
    return response