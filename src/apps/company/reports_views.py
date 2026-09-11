from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
from django.http import JsonResponse
from django.core.paginator import Paginator

from apps.epa_shop.models import Sale, SaleItem, Electronic, Phone, Accessory, Branch, StockMovement
from apps.companies.models import Company
from apps.company.models import Expense
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)


# ============================================
# COST OF GOODS SOLD (COGS) HELPER FUNCTIONS
# ============================================

def get_sale_cogs(sale):
    """Calculate Cost of Goods Sold for a single sale"""
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


def get_cogs_for_queryset(sales_qs):
    """Calculate total COGS for a sales queryset"""
    total_cogs = Decimal('0.00')
    for sale in sales_qs:
        total_cogs += get_sale_cogs(sale)
    return total_cogs


# ============================================
# EXPENSE HELPER FUNCTIONS
# ============================================

def get_expenses_summary(expenses_qs):
    """Calculate summary for expenses queryset"""
    total_expenses = expenses_qs.count()
    total_amount = expenses_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    return {
        'total_expenses': total_expenses,
        'total_amount': total_amount,
    }


def get_expense_category_breakdown(expenses_qs):
    """Get expense breakdown by category"""
    breakdown = {}
    
    for category in Expense.EXPENSE_CATEGORIES:
        breakdown[category[0]] = {
            'label': category[1],
            'count': 0,
            'amount': Decimal('0.00'),
        }
    
    category_data = expenses_qs.values('category').annotate(
        count=Count('id'),
        total=Sum('amount')
    )
    
    for data in category_data:
        category = data['category']
        if category in breakdown:
            breakdown[category]['count'] = data['count'] or 0
            breakdown[category]['amount'] = data['total'] or Decimal('0.00')
    
    return breakdown


# ============================================
# SALES SUMMARY FUNCTIONS (WITH COGS)
# ============================================

def get_sales_summary(sales_qs):
    """Calculate summary statistics for a queryset with COGS"""
    total_sales = sales_qs.count()
    total_revenue = sales_qs.aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')
    total_cogs = get_cogs_for_queryset(sales_qs)
    gross_profit = total_revenue - total_cogs
    
    return {
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'total_profit': gross_profit,
        'total_purchase_cost': total_cogs,
    }


def get_profit_breakdown(sales_qs):
    """Get profit breakdown by product type with COGS"""
    breakdown = {
        'electronics': {'sales': 0, 'revenue': Decimal('0.00'), 'cogs': Decimal('0.00'), 'profit': Decimal('0.00')},
        'phones': {'sales': 0, 'revenue': Decimal('0.00'), 'cogs': Decimal('0.00'), 'profit': Decimal('0.00')},
        'accessories': {'sales': 0, 'revenue': Decimal('0.00'), 'cogs': Decimal('0.00'), 'profit': Decimal('0.00')},
    }
    
    for sale in sales_qs:
        for item in sale.items.all():
            product_type = 'other'
            if item.content_type:
                model_name = item.content_type.model
                if model_name == 'electronic':
                    product_type = 'electronics'
                elif model_name == 'phone':
                    product_type = 'phones'
                elif model_name == 'accessory':
                    product_type = 'accessories'
            
            if product_type in breakdown:
                item_cogs = Decimal('0.00')
                try:
                    product = item.content_type.get_object_for_this_type(id=item.object_id)
                    if hasattr(product, 'purchase_price') and product.purchase_price:
                        item_cogs = product.purchase_price * item.quantity
                    else:
                        item_cogs = item.total_price * Decimal('0.7')
                except:
                    item_cogs = item.total_price * Decimal('0.7')
                
                breakdown[product_type]['sales'] += item.quantity
                breakdown[product_type]['revenue'] += item.total_price
                breakdown[product_type]['cogs'] += item_cogs
                breakdown[product_type]['profit'] += item.total_price - item_cogs
    
    return breakdown


