from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import datetime, timedelta, date
from decimal import Decimal
from django.core.paginator import Paginator
from django.db import transaction

from apps.companies.models import Company
from apps.company.models import Expense
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)
from .models import (
    Branch, Sale, SaleItem, PurchaseOrder,
    COGSAccount, COGSTransaction, PurchaseRecord,
    COGSAllocationRule, COGSSummary
)


# ============================================
# COGS CALCULATION HELPERS
# ============================================

def get_cogs_from_sale(sale):
    """Calculate COGS for a single sale"""
    total_cogs = Decimal('0.00')
    
    for item in sale.items.all():
        if item.content_type:
            try:
                product = item.content_type.get_object_for_this_type(id=item.object_id)
                if hasattr(product, 'purchase_price') and product.purchase_price:
                    total_cogs += product.purchase_price * item.quantity
                else:
                    total_cogs += item.unit_price * Decimal('0.7') * item.quantity
            except:
                total_cogs += item.unit_price * Decimal('0.7') * item.quantity
        else:
            total_cogs += item.unit_price * Decimal('0.7') * item.quantity
    
    return total_cogs


def calculate_total_cogs_from_sales(company, branch=None):
    """Calculate total COGS from ALL sales"""
    sales = Sale.objects.filter(company=company, payment_status='paid')
    if branch:
        sales = sales.filter(branch=branch)
    
    total_cogs = Decimal('0.00')
    for sale in sales:
        total_cogs += get_cogs_from_sale(sale)
    
    return total_cogs


def get_total_revenue(company, branch=None):
    """Get total revenue from sales"""
    sales = Sale.objects.filter(company=company, payment_status='paid')
    if branch:
        sales = sales.filter(branch=branch)
    return sales.aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')


def get_total_purchases(company, branch=None):
    """Get total purchases amount"""
    purchases = PurchaseRecord.objects.filter(company=company, status='completed')
    if branch:
        purchases = purchases.filter(branch=branch)
    return purchases.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')


def get_total_expenses(company, branch=None):
    """Get total expenses amount"""
    expenses = Expense.objects.filter(company=company)
    if branch:
        expenses = expenses.filter(branch=branch)
    return expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')


def get_effective_cogs_balance(company, branch=None):
    """COGS Balance = Total COGS from sales - Total Purchases"""
    total_cogs = calculate_total_cogs_from_sales(company, branch)
    total_purchases = get_total_purchases(company, branch)
    return total_cogs - total_purchases


def get_effective_profit_balance(company, branch=None):
    """Profit Balance = Total Revenue - Total COGS - Total Expenses"""
    total_revenue = get_total_revenue(company, branch)
    total_cogs = calculate_total_cogs_from_sales(company, branch)
    total_expenses = get_total_expenses(company, branch)
    gross_profit = total_revenue - total_cogs
    net_profit = gross_profit - total_expenses
    return net_profit


def get_cogs_balance(company, branch=None):
    """Alias for get_effective_cogs_balance"""
    return get_effective_cogs_balance(company, branch)


def get_cogs_summary(company, start_date, end_date, branch=None):
    """Get COGS summary for a date range"""
    sales = Sale.objects.filter(
        company=company,
        payment_status='paid',
        sale_date__date__gte=start_date,
        sale_date__date__lte=end_date
    )
    if branch:
        sales = sales.filter(branch=branch)
    
    total_credits = Decimal('0.00')
    sale_count = 0
    for sale in sales:
        cogs = get_cogs_from_sale(sale)
        if cogs > 0:
            total_credits += cogs
            sale_count += 1
    
    purchases = PurchaseRecord.objects.filter(
        company=company,
        status='completed',
        purchase_date__gte=start_date,
        purchase_date__lte=end_date
    )
    if branch:
        purchases = purchases.filter(branch=branch)
    
    total_debits = purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    opening_sales = Sale.objects.filter(
        company=company,
        payment_status='paid',
        sale_date__date__lt=start_date
    )
    if branch:
        opening_sales = opening_sales.filter(branch=branch)
    
    opening_credits = Decimal('0.00')
    for sale in opening_sales:
        opening_credits += get_cogs_from_sale(sale)
    
    opening_purchases = PurchaseRecord.objects.filter(
        company=company,
        status='completed',
        purchase_date__lt=start_date
    )
    if branch:
        opening_purchases = opening_purchases.filter(branch=branch)
    
    opening_debits = opening_purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    opening_balance = opening_credits - opening_debits
    closing_balance = opening_balance + total_credits - total_debits
    
    return {
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
        'total_credits': total_credits,
        'total_debits': total_debits,
        'net_change': total_credits - total_debits,
        'transaction_count': sale_count + purchases.count(),
        'credit_count': sale_count,
        'debit_count': purchases.count(),
    }


