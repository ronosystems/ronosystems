from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, Value, CharField
from django.db.models.functions import Concat
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods

from apps.companies.models import Company
from apps.epa_shop.models import Branch
from .models import Expense

# ============================================
# EXPENSE CATEGORIES (From Model)
# ============================================

EXPENSE_CATEGORIES = Expense.EXPENSE_CATEGORIES

# ============================================
# EXPENSE DASHBOARD
# ============================================

@login_required
def expenses_dashboard(request):
    """Main expenses dashboard with daily, weekly, monthly views"""
    company = request.user.company
    branch_id = request.GET.get('branch')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Base queryset
    expenses_qs = Expense.objects.filter(company=company)
    
    if branch_id:
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    if date_from:
        expenses_qs = expenses_qs.filter(expense_date__gte=date_from)
    if date_to:
        expenses_qs = expenses_qs.filter(expense_date__lte=date_to)
    
    # Get branches for filter
    branches = Branch.objects.filter(company=company, is_active=True)
    
    # Today's summary
    today = timezone.now().date()
    today_expenses = expenses_qs.filter(expense_date=today)
    today_summary = get_expenses_summary(today_expenses)
    
    # This week summary
    week_start = today - timedelta(days=today.weekday())
    week_expenses = expenses_qs.filter(expense_date__gte=week_start)
    week_summary = get_expenses_summary(week_expenses)
    
    # This month summary
    month_start = today.replace(day=1)
    month_expenses = expenses_qs.filter(expense_date__gte=month_start)
    month_summary = get_expenses_summary(month_expenses)
    
    # Daily records for the current month with submitter information
    daily_records = get_daily_expense_records_with_submitters(expenses_qs, month_start, today)
    
    # Weekly records
    weekly_records = get_weekly_expense_records(expenses_qs, today)
    
    # Monthly records
    monthly_records = get_monthly_expense_records(expenses_qs, today.year)
    
    # Expense categories breakdown
    category_breakdown = get_category_breakdown(expenses_qs)
    
    context = {
        'branches': branches,
        'today_summary': today_summary,
        'week_summary': week_summary,
        'month_summary': month_summary,
        'daily_records': daily_records,
        'weekly_records': weekly_records[:12],
        'monthly_records': monthly_records,
        'category_breakdown': category_breakdown,
        'current_date': today,
        'today': today,
        'month_start': month_start,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'expense_categories': EXPENSE_CATEGORIES,
        'is_expenses': True,
    }
    return render(request, 'company/expenses/dashboard.html', context)

# ============================================
# EXPENSE CRUD OPERATIONS
# ============================================

@login_required
def expense_create(request):
    """Create a new expense record"""
    company = request.user.company
    branches = Branch.objects.filter(company=company, is_active=True)
    
    if request.method == 'POST':
        try:
            # Get form data
            expense_date = request.POST.get('expense_date')
            category = request.POST.get('category')
            description = request.POST.get('description', '').strip()
            amount = Decimal(request.POST.get('amount', '0'))
            branch_id = request.POST.get('branch')
            payment_method = request.POST.get('payment_method', 'cash')
            reference = request.POST.get('reference', '').strip()
            notes = request.POST.get('notes', '').strip()
            
            # Validate
            if not expense_date:
                messages.error(request, 'Please select a date.')
                return redirect('company-expenses-create')
            
            if not category:
                messages.error(request, 'Please select a category.')
                return redirect('company-expenses-create')
            
            if not description:
                messages.error(request, 'Please enter a description.')
                return redirect('company-expenses-create')
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than 0.')
                return redirect('company-expenses-create')
            
            # Get branch
            branch = None
            if branch_id:
                branch = Branch.objects.get(id=branch_id, company=company)
            
            # Create expense
            expense = Expense.objects.create(
                company=company,
                branch=branch,
                expense_date=datetime.strptime(expense_date, '%Y-%m-%d').date(),
                category=category,
                description=description,
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                notes=notes,
                created_by=request.user,
                status=Expense.STATUS_PENDING
            )
            
            messages.success(request, f'✅ Expense "{expense.description}" recorded successfully!')
            return redirect('company-expenses-dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error saving expense: {str(e)}')
            return redirect('company-expenses-create')
    
    context = {
        'branches': branches,
        'expense_categories': EXPENSE_CATEGORIES,
        'today': timezone.now().date(),
        'is_expenses': True,
    }
    return render(request, 'company/expenses/form.html', context)