def get_top_products(sales_qs, limit=10):
    """Get top selling products with COGS"""
    products = {}
    
    for sale in sales_qs:
        for item in sale.items.all():
            product_name = item.item_name
            if product_name in products:
                products[product_name]['quantity'] += item.quantity
                products[product_name]['revenue'] += item.total_price
            else:
                products[product_name] = {
                    'quantity': item.quantity,
                    'revenue': item.total_price,
                }
    
    sorted_products = sorted(products.items(), key=lambda x: x[1]['quantity'], reverse=True)[:limit]
    
    return [{'name': name, 'quantity': data['quantity'], 'revenue': data['revenue']} 
            for name, data in sorted_products]


def get_sales_by_hour(sales_qs):
    """Get sales distribution by hour"""
    hourly_data = {}
    for hour in range(24):
        hourly_data[hour] = {'count': 0, 'revenue': Decimal('0.00')}
    
    for sale in sales_qs:
        hour = sale.sale_date.hour
        hourly_data[hour]['count'] += 1
        hourly_data[hour]['revenue'] += sale.net_amount
    
    return [{'hour': h, 'count': data['count'], 'revenue': float(data['revenue'])} 
            for h, data in hourly_data.items()]


# ============================================
# COMBINED SUMMARY FUNCTIONS (Sales + Expenses)
# ============================================

def combine_summaries(sales_summary, expenses_summary):
    """Combine sales and expense summaries with COGS"""
    gross_profit = sales_summary['total_revenue'] - sales_summary['total_cogs']
    net_profit = gross_profit - expenses_summary['total_amount']
    closing_balance = net_profit
    
    profit_margin = Decimal('0.00')
    if sales_summary['total_revenue'] > 0:
        profit_margin = (gross_profit / sales_summary['total_revenue']) * 100
    
    return {
        'total_sales': sales_summary['total_sales'],
        'total_revenue': sales_summary['total_revenue'],
        'total_cogs': sales_summary['total_cogs'],
        'gross_profit': gross_profit,
        'total_profit': gross_profit,
        'total_expenses': expenses_summary['total_amount'],
        'total_expense_count': expenses_summary['total_expenses'],
        'net_profit': net_profit,
        'closing_balance': closing_balance,
        'profit_margin': profit_margin,
    }


def get_combined_daily_records(sales_qs, expenses_qs, start_date, end_date):
    """Get combined daily records (sales + expenses) with COGS"""
    records = []
    current_date = start_date
    
    while current_date <= end_date:
        day_sales = sales_qs.filter(sale_date__date=current_date)
        day_expenses = expenses_qs.filter(expense_date=current_date)
        
        sales_summary = get_sales_summary(day_sales)
        expenses_summary = get_expenses_summary(day_expenses)
        combined = combine_summaries(sales_summary, expenses_summary)
        
        records.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'sales_count': combined['total_sales'],
            'revenue': combined['total_revenue'],
            'cogs': combined['total_cogs'],
            'gross_profit': combined['gross_profit'],
            'profit': combined['gross_profit'],
            'expenses': combined['total_expenses'],
            'net_profit': combined['net_profit'],
            'closing_balance': combined['closing_balance'],
            'profit_margin': combined['profit_margin'],
            'is_today': current_date == timezone.now().date(),
            'has_sales': combined['total_sales'] > 0,
        })
        current_date += timedelta(days=1)
    
    return records