def update_cogs_from_sale(sale, user=None):
    """Record COGS from sale (for future use)"""
    pass


def update_cogs_from_purchase(purchase_record, user=None):
    """Just mark the purchase as completed - no COGSAccount update needed"""
    pass


# ============================================
# DEBUG VIEW
# ============================================

@login_required
def debug_cogs_balance(request):
    """Debug view to check COGS calculation"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    
    sales = Sale.objects.filter(company=company, payment_status='paid')
    if branch_id:
        sales = sales.filter(branch_id=branch_id)
    
    total_cogs = Decimal('0.00')
    sale_details = []
    
    for sale in sales:
        cogs = get_cogs_from_sale(sale)
        if cogs > 0:
            total_cogs += cogs
            sale_details.append({
                'id': sale.id,
                'company_sale_id': sale.company_sale_id,
                'customer': sale.customer_name,
                'amount': float(sale.net_amount),
                'cogs': float(cogs),
                'date': sale.sale_date.strftime('%Y-%m-%d'),
            })
    
    purchases = PurchaseRecord.objects.filter(company=company, status='completed')
    if branch_id:
        purchases = purchases.filter(branch_id=branch_id)
    
    total_purchases = purchases.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    balance = total_cogs - total_purchases
    
    return JsonResponse({
        'total_sales': sales.count(),
        'sales_with_cogs': len(sale_details),
        'total_cogs': float(total_cogs),
        'total_purchases': float(total_purchases),
        'balance': float(balance),
        'sales': sale_details[:20],
        'purchase_count': purchases.count(),
        'company_name': company.name,
    })


# ============================================
# FINANCE DASHBOARD
# ============================================

@login_required
def finance_dashboard(request):
    """Main finance dashboard with COGS balance and Profit balance"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    branches = Branch.objects.filter(company=company, is_active=True)
    today = timezone.now().date()
    
    current_balance = get_effective_cogs_balance(company, branch_id)
    current_profit_balance = get_effective_profit_balance(company, branch_id)
    
    today_sales = Sale.objects.filter(
        company=company,
        payment_status='paid',
        sale_date__date=today
    )
    if branch_id:
        today_sales = today_sales.filter(branch_id=branch_id)
    
    today_cogs = Decimal('0.00')
    for sale in today_sales:
        today_cogs += get_cogs_from_sale(sale)
    
    today_purchases = PurchaseRecord.objects.filter(
        company=company,
        status='completed',
        purchase_date=today
    )
    if branch_id:
        today_purchases = today_purchases.filter(branch_id=branch_id)
    
    today_purchases_value = today_purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    def get_cogs_for_period(start_date, end_date):
        sales = Sale.objects.filter(
            company=company,
            payment_status='paid',
            sale_date__date__gte=start_date,
            sale_date__date__lte=end_date
        )
        if branch_id:
            sales = sales.filter(branch_id=branch_id)
        
        total = Decimal('0.00')
        for sale in sales:
            total += get_cogs_from_sale(sale)
        return total
    
    week_cogs = get_cogs_for_period(week_start, week_end)
    month_cogs = get_cogs_for_period(today.replace(day=1), today)
    
    yesterday = today - timedelta(days=1)
    yesterday_cogs = get_cogs_for_period(yesterday, yesterday)
    
    last_week_start = week_start - timedelta(days=7)
    last_week_end = last_week_start + timedelta(days=6)
    last_week_cogs = get_cogs_for_period(last_week_start, last_week_end)
    
    if today.month == 1:
        last_month_start = today.replace(year=today.year-1, month=12, day=1)
        last_month_end = today.replace(year=today.year-1, month=12, day=31)
    else:
        last_month_start = today.replace(month=today.month-1, day=1)
        last_month_end = today.replace(month=today.month, day=1) - timedelta(days=1)
    
    last_month_cogs = get_cogs_for_period(last_month_start, last_month_end)
    
    context = {
        'company': company,
        'branches': branches,
        'selected_branch': branch_id,
        'current_balance': current_balance,
        'current_profit_balance': current_profit_balance,
        'today_cogs': today_cogs,
        'yesterday_cogs': yesterday_cogs,
        'week_cogs': week_cogs,
        'last_week_cogs': last_week_cogs,
        'month_cogs': month_cogs,
        'last_month_cogs': last_month_cogs,
        'today_purchases': today_purchases_value,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/dashboard.html', context)


# ============================================
# API COGS BALANCE - For Sidebar Badge
# ============================================

@login_required
def api_cogs_balance(request):
    """API endpoint to get current COGS balance for the sidebar badge"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    branch_id = request.GET.get('branch')
    
    balance = get_effective_cogs_balance(company, branch_id)
    profit_balance = get_effective_profit_balance(company, branch_id)
    total_cogs = calculate_total_cogs_from_sales(company, branch_id)
    total_purchases = get_total_purchases(company, branch_id)
    total_revenue = get_total_revenue(company, branch_id)
    total_expenses = get_total_expenses(company, branch_id)
    
    return JsonResponse({
        'balance': float(balance),
        'formatted': f"KSh {balance:,.2f}",
        'profit_balance': float(profit_balance),
        'profit_formatted': f"KSh {profit_balance:,.2f}",
        'total_cogs': float(total_cogs),
        'total_purchases': float(total_purchases),
        'total_revenue': float(total_revenue),
        'total_expenses': float(total_expenses),
        'gross_profit': float(total_revenue - total_cogs),
    })


# ============================================
# COGS REPORT
# ============================================

@login_required
def cogs_report(request):
    """Generate COGS report with Daily, Weekly, Monthly tables"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    branches = Branch.objects.filter(company=company, is_active=True)
    today = timezone.now().date()
    
    if not date_from:
        date_from = today - timedelta(days=30)
    else:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    
    if not date_to:
        date_to = today
    else:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    sales_qs = Sale.objects.filter(company=company, payment_status='paid')
    if branch_id:
        sales_qs = sales_qs.filter(branch_id=branch_id)
    
    purchases_qs = PurchaseRecord.objects.filter(company=company, status='completed')
    if branch_id:
        purchases_qs = purchases_qs.filter(branch_id=branch_id)
    
    # DAILY COGS RECORDS
    daily_records = []
    week_start = today - timedelta(days=today.weekday())
    current_date = week_start
    running_balance = Decimal('0.00')
    
    while current_date <= week_start + timedelta(days=6):
        day_sales = sales_qs.filter(sale_date__date=current_date)
        day_purchases = purchases_qs.filter(purchase_date=current_date)
        
        day_cogs = Decimal('0.00')
        for sale in day_sales:
            day_cogs += get_cogs_from_sale(sale)
        
        day_purchases_count = day_purchases.count()
        day_purchases_value = day_purchases.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        running_balance += day_cogs - day_purchases_value
        
        daily_records.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'purchases_count': day_purchases_count,
            'cogs': day_cogs,
            'purchases_value': day_purchases_value,
            'closing_balance': running_balance,
            'is_today': current_date == today,
        })
        current_date += timedelta(days=1)
    
    daily_totals = {
        'purchases_count': sum(r['purchases_count'] for r in daily_records),
        'cogs': sum(r['cogs'] for r in daily_records),
        'purchases_value': sum(r['purchases_value'] for r in daily_records),
        'closing_balance': daily_records[-1]['closing_balance'] if daily_records else Decimal('0.00'),
    }
    
    # WEEKLY COGS RECORDS
    weekly_records = []
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    
    running_balance = Decimal('0.00')
    current_week_start = month_start - timedelta(days=month_start.weekday())
    
    while current_week_start <= month_end:
        week_end_date = current_week_start + timedelta(days=6)
        week_start_in_month = max(current_week_start, month_start)
        week_end_in_month = min(week_end_date, month_end)
        
        if week_start_in_month <= week_end_in_month:
            week_sales = sales_qs.filter(
                sale_date__date__gte=week_start_in_month,
                sale_date__date__lte=week_end_in_month
            )
            week_purchases = purchases_qs.filter(
                purchase_date__gte=week_start_in_month,
                purchase_date__lte=week_end_in_month
            )
            
            week_cogs = Decimal('0.00')
            for sale in week_sales:
                week_cogs += get_cogs_from_sale(sale)
            
            week_purchases_count = week_purchases.count()
            week_purchases_value = week_purchases.aggregate(
                total=Sum('total_amount')
            )['total'] or Decimal('0.00')
            
            running_balance += week_cogs - week_purchases_value
            
            thursday = current_week_start + timedelta(days=3)
            iso_week = thursday.isocalendar()
            
            weekly_records.append({
                'year': iso_week[0],
                'week': iso_week[1],
                'week_start': current_week_start,
                'week_end': week_end_date,
                'purchases_count': week_purchases_count,
                'cogs': week_cogs,
                'purchases_value': week_purchases_value,
                'closing_balance': running_balance,
            })
        
        current_week_start += timedelta(days=7)
    
    weekly_totals = {
        'purchases_count': sum(r['purchases_count'] for r in weekly_records),
        'cogs': sum(r['cogs'] for r in weekly_records),
        'purchases_value': sum(r['purchases_value'] for r in weekly_records),
        'closing_balance': weekly_records[-1]['closing_balance'] if weekly_records else Decimal('0.00'),
    }
    
    # MONTHLY COGS RECORDS
    monthly_records = []
    current_year = today.year
    running_balance = Decimal('0.00')
    
    for month in range(1, 13):
        month_start_date = date(current_year, month, 1)
        if month == 12:
            month_end_date = date(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end_date = date(current_year, month + 1, 1) - timedelta(days=1)
        
        month_sales = sales_qs.filter(
            sale_date__date__gte=month_start_date,
            sale_date__date__lte=month_end_date
        )
        month_purchases = purchases_qs.filter(
            purchase_date__gte=month_start_date,
            purchase_date__lte=month_end_date
        )
        
        month_cogs = Decimal('0.00')
        for sale in month_sales:
            month_cogs += get_cogs_from_sale(sale)
        
        month_purchases_count = month_purchases.count()
        month_purchases_value = month_purchases.aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        
        running_balance += month_cogs - month_purchases_value
        
        monthly_records.append({
            'month': month,
            'month_name': month_start_date.strftime('%B'),
            'purchases_count': month_purchases_count,
            'cogs': month_cogs,
            'purchases_value': month_purchases_value,
            'closing_balance': running_balance,
        })
    
    monthly_totals = {
        'purchases_count': sum(r['purchases_count'] for r in monthly_records),
        'cogs': sum(r['cogs'] for r in monthly_records),
        'purchases_value': sum(r['purchases_value'] for r in monthly_records),
        'closing_balance': monthly_records[-1]['closing_balance'] if monthly_records else Decimal('0.00'),
    }
    
    total_cogs_generated = daily_totals['cogs']
    total_cogs_used = daily_totals['purchases_value']
    net_change = total_cogs_generated - total_cogs_used
    closing_balance = daily_totals['closing_balance']
    
    context = {
        'company': company,
        'total_cogs_generated': total_cogs_generated,
        'total_cogs_used': total_cogs_used,
        'net_change': net_change,
        'closing_balance': closing_balance,
        'daily_records': daily_records,
        'daily_totals': daily_totals,
        'weekly_records': weekly_records,
        'weekly_totals': weekly_totals,
        'monthly_records': monthly_records,
        'monthly_totals': monthly_totals,
        'branches': branches,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'current_year': current_year,
        'current_month': today.month,
        'today': today,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_report.html', context)


# ============================================
# COGS DAILY DETAIL VIEW
# ============================================

@login_required
def cogs_daily_detail(request, date_str):
    """View detailed daily purchases list"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    branch_id = request.GET.get('branch')
    
    purchases = PurchaseRecord.objects.filter(
        company=company,
        status='completed',
        purchase_date=report_date
    ).order_by('-purchase_date')
    
    if branch_id:
        purchases = purchases.filter(branch_id=branch_id)
    
    total_purchases_value = purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    purchases_count = purchases.count()
    
    context = {
        'company': company,
        'report_date': report_date,
        'purchases': purchases,
        'total_purchases_value': total_purchases_value,
        'purchases_count': purchases_count,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_daily_detail.html', context)


# ============================================
# COGS WEEKLY DETAIL VIEW
# ============================================

@login_required
def cogs_weekly_detail(request, year, week):
    """View detailed weekly purchases list"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    
    first_day = date(year, 1, 1)
    days_to_thursday = (3 - first_day.weekday()) % 7
    first_thursday = first_day + timedelta(days=days_to_thursday)
    week_1_monday = first_thursday - timedelta(days=3)
    week_start = week_1_monday + timedelta(weeks=week-1)
    week_end = week_start + timedelta(days=6)
    
    purchases = PurchaseRecord.objects.filter(
        company=company,
        status='completed',
        purchase_date__gte=week_start,
        purchase_date__lte=week_end
    ).order_by('-purchase_date')
    
    if branch_id:
        purchases = purchases.filter(branch_id=branch_id)
    
    total_purchases_value = purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    purchases_count = purchases.count()
    
    context = {
        'company': company,
        'week_start': week_start,
        'week_end': week_end,
        'year': year,
        'week': week,
        'purchases': purchases,
        'total_purchases_value': total_purchases_value,
        'purchases_count': purchases_count,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_weekly_detail.html', context)


# ============================================
# COGS MONTHLY DETAIL VIEW
# ============================================

@login_required
def cogs_monthly_detail(request, year, month):
    """View detailed monthly purchases list"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    purchases = PurchaseRecord.objects.filter(
        company=company,
        status='completed',
        purchase_date__gte=month_start,
        purchase_date__lte=month_end
    ).order_by('-purchase_date')
    
    if branch_id:
        purchases = purchases.filter(branch_id=branch_id)
    
    total_purchases_value = purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    purchases_count = purchases.count()
    
    context = {
        'company': company,
        'month_start': month_start,
        'month_end': month_end,
        'year': year,
        'month': month,
        'month_name': month_start.strftime('%B'),
        'purchases': purchases,
        'total_purchases_value': total_purchases_value,
        'purchases_count': purchases_count,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_monthly_detail.html', context)


# ============================================
# COGS TRANSACTIONS VIEW
# ============================================

@login_required
def cogs_transactions(request):
    """View all COGS transactions"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    transaction_type = request.GET.get('transaction_type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search = request.GET.get('search')
    
    transactions = COGSTransaction.objects.filter(company=company)
    
    if branch_id:
        transactions = transactions.filter(branch_id=branch_id)
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if date_from:
        transactions = transactions.filter(transaction_date__date__gte=date_from)
    if date_to:
        transactions = transactions.filter(transaction_date__date__lte=date_to)
    if search:
        transactions = transactions.filter(
            Q(description__icontains=search) |
            Q(reference__icontains=search)
        )
    
    transactions = transactions.order_by('-transaction_date')
    
    paginator = Paginator(transactions, 50)
    page = request.GET.get('page')
    transactions_page = paginator.get_page(page)
    
    total_credits = transactions.aggregate(
        total=Sum('amount', filter=Q(transaction_type='credit'))
    )['total'] or Decimal('0.00')
    
    total_debits = transactions.aggregate(
        total=Sum('amount', filter=Q(transaction_type='debit'))
    )['total'] or Decimal('0.00')
    
    context = {
        'company': company,
        'transactions': transactions_page,
        'total_credits': total_credits,
        'total_debits': total_debits,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'selected_type': transaction_type,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_transactions.html', context)


# ============================================
# PURCHASE RECORDS VIEW
# ============================================

@login_required
def purchase_records(request):
    """View all purchase records"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    branch_id = request.GET.get('branch')
    purchase_type = request.GET.get('purchase_type')
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search = request.GET.get('search')
    
    purchases = PurchaseRecord.objects.filter(company=company)
    
    if branch_id:
        purchases = purchases.filter(branch_id=branch_id)
    if purchase_type:
        purchases = purchases.filter(purchase_type=purchase_type)
    if status:
        purchases = purchases.filter(status=status)
    if date_from:
        purchases = purchases.filter(purchase_date__gte=date_from)
    if date_to:
        purchases = purchases.filter(purchase_date__lte=date_to)
    if search:
        purchases = purchases.filter(
            Q(supplier_name__icontains=search) |
            Q(purchase_number__icontains=search) |
            Q(description__icontains=search)
        )
    
    purchases = purchases.order_by('-purchase_date')
    
    paginator = Paginator(purchases, 50)
    page = request.GET.get('page')
    purchases_page = paginator.get_page(page)
    
    total_amount = purchases.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    current_balance = get_effective_cogs_balance(company, branch_id)
    
    context = {
        'company': company,
        'purchases': purchases_page,
        'total_amount': total_amount,
        'current_balance': current_balance,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'selected_type': purchase_type,
        'selected_status': status,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/purchase_records.html', context)


# ============================================
# CREATE PURCHASE VIEW
# ============================================

@login_required
def purchase_create(request):
    """Create a new purchase record"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    current_balance = get_effective_cogs_balance(company)
    
    if request.method == 'POST':
        branch_id = request.POST.get('branch')
        purchase_type = request.POST.get('purchase_type')
        amount = request.POST.get('amount')
        reference = request.POST.get('reference')
        description = request.POST.get('description')
        receipt_image = request.FILES.get('receipt_image')
        
        errors = []
        
        if not branch_id:
            errors.append("Branch is required")
        if not purchase_type:
            errors.append("Purchase type is required")
        if not amount:
            errors.append("Amount is required")
        if not reference:
            errors.append("Reference is required")
        if not description:
            errors.append("Description is required")
        
        if errors:
            messages.error(request, "\n".join(errors))
            return render(request, 'company/finance/purchase_create.html', {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True),
                'cogs_accounts': COGSAccount.objects.filter(company=company, is_active=True),
                'is_finance': True,
                'current_balance': current_balance,
                'purchase_types': PurchaseRecord.PURCHASE_TYPES,
                'payment_methods': PurchaseRecord.PAYMENT_METHODS,
                'today': timezone.now().date(),
                'is_viewing_company': is_viewing_company,
            })
        
        try:
            amount = Decimal(amount)
            
            if current_balance < amount:
                messages.error(
                    request,
                    f"Insufficient COGS balance. Available: {current_balance:,.2f}, Required: {amount:,.2f}"
                )
                return render(request, 'company/finance/purchase_create.html', {
                    'company': company,
                    'branches': Branch.objects.filter(company=company, is_active=True),
                    'cogs_accounts': COGSAccount.objects.filter(company=company, is_active=True),
                    'is_finance': True,
                    'current_balance': current_balance,
                    'purchase_types': PurchaseRecord.PURCHASE_TYPES,
                    'payment_methods': PurchaseRecord.PAYMENT_METHODS,
                    'today': timezone.now().date(),
                    'is_viewing_company': is_viewing_company,
                })
            
            with transaction.atomic():
                purchase = PurchaseRecord.objects.create(
                    company=company,
                    branch_id=branch_id,
                    cogs_account=None,
                    purchase_type=purchase_type,
                    purchase_date=timezone.now().date(),
                    amount=amount,
                    tax=Decimal('0.00'),
                    total_amount=amount,
                    supplier_name='Walk-in Supplier',
                    supplier_contact='',
                    supplier_phone='',
                    payment_method='cash',
                    payment_reference=reference,
                    description=description,
                    notes=f"Reference: {reference}",
                    status='completed',
                    created_by=request.user,
                    receipt_image=receipt_image,
                    receipt_number=reference,
                )
                
                messages.success(request, f"Purchase #{purchase.purchase_number} created successfully!")
                return redirect('finance-dashboard')
                
        except Exception as e:
            messages.error(request, f"Error creating purchase: {str(e)}")
    
    context = {
        'company': company,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'cogs_accounts': COGSAccount.objects.filter(company=company, is_active=True),
        'is_finance': True,
        'current_balance': current_balance,
        'purchase_types': PurchaseRecord.PURCHASE_TYPES,
        'payment_methods': PurchaseRecord.PAYMENT_METHODS,
        'today': timezone.now().date(),
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/purchase_create.html', context)


# ============================================
# PURCHASE DETAIL VIEW
# ============================================

@login_required
def purchase_detail(request, pk):
    """View purchase record details"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    purchase = get_object_or_404(PurchaseRecord, company=company, pk=pk)
    
    context = {
        'company': company,
        'purchase': purchase,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/purchase_detail.html', context)


# ============================================
# COGS ACCOUNT MANAGEMENT
# ============================================

@login_required
def cogs_accounts(request):
    """Manage COGS accounts"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    accounts = COGSAccount.objects.filter(company=company, is_active=True)
    
    context = {
        'company': company,
        'accounts': accounts,
        'is_finance': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_accounts.html', context)


@login_required
def cogs_account_create(request):
    """Create a new COGS account"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')
    
    if request.method == 'POST':
        branch_id = request.POST.get('branch')
        account_name = request.POST.get('account_name')
        account_code = request.POST.get('account_code')
        account_type = request.POST.get('account_type', 'main')
        description = request.POST.get('description', '')
        
        errors = []
        if not account_name:
            errors.append("Account name is required")
        if not account_code:
            errors.append("Account code is required")
        
        if errors:
            messages.error(request, "\n".join(errors))
            return render(request, 'company/finance/cogs_account_create.html', {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True),
                'is_finance': True,
                'is_viewing_company': is_viewing_company,
            })
        
        try:
            COGSAccount.objects.create(
                company=company,
                branch_id=branch_id if branch_id else None,
                account_name=account_name,
                account_code=account_code,
                account_type=account_type,
                description=description,
                is_active=True
            )
            messages.success(request, f"COGS Account '{account_name}' created successfully!")
            return redirect('finance-cogs-accounts')
        except Exception as e:
            messages.error(request, f"Error creating account: {str(e)}")
    
    context = {
        'company': company,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'is_finance': True,
        'account_types': COGSAccount.ACCOUNT_TYPES,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/finance/cogs_account_create.html', context)


# ============================================
# API/HELPER FUNCTIONS
# ============================================

def get_top_cogs_products(company, branch_id=None, limit=10):
    """Get top products generating COGS"""
    sales = Sale.objects.filter(company=company, payment_status='paid')
    if branch_id:
        sales = sales.filter(branch_id=branch_id)
    
    product_cogs = {}
    
    for sale in sales:
        sale_cogs = get_cogs_from_sale(sale)
        for item in sale.items.all():
            product_name = item.item_name
            item_share = item.total_price / sale.total_amount if sale.total_amount > 0 else 0
            cogs_for_item = sale_cogs * item_share
            
            if product_name in product_cogs:
                product_cogs[product_name]['amount'] += cogs_for_item
                product_cogs[product_name]['quantity'] += item.quantity
            else:
                product_cogs[product_name] = {
                    'amount': cogs_for_item,
                    'quantity': item.quantity,
                }
    
    sorted_products = sorted(
        product_cogs.items(),
        key=lambda x: x[1]['amount'],
        reverse=True
    )[:limit]
    
    return [
        {
            'name': name,
            'amount': float(data['amount']),
            'quantity': data['quantity']
        }
        for name, data in sorted_products
    ]


def get_cogs_monthly_trend(company, branch_id=None):
    """Get monthly COGS trend for the last 12 months"""
    today = timezone.now().date()
    trend = []
    
    for i in range(12):
        month = today.month - i
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        summary = get_cogs_summary(company, month_start, month_end, branch_id)
        
        trend.append({
            'month': month_start.strftime('%b %Y'),
            'credits': float(summary['total_credits']),
            'debits': float(summary['total_debits']),
            'net': float(summary['net_change']),
            'balance': float(summary['closing_balance']),
        })
    
    return list(reversed(trend))


def get_cogs_daily_trend(company, branch_id=None):
    """Get daily COGS trend for the last 30 days"""
    today = timezone.now().date()
    trend = []
    
    for i in range(30):
        day = today - timedelta(days=i)
        summary = get_cogs_summary(company, day, day, branch_id)
        
        trend.append({
            'date': day.strftime('%Y-%m-%d'),
            'credits': float(summary['total_credits']),
            'debits': float(summary['total_debits']),
            'net': float(summary['net_change']),
            'balance': float(summary['closing_balance']),
        })
    
    return list(reversed(trend))


@login_required
def finance_api_data(request):
    """API endpoint for finance charts"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    period = request.GET.get('period', 'monthly')
    branch_id = request.GET.get('branch')
    
    data = {}
    
    if period == 'daily':
        trend = get_cogs_daily_trend(company, branch_id)
        data = {
            'labels': [d['date'] for d in trend],
            'credits': [d['credits'] for d in trend],
            'debits': [d['debits'] for d in trend],
            'net': [d['net'] for d in trend],
            'balance': [d['balance'] for d in trend],
        }
    elif period == 'monthly':
        trend = get_cogs_monthly_trend(company, branch_id)
        data = {
            'labels': [d['month'] for d in trend],
            'credits': [d['credits'] for d in trend],
            'debits': [d['debits'] for d in trend],
            'net': [d['net'] for d in trend],
            'balance': [d['balance'] for d in trend],
        }
    
    return JsonResponse(data)


@login_required
def export_cogs_report(request):
    """Export COGS report as CSV"""
    import csv
    from django.http import HttpResponse
    
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return HttpResponse('No company assigned', status=400)
    
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    branch_id = request.GET.get('branch')
    
    if not date_from or not date_to:
        today = timezone.now().date()
        date_from = today.replace(day=1)
        date_to = today
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cogs_report_{date_from}_{date_to}.csv"'
    
    writer = csv.writer(response)
    
    writer.writerow(['COGS Report'])
    writer.writerow([f'Period: {date_from} to {date_to}'])
    writer.writerow([])
    
    summary = get_cogs_summary(company, date_from, date_to, branch_id)
    writer.writerow(['SUMMARY'])
    writer.writerow(['Opening Balance', float(summary['opening_balance'])])
    writer.writerow(['Total Credits (from sales)', float(summary['total_credits'])])
    writer.writerow(['Total Debits (from purchases)', float(summary['total_debits'])])
    writer.writerow(['Net Change', float(summary['net_change'])])
    writer.writerow(['Closing Balance', float(summary['closing_balance'])])
    writer.writerow([])
    
    transactions = COGSTransaction.objects.filter(
        company=company,
        transaction_date__date__gte=date_from,
        transaction_date__date__lte=date_to
    ).order_by('transaction_date')
    
    if branch_id:
        transactions = transactions.filter(branch_id=branch_id)
    
    writer.writerow(['TRANSACTIONS'])
    writer.writerow(['Date', 'Type', 'Description', 'Amount', 'Balance', 'Reference'])
    
    for transaction in transactions:
        writer.writerow([
            transaction.transaction_date.strftime('%Y-%m-%d %H:%M'),
            transaction.get_transaction_type_display(),
            transaction.description,
            float(transaction.amount),
            float(transaction.balance_after),
            transaction.reference or ''
        ])
    
    return response