@login_required
def expense_edit(request, pk):
    """Edit an existing expense record"""
    company = request.user.company
    expense = get_object_or_404(Expense, id=pk, company=company)
    branches = Branch.objects.filter(company=company, is_active=True)
    
    if request.method == 'POST':
        try:
            # Update expense
            expense.expense_date = datetime.strptime(request.POST.get('expense_date'), '%Y-%m-%d').date()
            expense.category = request.POST.get('category')
            expense.description = request.POST.get('description', '').strip()
            expense.amount = Decimal(request.POST.get('amount', '0'))
            expense.payment_method = request.POST.get('payment_method', 'cash')
            expense.reference = request.POST.get('reference', '').strip()
            expense.notes = request.POST.get('notes', '').strip()
            
            branch_id = request.POST.get('branch')
            if branch_id:
                expense.branch = Branch.objects.get(id=branch_id, company=company)
            else:
                expense.branch = None
            
            expense.save()
            
            messages.success(request, f'✅ Expense "{expense.description}" updated successfully!')
            return redirect('company-expenses-dashboard')
            
        except Exception as e:
            messages.error(request, f'❌ Error updating expense: {str(e)}')
    
    context = {
        'expense': expense,
        'branches': branches,
        'expense_categories': EXPENSE_CATEGORIES,
        'is_expenses': True,
        'is_edit': True,
    }
    return render(request, 'company/expenses/form.html', context)

@login_required
def expense_delete(request, pk):
    """Delete an expense record"""
    company = request.user.company
    expense = get_object_or_404(Expense, id=pk, company=company)
    
    if request.method == 'POST':
        try:
            description = expense.description
            expense.delete()
            messages.success(request, f'✅ Expense "{description}" deleted successfully!')
        except Exception as e:
            messages.error(request, f'❌ Error deleting expense: {str(e)}')
        return redirect('company-expenses-dashboard')
    
    context = {
        'expense': expense,
        'is_expenses': True,
    }
    return render(request, 'company/expenses_confirm_delete.html', context)

@login_required
def expense_detail(request, pk):
    """View expense details"""
    company = request.user.company
    expense = get_object_or_404(Expense, id=pk, company=company)
    
    context = {
        'expense': expense,
        'is_expenses': True,
    }
    return render(request, 'company/expenses/detail.html', context)

# ============================================
# EXPENSE DETAIL REPORTS
# ============================================

@login_required
def expenses_daily_detail(request, date_str):
    """View detailed daily expenses"""
    company = request.user.company
    report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    branch_id = request.GET.get('branch')
    
    expenses_qs = Expense.objects.filter(company=company, expense_date=report_date)
    
    if branch_id:
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    
    expenses = expenses_qs.order_by('-created_at')
    summary = get_expenses_summary(expenses_qs)
    category_breakdown = get_category_breakdown(expenses_qs)
    
    context = {
        'report_date': report_date,
        'expenses': expenses,
        'summary': summary,
        'category_breakdown': category_breakdown,
        'branches': Branch.objects.filter(company=company, is_active=True),
        'selected_branch': branch_id,
        'expense_categories': EXPENSE_CATEGORIES,
        'is_expenses': True,
    }
    return render(request, 'company/expenses/daily_detail.html', context)

# ============================================
# EXPENSE APPROVAL (Optional)
# ============================================

@login_required
def expense_approve(request, pk):
    """Approve an expense (for managers/admins)"""
    company = request.user.company
    expense = get_object_or_404(Expense, id=pk, company=company)
    
    if request.method == 'POST':
        try:
            expense.approve(request.user)
            messages.success(request, f'✅ Expense "{expense.description}" approved!')
        except Exception as e:
            messages.error(request, f'❌ Error approving expense: {str(e)}')
        return redirect('company-expenses-dashboard')
    
    context = {
        'expense': expense,
        'is_expenses': True,
    }
    return render(request, 'company/expenses/approve.html', context)

@login_required
def expense_reject(request, pk):
    """Reject an expense"""
    company = request.user.company
    expense = get_object_or_404(Expense, id=pk, company=company)
    
    if request.method == 'POST':
        try:
            expense.reject()
            messages.success(request, f'✅ Expense "{expense.description}" rejected!')
        except Exception as e:
            messages.error(request, f'❌ Error rejecting expense: {str(e)}')
        return redirect('company-expenses-dashboard')
    
    context = {
        'expense': expense,
        'is_expenses': True,
    }
    return render(request, 'company/expenses/reject.html', context)

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_expenses_summary(expenses_qs):
    """Calculate summary for expenses queryset"""
    total_expenses = expenses_qs.count()
    total_amount = expenses_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    return {
        'total_expenses': total_expenses,
        'total_amount': total_amount,
    }