def get_combined_weekly_records(sales_qs, expenses_qs, current_date):
    """Get combined weekly records with COGS"""
    records = []
    current_week = current_date.isocalendar()[1]
    current_year = current_date.year
    
    for i in range(52):
        week_num = current_week - i
        year = current_year
        
        if week_num <= 0:
            week_num += 52
            year -= 1
        
        try:
            week_start = datetime.strptime(f'{year}-W{week_num:02d}-1', '%Y-W%W-%w').date()
            week_end = week_start + timedelta(days=6)
            
            week_sales = sales_qs.filter(
                sale_date__date__gte=week_start,
                sale_date__date__lte=week_end
            )
            week_expenses = expenses_qs.filter(
                expense_date__gte=week_start,
                expense_date__lte=week_end
            )
            
            sales_summary = get_sales_summary(week_sales)
            expenses_summary = get_expenses_summary(week_expenses)
            combined = combine_summaries(sales_summary, expenses_summary)
            
            records.append({
                'year': year,
                'week': week_num,
                'week_start': week_start,
                'week_end': week_end,
                'sales_count': combined['total_sales'],
                'revenue': combined['total_revenue'],
                'cogs': combined['total_cogs'],
                'gross_profit': combined['gross_profit'],
                'profit': combined['gross_profit'],
                'expenses': combined['total_expenses'],
                'net_profit': combined['net_profit'],
                'closing_balance': combined['closing_balance'],
                'profit_margin': combined['profit_margin'],
            })
        except:
            continue
    
    return records


def get_combined_monthly_records(sales_qs, expenses_qs, year):
    """Get combined monthly records with COGS"""
    records = []
    
    for month in range(1, 13):
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        month_sales = sales_qs.filter(
            sale_date__date__gte=month_start,
            sale_date__date__lte=month_end
        )
        month_expenses = expenses_qs.filter(
            expense_date__gte=month_start,
            expense_date__lte=month_end
        )
        
        sales_summary = get_sales_summary(month_sales)
        expenses_summary = get_expenses_summary(month_expenses)
        combined = combine_summaries(sales_summary, expenses_summary)
        
        records.append({
            'month': month,
            'month_name': month_start.strftime('%B'),
            'month_start': month_start,
            'month_end': month_end,
            'sales_count': combined['total_sales'],
            'revenue': combined['total_revenue'],
            'cogs': combined['total_cogs'],
            'gross_profit': combined['gross_profit'],
            'profit': combined['gross_profit'],
            'expenses': combined['total_expenses'],
            'net_profit': combined['net_profit'],
            'closing_balance': combined['closing_balance'],
            'profit_margin': combined['profit_margin'],
        })
    
    return records


def get_combined_recent_daily_records(sales_qs, expenses_qs, days):
    """Get recent combined daily records with COGS"""
    today = timezone.now().date()
    start_date = today - timedelta(days=days)
    return get_combined_daily_records(sales_qs, expenses_qs, start_date, today)


def get_combined_daily_breakdown(sales_qs, expenses_qs, start_date, end_date):
    """Get combined daily breakdown for a date range with COGS"""
    breakdown = []
    current_date = start_date
    
    while current_date <= end_date:
        day_sales = sales_qs.filter(sale_date__date=current_date)
        day_expenses = expenses_qs.filter(expense_date=current_date)
        
        sales_summary = get_sales_summary(day_sales)
        expenses_summary = get_expenses_summary(day_expenses)
        combined = combine_summaries(sales_summary, expenses_summary)
        
        breakdown.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'sales_count': combined['total_sales'],
            'revenue': combined['total_revenue'],
            'cogs': combined['total_cogs'],
            'gross_profit': combined['gross_profit'],
            'profit': combined['gross_profit'],
            'expenses': combined['total_expenses'],
            'net_profit': combined['net_profit'],
            'closing_balance': combined['closing_balance'],
            'profit_margin': combined['profit_margin'],
        })
        current_date += timedelta(days=1)
    
    return breakdown


# ============================================
# CALCULATE TOTALS FOR TABLES
# ============================================

