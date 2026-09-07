from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from .models import (
    Treasury, Movement, DailyRecord, DailyBankBalance, 
    DailyMpesaBalance, BankAccount, MpesaAccount
)


def create_boost_movement(company, branch, amount, boost_source, to_account='BANK', 
                          reason="", boost_reference="", boost_notes="", created_by=None):
    """
    Create a BOOST movement - inject external money into treasury
    """
    # Get or create treasury
    treasury, created = Treasury.objects.get_or_create(
        company=company,
        branch=branch
    )
    
    # Create the movement
    movement = Movement.objects.create(
        company=company,
        branch=branch,
        treasury=treasury,
        movement_type=Movement.MovementType.BOOST,
        from_account=Movement.AccountType.EXTERNAL,
        to_account=to_account,
        amount=amount,
        reason=reason or f"BOOST from {dict(Movement.BoostSource.choices).get(boost_source)}",
        boost_source=boost_source,
        boost_reference=boost_reference,
        boost_notes=boost_notes,
        created_by=created_by,
        status=Movement.Status.COMPLETED
    )
    
    # Update treasury balance
    balance_map = {
        'BANK': 'total_bank_balance',
        'MPESA': 'total_mpesa_balance',
        'CASH': 'cash_balance',
        'CREDIT': 'credit_balance',
    }
    
    field = balance_map.get(to_account)
    if field:
        setattr(treasury, field, getattr(treasury, field) + amount)
        treasury.save()
    
    return movement