def get_daily_expense_records(expenses_qs, start_date, end_date):
    """Get daily expense records (original version without submitters)"""
    records = []
    current_date = start_date
    
    while current_date <= end_date:
        day_expenses = expenses_qs.filter(expense_date=current_date)
        summary = get_expenses_summary(day_expenses)
        
        records.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'expense_count': summary['total_expenses'],
            'total_amount': summary['total_amount'],
            'is_today': current_date == timezone.now().date(),
        })
        current_date += timedelta(days=1)
    
    return records

def get_daily_expense_records_with_submitters(expenses_qs, start_date, end_date):
    """
    Get daily expense records with submitter information.
    Shows all users who submitted expenses on each day.
    """
    records = []
    current_date = start_date
    
    while current_date <= end_date:
        day_expenses = expenses_qs.filter(expense_date=current_date)
        summary = get_expenses_summary(day_expenses)
        
        # Get all users who submitted expenses on this day
        submitters_qs = day_expenses.values(
            'created_by__id',
            'created_by__username',
            'created_by__first_name',
            'created_by__last_name'
        ).distinct()
        
        submitter_names = []
        submitter_usernames = []
        submitter_ids = []
        
        for submitter in submitters_qs:
            first_name = submitter.get('created_by__first_name', '')
            last_name = submitter.get('created_by__last_name', '')
            username = submitter.get('created_by__username', '')
            user_id = submitter.get('created_by__id')
            
            if first_name or last_name:
                full_name = f"{first_name} {last_name}".strip()
                submitter_names.append(full_name)
            else:
                submitter_names.append(username)
            
            submitter_usernames.append(username)
            submitter_ids.append(user_id)
        
        # Build display string
        if submitter_names:
            if len(submitter_names) == 1:
                submitted_by_display = submitter_names[0]
                submitter_count = 1
            else:
                submitted_by_display = f"{submitter_names[0]} +{len(submitter_names)-1} more"
                submitter_count = len(submitter_names)
        else:
            submitted_by_display = 'N/A'
            submitter_count = 0
        
        records.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'expense_count': summary['total_expenses'],
            'total_amount': summary['total_amount'],
            'is_today': current_date == timezone.now().date(),
            # Submitter fields
            'submitted_by': submitted_by_display,
            'submitted_by_full': ', '.join(submitter_names) if submitter_names else 'N/A',
            'submitted_by_usernames': submitter_usernames,
            'submitted_by_ids': submitter_ids,
            'submitter_count': submitter_count,
            'submitters': submitters_qs,  # Full queryset for detailed display
        })
        current_date += timedelta(days=1)
    
    return records

def get_weekly_expense_records(expenses_qs, current_date):
    """Get weekly expense records"""
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
            
            week_expenses = expenses_qs.filter(
                expense_date__gte=week_start,
                expense_date__lte=week_end
            )
            summary = get_expenses_summary(week_expenses)
            
            records.append({
                'year': year,
                'week': week_num,
                'week_start': week_start,
                'week_end': week_end,
                'expense_count': summary['total_expenses'],
                'total_amount': summary['total_amount'],
            })
        except:
            continue
    
    return records

def get_monthly_expense_records(expenses_qs, year):
    """Get monthly expense records"""
    records = []
    
    for month in range(1, 13):
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)
        
        month_expenses = expenses_qs.filter(
            expense_date__gte=month_start,
            expense_date__lte=month_end
        )
        summary = get_expenses_summary(month_expenses)
        
        records.append({
            'month': month,
            'month_name': month_start.strftime('%B'),
            'month_start': month_start,
            'month_end': month_end,
            'expense_count': summary['total_expenses'],
            'total_amount': summary['total_amount'],
        })
    
    return records

def get_category_breakdown(expenses_qs):
    """Get expense breakdown by category"""
    breakdown = {}
    
    # Initialize all categories
    for category in EXPENSE_CATEGORIES:
        breakdown[category[0]] = {
            'label': category[1],
            'count': 0,
            'amount': Decimal('0.00'),
        }
    
    # Aggregate by category
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