def calculate_daily_totals(daily_records):
    """Calculate totals for daily records"""
    totals = {
        'sales_count': 0,
        'revenue': Decimal('0.00'),
        'cogs': Decimal('0.00'),
        'gross_profit': Decimal('0.00'),
        'profit': Decimal('0.00'),
        'expenses': Decimal('0.00'),
        'net_profit': Decimal('0.00'),
        'closing_balance': Decimal('0.00'),
    }
    
    for record in daily_records:
        totals['sales_count'] += record.get('sales_count', 0)
        totals['revenue'] += record.get('revenue', Decimal('0.00'))
        totals['cogs'] += record.get('cogs', Decimal('0.00'))
        totals['gross_profit'] += record.get('gross_profit', Decimal('0.00'))
        totals['profit'] += record.get('profit', Decimal('0.00'))
        totals['expenses'] += record.get('expenses', Decimal('0.00'))
        totals['net_profit'] += record.get('net_profit', Decimal('0.00'))
        totals['closing_balance'] += record.get('closing_balance', Decimal('0.00'))
    
    return totals


def calculate_weekly_totals(weekly_records):
    """Calculate totals for weekly records"""
    totals = {
        'sales_count': 0,
        'revenue': Decimal('0.00'),
        'cogs': Decimal('0.00'),
        'gross_profit': Decimal('0.00'),
        'profit': Decimal('0.00'),
        'expenses': Decimal('0.00'),
        'net_profit': Decimal('0.00'),
        'closing_balance': Decimal('0.00'),
    }
    
    for record in weekly_records[:12]:
        totals['sales_count'] += record.get('sales_count', 0)
        totals['revenue'] += record.get('revenue', Decimal('0.00'))
        totals['cogs'] += record.get('cogs', Decimal('0.00'))
        totals['gross_profit'] += record.get('gross_profit', Decimal('0.00'))
        totals['profit'] += record.get('profit', Decimal('0.00'))
        totals['expenses'] += record.get('expenses', Decimal('0.00'))
        totals['net_profit'] += record.get('net_profit', Decimal('0.00'))
        totals['closing_balance'] += record.get('closing_balance', Decimal('0.00'))
    
    return totals


def calculate_monthly_totals(monthly_records):
    """Calculate totals for monthly records"""
    totals = {
        'sales_count': 0,
        'revenue': Decimal('0.00'),
        'cogs': Decimal('0.00'),
        'gross_profit': Decimal('0.00'),
        'profit': Decimal('0.00'),
        'expenses': Decimal('0.00'),
        'net_profit': Decimal('0.00'),
        'closing_balance': Decimal('0.00'),
    }
    
    for record in monthly_records:
        totals['sales_count'] += record.get('sales_count', 0)
        totals['revenue'] += record.get('revenue', Decimal('0.00'))
        totals['cogs'] += record.get('cogs', Decimal('0.00'))
        totals['gross_profit'] += record.get('gross_profit', Decimal('0.00'))
        totals['profit'] += record.get('profit', Decimal('0.00'))
        totals['expenses'] += record.get('expenses', Decimal('0.00'))
        totals['net_profit'] += record.get('net_profit', Decimal('0.00'))
        totals['closing_balance'] += record.get('closing_balance', Decimal('0.00'))
    
    return totals


# ============================================
# MAIN REPORTS DASHBOARD
# ============================================