def create_transfer_movement(company, branch, from_account, to_account, amount, 
                             reason="", created_by=None):
    """
    Create a transfer movement between accounts
    """
    # Get treasury
    treasury = Treasury.objects.get(company=company, branch=branch)
    
    # Check sufficient balance
    balance_map = {
        'BANK': treasury.total_bank_balance,
        'MPESA': treasury.total_mpesa_balance,
        'CASH': treasury.cash_balance,
        'CREDIT': treasury.credit_balance,
    }
    
    if balance_map.get(from_account, 0) < amount:
        raise ValueError(f"Insufficient {from_account} balance. Available: {balance_map.get(from_account)}")
    
    # Create the movement
    movement = Movement.objects.create(
        company=company,
        branch=branch,
        treasury=treasury,
        movement_type=Movement.MovementType.TRANSFER,
        from_account=from_account,
        to_account=to_account,
        amount=amount,
        reason=reason or f"Transfer from {from_account} to {to_account}",
        created_by=created_by,
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
    
    from_field = from_balance_map.get(from_account)
    to_field = to_balance_map.get(to_account)
    
    if from_field and to_field:
        setattr(treasury, from_field, getattr(treasury, from_field) - amount)
        setattr(treasury, to_field, getattr(treasury, to_field) + amount)
        treasury.save()
    
    return movement


def create_daily_record(company, branch, date, cash_balance=0, credit_balance=0, 
                        bank_balances=None, mpesa_balances=None, notes=""):
    """
    Create a daily record with all bank and M-Pesa account balances
    """
    treasury, _ = Treasury.objects.get_or_create(company=company, branch=branch)
    
    with transaction.atomic():
        # Create the daily record
        daily_record = DailyRecord.objects.create(
            company=company,
            branch=branch,
            treasury=treasury,
            date=date,
            cash_balance=cash_balance,
            credit_balance=credit_balance,
            notes=notes
        )
        
        # Get all active bank accounts for this branch
        bank_accounts = BankAccount.objects.filter(
            company=company, 
            branch=branch, 
            is_active=True
        )
        
        # Create daily bank balances
        for bank in bank_accounts:
            balance = bank_balances.get(bank.id, 0) if bank_balances else bank.current_balance
            DailyBankBalance.objects.create(
                daily_record=daily_record,
                bank_account=bank,
                closing_balance=balance
            )
            # Update account current balance
            bank.current_balance = balance
            bank.save()
        
        # Get all active M-Pesa accounts for this branch
        mpesa_accounts = MpesaAccount.objects.filter(
            company=company, 
            branch=branch, 
            is_active=True
        )
        
        # Create daily M-Pesa balances
        for mpesa in mpesa_accounts:
            balance = mpesa_balances.get(mpesa.id, 0) if mpesa_balances else mpesa.current_balance
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
        
        return daily_record


def update_daily_balances(daily_record, bank_balances=None, mpesa_balances=None,
                          cash_balance=None, credit_balance=None):
    """
    Update daily record with specific bank and M-Pesa balances
    """
    with transaction.atomic():
        # Update bank balances
        if bank_balances:
            for bank_id, balance in bank_balances.items():
                DailyBankBalance.objects.update_or_create(
                    daily_record=daily_record,
                    bank_account_id=bank_id,
                    defaults={'closing_balance': balance}
                )
                # Update bank account current balance
                bank = BankAccount.objects.get(id=bank_id)
                bank.current_balance = balance
                bank.save()
        
        # Update M-Pesa balances
        if mpesa_balances:
            for mpesa_id, balance in mpesa_balances.items():
                DailyMpesaBalance.objects.update_or_create(
                    daily_record=daily_record,
                    mpesa_account_id=mpesa_id,
                    defaults={'closing_balance': balance}
                )
                # Update M-Pesa account current balance
                mpesa = MpesaAccount.objects.get(id=mpesa_id)
                mpesa.current_balance = balance
                mpesa.save()
        
        # Update cash balance
        if cash_balance is not None:
            daily_record.cash_balance = cash_balance
        
        # Update credit balance
        if credit_balance is not None:
            daily_record.credit_balance = credit_balance
        
        daily_record.save()
        
        # Update treasury aggregated balances
        daily_record.treasury.total_bank_balance = daily_record.total_bank_balance
        daily_record.treasury.total_mpesa_balance = daily_record.total_mpesa_balance
        daily_record.treasury.cash_balance = daily_record.cash_balance
        daily_record.treasury.credit_balance = daily_record.credit_balance
        daily_record.treasury.save()
        
        return daily_record


def get_balance_summary(company, branch):
    """
    Get a summary of all balances for a branch
    """
    treasury, _ = Treasury.objects.get_or_create(company=company, branch=branch)
    
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
    
    return {
        'treasury': {
            'total_bank': treasury.total_bank_balance,
            'total_mpesa': treasury.total_mpesa_balance,
            'cash': treasury.cash_balance,
            'credit': treasury.credit_balance,
            'net': treasury.net_balance,
            'liquid': treasury.liquid_balance,
        },
        'bank_accounts': [
            {
                'id': bank.id,
                'name': bank.account_name,
                'type': bank.get_bank_type_display(),
                'balance': bank.current_balance,
            }
            for bank in bank_accounts
        ],
        'mpesa_accounts': [
            {
                'id': mpesa.id,
                'name': mpesa.till_name,
                'number': mpesa.till_number,
                'balance': mpesa.current_balance,
            }
            for mpesa in mpesa_accounts
        ]
    }


def get_daily_record_with_balances(daily_record):
    """
    Get a daily record with all its bank and M-Pesa balances
    """
    bank_balances = DailyBankBalance.objects.filter(
        daily_record=daily_record
    ).select_related('bank_account')
    
    mpesa_balances = DailyMpesaBalance.objects.filter(
        daily_record=daily_record
    ).select_related('mpesa_account')
    
    return {
        'daily_record': daily_record,
        'bank_balances': [
            {
                'account_id': b.bank_account_id,
                'account_name': b.bank_account.account_name,
                'bank_type': b.bank_account.get_bank_type_display(),
                'closing_balance': b.closing_balance,
            }
            for b in bank_balances
        ],
        'mpesa_balances': [
            {
                'account_id': m.mpesa_account_id,
                'till_name': m.mpesa_account.till_name,
                'till_number': m.mpesa_account.till_number,
                'closing_balance': m.closing_balance,
            }
            for m in mpesa_balances
        ],
        'cash_balance': daily_record.cash_balance,
        'credit_balance': daily_record.credit_balance,
        'total_bank': daily_record.total_bank_balance,
        'total_mpesa': daily_record.total_mpesa_balance,
        'net_balance': daily_record.net_balance,
    }


def get_movement_summary(company, branch, start_date=None, end_date=None):
    """
    Get summary of movements for a branch
    """
    movements = Movement.objects.filter(company=company, branch=branch)
    
    if start_date:
        movements = movements.filter(created_at__date__gte=start_date)
    if end_date:
        movements = movements.filter(created_at__date__lte=end_date)
    
    total_boost = movements.filter(movement_type=Movement.MovementType.BOOST).aggregate(
        total=models.Sum('amount')
    )['total'] or 0
    
    total_transfers = movements.filter(movement_type=Movement.MovementType.TRANSFER).aggregate(
        total=models.Sum('amount')
    )['total'] or 0
    
    return {
        'total_boost': total_boost,
        'total_transfers': total_transfers,
        'total_movements': movements.count(),
        'boost_count': movements.filter(movement_type=Movement.MovementType.BOOST).count(),
        'transfer_count': movements.filter(movement_type=Movement.MovementType.TRANSFER).count(),
    }


def get_branch_treasury_data(company, branch):
    """
    Get all treasury data for a branch in one call
    """
    treasury, _ = Treasury.objects.get_or_create(company=company, branch=branch)
    
    # Get today's record
    today_record = DailyRecord.objects.filter(
        company=company,
        branch=branch,
        date=timezone.now().date()
    ).first()
    
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
    
    # Get recent movements
    recent_movements = Movement.objects.filter(
        company=company,
        branch=branch
    ).order_by('-created_at')[:5]
    
    return {
        'treasury': treasury,
        'today_record': today_record,
        'bank_accounts': bank_accounts,
        'mpesa_accounts': mpesa_accounts,
        'recent_movements': recent_movements,
        'total_bank': treasury.total_bank_balance,
        'total_mpesa': treasury.total_mpesa_balance,
        'cash_balance': treasury.cash_balance,
        'credit_balance': treasury.credit_balance,
        'net_balance': treasury.net_balance,
        'liquid_balance': treasury.liquid_balance,
    }


def generate_company_treasury_report(company, start_date=None, end_date=None):
    """
    Generate a treasury report for a company
    """
    from django.db.models import Sum, Avg, Count, Q
    
    if not start_date:
        start_date = timezone.now().date().replace(day=1)
    if not end_date:
        end_date = timezone.now().date()
    
    # Get all branches
    branches = Branch.objects.filter(company=company, is_active=True)
    
    report_data = []
    total_net = 0
    
    for branch in branches:
        treasury, _ = Treasury.objects.get_or_create(company=company, branch=branch)
        
        # Get daily records in date range
        daily_records = DailyRecord.objects.filter(
            company=company,
            branch=branch,
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        # Calculate average balances
        avg_bank = daily_records.aggregate(avg=Avg('total_bank_balance'))['avg'] or 0
        avg_mpesa = daily_records.aggregate(avg=Avg('total_mpesa_balance'))['avg'] or 0
        avg_cash = daily_records.aggregate(avg=Avg('cash_balance'))['avg'] or 0
        avg_credit = daily_records.aggregate(avg=Avg('credit_balance'))['avg'] or 0
        avg_net = daily_records.aggregate(avg=Avg('net_balance'))['avg'] or 0
        
        # Get movements in date range
        movements = Movement.objects.filter(
            company=company,
            branch=branch,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        total_boost_in = movements.filter(
            movement_type=Movement.MovementType.BOOST
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        total_net += treasury.net_balance
        
        report_data.append({
            'branch': branch,
            'treasury': treasury,
            'current_net': treasury.net_balance,
            'record_count': daily_records.count(),
            'avg_bank': avg_bank,
            'avg_mpesa': avg_mpesa,
            'avg_cash': avg_cash,
            'avg_credit': avg_credit,
            'avg_net': avg_net,
            'total_boost_in': total_boost_in,
            'movement_count': movements.count(),
        })
    
    return {
        'company': company,
        'start_date': start_date,
        'end_date': end_date,
        'branches': report_data,
        'total_net': total_net,
        'total_branches': len(report_data),
    }