@login_required
def reports_dashboard(request):
    """Main reports dashboard with daily, weekly, monthly views"""
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
    
    sales_qs = Sale.objects.filter(company=company, payment_status='paid')
    expenses_qs = Expense.objects.filter(company=company)
    
    if branch_id:
        sales_qs = sales_qs.filter(branch_id=branch_id)
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    if date_from:
        sales_qs = sales_qs.filter(sale_date__date__gte=date_from)
        expenses_qs = expenses_qs.filter(expense_date__gte=date_from)
    if date_to:
        sales_qs = sales_qs.filter(sale_date__date__lte=date_to)
        expenses_qs = expenses_qs.filter(expense_date__lte=date_to)
    
    branches = Branch.objects.filter(company=company, is_active=True)
    
    today = timezone.now().date()
    
    today_sales = sales_qs.filter(sale_date__date=today)
    today_sales_summary = get_sales_summary(today_sales)
    today_expenses = expenses_qs.filter(expense_date=today)
    today_expenses_summary = get_expenses_summary(today_expenses)
    today_summary = combine_summaries(today_sales_summary, today_expenses_summary)
    
    week_start = today - timedelta(days=today.weekday())
    week_sales = sales_qs.filter(sale_date__date__gte=week_start)
    week_sales_summary = get_sales_summary(week_sales)
    week_expenses = expenses_qs.filter(expense_date__gte=week_start)
    week_expenses_summary = get_expenses_summary(week_expenses)
    week_summary = combine_summaries(week_sales_summary, week_expenses_summary)
    
    month_start = today.replace(day=1)
    month_sales = sales_qs.filter(sale_date__date__gte=month_start)
    month_sales_summary = get_sales_summary(month_sales)
    month_expenses = expenses_qs.filter(expense_date__gte=month_start)
    month_expenses_summary = get_expenses_summary(month_expenses)
    month_summary = combine_summaries(month_sales_summary, month_expenses_summary)
    
    daily_records = get_combined_daily_records(sales_qs, expenses_qs, month_start, today)
    weekly_records = get_combined_weekly_records(sales_qs, expenses_qs, today)
    monthly_records = get_combined_monthly_records(sales_qs, expenses_qs, today.year)
    recent_days = get_combined_recent_daily_records(sales_qs, expenses_qs, 30)
    
    daily_totals = calculate_daily_totals(daily_records)
    weekly_totals = calculate_weekly_totals(weekly_records)
    monthly_totals = calculate_monthly_totals(monthly_records)
    
    context = {
        'company': company,
        'branches': branches,
        'today_summary': today_summary,
        'week_summary': week_summary,
        'month_summary': month_summary,
        'daily_records': daily_records,
        'weekly_records': weekly_records[:12],
        'monthly_records': monthly_records,
        'recent_days': recent_days,
        'daily_totals': daily_totals,
        'weekly_totals': weekly_totals,
        'monthly_totals': monthly_totals,
        'current_date': today,
        'today': today,
        'month_start': month_start,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'is_reports': True,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/reports/dashboard.html', context)


# ============================================
# DAILY DETAIL REPORT
# ============================================

@login_required
def reports_daily_detail(request, date_str):
    """View detailed daily report for a specific date"""
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
    
    epa_sales_qs = Sale.objects.filter(
        company=company, 
        payment_status='paid',
        sale_date__date=report_date
    )
    
    expenses_qs = Expense.objects.filter(
        company=company,
        expense_date=report_date
    )
    
    if branch_id:
        epa_sales_qs = epa_sales_qs.filter(branch_id=branch_id)
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    epa_sales = epa_sales_qs.order_by('-sale_date')
    epa_summary = get_sales_summary(epa_sales_qs)
    
    expenses = expenses_qs.order_by('-created_at')
    expenses_summary = get_expenses_summary(expenses_qs)
    
    supermarket_sales = []
    supermarket_summary = {
        'total_sales': 0,
        'total_revenue': Decimal('0.00'),
        'total_profit': Decimal('0.00'),
        'total_expenses': Decimal('0.00'),
        'closing_balance': Decimal('0.00'),
        'total_cogs': Decimal('0.00'),
    }
    
    combined_summary = combine_summaries(epa_summary, expenses_summary)
    profit_breakdown = get_profit_breakdown(epa_sales_qs)
    top_products = get_top_products(epa_sales_qs)
    sales_by_hour = get_sales_by_hour(epa_sales_qs)
    expense_breakdown = get_expense_category_breakdown(expenses_qs)
    
    context = {
        'company': company,
        'report_date': report_date,
        'daily_sales': epa_sales,
        'summary': epa_summary,
        'expenses': expenses,
        'expenses_summary': expenses_summary,
        'expense_breakdown': expense_breakdown,
        'profit_breakdown': profit_breakdown,
        'top_products': top_products,
        'sales_by_hour': sales_by_hour,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'is_reports': True,
        'is_viewing_company': is_viewing_company,
        'combined_summary': combined_summary,
        'epa_sales': epa_sales,
        'epa_summary': epa_summary,
        'supermarket_sales': supermarket_sales,
        'supermarket_summary': supermarket_summary,
    }
    return render(request, 'company/reports/daily_detail.html', context)


# ============================================
# WEEKLY DETAIL REPORT
# ============================================

@login_required
def reports_weekly_detail(request, year, week):
    """View detailed weekly report with COGS"""
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
    
    week_start = datetime.strptime(f'{year}-W{week:02d}-1', '%Y-W%W-%w').date()
    week_end = week_start + timedelta(days=6)
    
    sales_qs = Sale.objects.filter(
        company=company,
        payment_status='paid',
        sale_date__date__gte=week_start,
        sale_date__date__lte=week_end
    )
    
    expenses_qs = Expense.objects.filter(
        company=company,
        expense_date__gte=week_start,
        expense_date__lte=week_end
    )
    
    if branch_id:
        sales_qs = sales_qs.filter(branch_id=branch_id)
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    sales_summary = get_sales_summary(sales_qs)
    expenses_summary = get_expenses_summary(expenses_qs)
    combined_summary = combine_summaries(sales_summary, expenses_summary)
    
    daily_breakdown = get_combined_daily_breakdown(sales_qs, expenses_qs, week_start, week_end)
    top_products = get_top_products(sales_qs)
    expense_breakdown = get_expense_category_breakdown(expenses_qs)
    profit_breakdown = get_profit_breakdown(sales_qs)
    
    today = timezone.now().date()
    
    context = {
        'company': company,
        'week_start': week_start,
        'week_end': week_end,
        'year': year,
        'week': week,
        'summary': combined_summary,
        'combined_summary': combined_summary,
        'daily_breakdown': daily_breakdown,
        'top_products': top_products,
        'expense_breakdown': expense_breakdown,
        'profit_breakdown': profit_breakdown,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'is_reports': True,
        'is_viewing_company': is_viewing_company,
        'today': today,
    }
    return render(request, 'company/reports/weekly_detail.html', context)


# ============================================
# MONTHLY DETAIL REPORT
# ============================================

@login_required
def reports_monthly_detail(request, year, month):
    """View detailed monthly report with COGS"""
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
    
    sales_qs = Sale.objects.filter(
        company=company,
        payment_status='paid',
        sale_date__date__gte=month_start,
        sale_date__date__lte=month_end
    )
    
    expenses_qs = Expense.objects.filter(
        company=company,
        expense_date__gte=month_start,
        expense_date__lte=month_end
    )
    
    if branch_id:
        sales_qs = sales_qs.filter(branch_id=branch_id)
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    sales_summary = get_sales_summary(sales_qs)
    expenses_summary = get_expenses_summary(expenses_qs)
    combined_summary = combine_summaries(sales_summary, expenses_summary)
    
    daily_breakdown = get_combined_daily_breakdown(sales_qs, expenses_qs, month_start, month_end)
    profit_breakdown = get_profit_breakdown(sales_qs)
    top_products = get_top_products(sales_qs)
    expense_breakdown = get_expense_category_breakdown(expenses_qs)
    sales_by_hour = get_sales_by_hour(sales_qs)
    
    today = timezone.now().date()
    
    context = {
        'company': company,
        'month_start': month_start,
        'month_end': month_end,
        'year': year,
        'month': month,
        'month_name': month_start.strftime('%B'),
        'summary': combined_summary,
        'combined_summary': combined_summary,
        'daily_breakdown': daily_breakdown,
        'profit_breakdown': profit_breakdown,
        'top_products': top_products,
        'expense_breakdown': expense_breakdown,
        'sales_by_hour': sales_by_hour,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'is_reports': True,
        'is_viewing_company': is_viewing_company,
        'today': today,
    }
    return render(request, 'company/reports/monthly_detail.html', context)


# ============================================
# EXPORT REPORTS (CSV)
# ============================================

@login_required
def reports_export_csv(request, report_type, date_str=None, year=None, week=None, month=None):
    """Export report data as CSV with COGS"""
    import csv
    from django.http import HttpResponse
    
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{timezone.now().date()}.csv"'
    
    writer = csv.writer(response)
    
    if report_type == 'daily':
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        sales = Sale.objects.filter(
            company=company,
            payment_status='paid',
            sale_date__date=report_date
        ).order_by('-sale_date')
        
        expenses = Expense.objects.filter(
            company=company,
            expense_date=report_date
        ).order_by('-created_at')
        
        writer.writerow(['=== SALES WITH COGS ==='])
        writer.writerow(['Sale ID', 'Customer', 'Amount', 'COGS', 'Profit', 'Payment Method', 'Date', 'Items'])
        for sale in sales:
            items = ', '.join([f"{item.quantity}x {item.item_name}" for item in sale.items.all()])
            cogs = get_sale_cogs(sale)
            profit = sale.net_amount - cogs
            writer.writerow([
                sale.id,
                sale.customer_name,
                float(sale.net_amount),
                float(cogs),
                float(profit),
                sale.payment_method,
                sale.sale_date.strftime('%Y-%m-%d %H:%M'),
                items
            ])
        
        writer.writerow([])
        writer.writerow(['=== EXPENSES ==='])
        writer.writerow(['ID', 'Category', 'Description', 'Amount', 'Payment Method', 'Reference'])
        for expense in expenses:
            writer.writerow([
                expense.id,
                expense.category_display,
                expense.description,
                float(expense.amount),
                expense.payment_method_display,
                expense.reference or '-'
            ])
        
        writer.writerow([])
        writer.writerow(['=== SUMMARY ==='])
        sales_summary = get_sales_summary(sales)
        expenses_summary = get_expenses_summary(expenses)
        combined = combine_summaries(sales_summary, expenses_summary)
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Revenue', float(combined['total_revenue'])])
        writer.writerow(['Total COGS', float(combined['total_cogs'])])
        writer.writerow(['Gross Profit', float(combined['gross_profit'])])
        writer.writerow(['Total Expenses', float(combined['total_expenses'])])
        writer.writerow(['Net Profit', float(combined['net_profit'])])
        writer.writerow(['Profit Margin %', float(combined['profit_margin'])])
    
    elif report_type == 'weekly':
        week_start = datetime.strptime(f'{year}-W{week:02d}-1', '%Y-W%W-%w').date()
        week_end = week_start + timedelta(days=6)
        sales = Sale.objects.filter(
            company=company,
            payment_status='paid',
            sale_date__date__gte=week_start,
            sale_date__date__lte=week_end
        ).order_by('sale_date')
        
        expenses = Expense.objects.filter(
            company=company,
            expense_date__gte=week_start,
            expense_date__lte=week_end
        ).order_by('expense_date')
        
        writer.writerow(['Date', 'Day', 'Sales Count', 'Revenue', 'COGS', 'Gross Profit', 'Expenses', 'Net Profit', 'Margin %'])
        daily_breakdown = get_combined_daily_breakdown(sales, expenses, week_start, week_end)
        for day in daily_breakdown:
            writer.writerow([
                day['date'].strftime('%Y-%m-%d'),
                day['day_name'],
                day['sales_count'],
                float(day['revenue']),
                float(day['cogs']),
                float(day['gross_profit']),
                float(day['expenses']),
                float(day['net_profit']),
                float(day['profit_margin']),
            ])
    
    elif report_type == 'monthly':
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        sales = Sale.objects.filter(
            company=company,
            payment_status='paid',
            sale_date__date__gte=month_start,
            sale_date__date__lte=month_end
        ).order_by('sale_date')
        
        expenses = Expense.objects.filter(
            company=company,
            expense_date__gte=month_start,
            expense_date__lte=month_end
        ).order_by('expense_date')
        
        writer.writerow(['Date', 'Day', 'Sales Count', 'Revenue', 'COGS', 'Gross Profit', 'Expenses', 'Net Profit', 'Margin %'])
        daily_breakdown = get_combined_daily_breakdown(sales, expenses, month_start, month_end)
        for day in daily_breakdown:
            writer.writerow([
                day['date'].strftime('%Y-%m-%d'),
                day['day_name'],
                day['sales_count'],
                float(day['revenue']),
                float(day['cogs']),
                float(day['gross_profit']),
                float(day['expenses']),
                float(day['net_profit']),
                float(day['profit_margin']),
            ])
    
    return response


# ============================================
# API ENDPOINTS FOR REPORTS (AJAX)
# ============================================

@login_required
def reports_api_data(request):
    """API endpoint for reports data (for charts) with COGS"""
    # ============================================
    # SUPPORT MODE: Get active company
    # ============================================
    company, is_viewing_company = get_active_company(request)
    
    if not company:
        return JsonResponse({'error': 'No company assigned'}, status=400)
    
    period = request.GET.get('period', 'monthly')
    branch_id = request.GET.get('branch')
    
    sales_qs = Sale.objects.filter(company=company, payment_status='paid')
    expenses_qs = Expense.objects.filter(company=company)
    
    if branch_id:
        sales_qs = sales_qs.filter(branch_id=branch_id)
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    data = {}
    
    if period == 'daily':
        start_date = timezone.now().date() - timedelta(days=30)
        daily_data = get_combined_daily_records(sales_qs, expenses_qs, start_date, timezone.now().date())
        data = {
            'labels': [d['date'].strftime('%b %d') for d in daily_data],
            'revenue': [float(d['revenue']) for d in daily_data],
            'cogs': [float(d['cogs']) for d in daily_data],
            'gross_profit': [float(d['gross_profit']) for d in daily_data],
            'profit': [float(d['profit']) for d in daily_data],
            'expenses': [float(d['expenses']) for d in daily_data],
            'net_profit': [float(d['net_profit']) for d in daily_data],
            'sales': [d['sales_count'] for d in daily_data],
            'margin': [float(d['profit_margin']) for d in daily_data],
        }
    elif period == 'weekly':
        weekly_data = get_combined_weekly_records(sales_qs, expenses_qs, timezone.now().date())
        data = {
            'labels': [f"Week {d['week']}" for d in weekly_data[:12]],
            'revenue': [float(d['revenue']) for d in weekly_data[:12]],
            'cogs': [float(d['cogs']) for d in weekly_data[:12]],
            'gross_profit': [float(d['gross_profit']) for d in weekly_data[:12]],
            'profit': [float(d['profit']) for d in weekly_data[:12]],
            'expenses': [float(d['expenses']) for d in weekly_data[:12]],
            'net_profit': [float(d['net_profit']) for d in weekly_data[:12]],
            'sales': [d['sales_count'] for d in weekly_data[:12]],
            'margin': [float(d['profit_margin']) for d in weekly_data[:12]],
        }
    elif period == 'monthly':
        monthly_data = get_combined_monthly_records(sales_qs, expenses_qs, timezone.now().year)
        data = {
            'labels': [d['month_name'] for d in monthly_data],
            'revenue': [float(d['revenue']) for d in monthly_data],
            'cogs': [float(d['cogs']) for d in monthly_data],
            'gross_profit': [float(d['gross_profit']) for d in monthly_data],
            'profit': [float(d['profit']) for d in monthly_data],
            'expenses': [float(d['expenses']) for d in monthly_data],
            'net_profit': [float(d['net_profit']) for d in monthly_data],
            'sales': [d['sales_count'] for d in monthly_data],
            'margin': [float(d['profit_margin']) for d in monthly_data],
        }
    
    return JsonResponse(data)