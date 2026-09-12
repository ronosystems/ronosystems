from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.core.paginator import Paginator

from apps.companies.models import Company
from apps.epa_shop.models import Branch
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)
from .models import Expense

# ============================================
# CONSTANTS
# ============================================
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf')


# ============================================
# HELPERS
# ============================================
def get_user_branch(user):
    if hasattr(user, 'branch') and user.branch:
        return user.branch
    return None


def validate_attachment(file):
    if not file:
        return None
    if file.size > MAX_ATTACHMENT_SIZE:
        return f'Attachment is too large (max {MAX_ATTACHMENT_SIZE // (1024 * 1024)} MB).'
    name = file.name.lower()
    if not name.endswith(ALLOWED_ATTACHMENT_EXTENSIONS):
        allowed = ', '.join(ALLOWED_ATTACHMENT_EXTENSIONS)
        return f'Invalid file type. Allowed: {allowed}'
    return None


def get_expenses_summary(expenses_qs):
    total_expenses = expenses_qs.count()
    total_amount = expenses_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return {'total_expenses': total_expenses, 'total_amount': total_amount}


def _base_context(request, expense_type):
    """Common context for all expense category pages."""
    company, is_viewing_company = get_active_company(request)
    if not company:
        return None, None, None, None

    user_branch = get_user_branch(request.user)
    is_admin = is_viewing_company or request.user.role in ['super_admin', 'company_admin']

    qs = Expense.objects.filter(company=company, expense_type=expense_type)

    if not is_admin and not is_viewing_company and user_branch:
        qs = qs.filter(branch=user_branch)
    elif not is_admin and not is_viewing_company and not user_branch:
        qs = qs.none()

    branches = Branch.objects.filter(company=company, is_active=True)
    if not is_admin and not is_viewing_company and user_branch:
        branches = branches.filter(id=user_branch.id)

    context = {
        'company': company,
        'is_viewing_company': is_viewing_company,
        'is_admin': is_admin,
        'user_branch': user_branch,
        'branches': branches,
        'is_expenses': True,
        'expense_type': expense_type,
    }
    return company, is_admin, user_branch, context


# ============================================
# MAIN EXPENSES HUB
# ============================================
@login_required
def expenses_dashboard(request):
    """
    Main expenses dashboard — shows:
    - 4 category summary cards (Salaries, Rents, Bills, General)
    - Daily records table (all expenses combined)
    - Category breakdown
    - Today/Week/Month totals
    """
    company, is_viewing_company = get_active_company(request)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    user_branch = get_user_branch(request.user)
    is_admin = is_viewing_company or request.user.role in ['super_admin', 'company_admin']

    # Base queryset — ALL expense types
    expenses_qs = Expense.objects.filter(company=company)
    if not is_admin and not is_viewing_company and user_branch:
        expenses_qs = expenses_qs.filter(branch=user_branch)

    # Apply filters
    branch_id = request.GET.get('branch')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    expense_type_filter = request.GET.get('type')  # Optional type filter

    if branch_id:
        expenses_qs = expenses_qs.filter(branch_id=branch_id)
    if date_from:
        expenses_qs = expenses_qs.filter(expense_date__gte=date_from)
    if date_to:
        expenses_qs = expenses_qs.filter(expense_date__lte=date_to)
    if expense_type_filter:
        expenses_qs = expenses_qs.filter(expense_type=expense_type_filter)

    branches = Branch.objects.filter(company=company, is_active=True)
    if not is_admin and not is_viewing_company and user_branch:
        branches = branches.filter(id=user_branch.id)

    today = timezone.now().date()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    # ============================================
    # PER-TYPE SUMMARIES (this month) — for the 4 cards
    # ============================================
    def type_summary(etype):
        qs = expenses_qs.filter(expense_type=etype, expense_date__gte=month_start)
        s = get_expenses_summary(qs)
        return {
            'count': s['total_expenses'],
            'total': s['total_amount'],
            'pending': qs.filter(status=Expense.STATUS_PENDING).count(),
        }

    # ============================================
    # TIME-BASED SUMMARIES (all types combined)
    # ============================================
    today_summary = get_expenses_summary(expenses_qs.filter(expense_date=today))
    week_summary = get_expenses_summary(expenses_qs.filter(expense_date__gte=week_start))
    month_summary = get_expenses_summary(expenses_qs.filter(expense_date__gte=month_start))

    # ============================================
    # DAILY RECORDS TABLE (all types combined)
    # ============================================
    daily_records = get_daily_expense_records_with_submitters(expenses_qs, month_start, today)

    # ============================================
    # CATEGORY BREAKDOWN (general only — salaries/rents/bills have their own pages)
    # ============================================
    category_breakdown = get_category_breakdown(
        expenses_qs.filter(expense_type=Expense.TYPE_GENERAL)
    )

    context = {
        'company': company,
        'branches': branches,
        'today_summary': today_summary,
        'week_summary': week_summary,
        'month_summary': month_summary,
        'daily_records': daily_records,
        'category_breakdown': category_breakdown,
        'current_date': today,
        'today': today,
        'month_start': month_start,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'selected_type': expense_type_filter,
        'expense_types': Expense.EXPENSE_TYPES,
        'expense_categories': Expense.GENERAL_CATEGORIES,
        'is_expenses': True,
        'is_admin': is_admin,
        'user_branch': user_branch,
        'is_viewing_company': is_viewing_company,
        # 4 category card summaries
        'salary_summary': type_summary(Expense.TYPE_SALARY),
        'rent_summary': type_summary(Expense.TYPE_RENT),
        'bill_summary': type_summary(Expense.TYPE_BILL),
        'general_summary': type_summary(Expense.TYPE_GENERAL),
    }
    return render(request, 'company/expenses/dashboard.html', context)




@login_required
def expenses_daily_detail(request, date_str):
    """View detailed expenses for a specific day."""
    company, is_viewing_company = get_active_company(request)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    try:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Invalid date format.')
        return redirect('company-expenses-dashboard')

    user_branch = get_user_branch(request.user)
    is_admin = is_viewing_company or request.user.role in ['super_admin', 'company_admin']

    # Base queryset — all expense types for that day
    expenses_qs = Expense.objects.filter(company=company, expense_date=report_date)

    if not is_admin and not is_viewing_company and user_branch:
        expenses_qs = expenses_qs.filter(branch=user_branch)

    # Optional branch filter via GET
    branch_id = request.GET.get('branch')
    if branch_id:
        expenses_qs = expenses_qs.filter(branch_id=branch_id)

    # Optional type filter via GET
    expense_type = request.GET.get('type')
    if expense_type:
        expenses_qs = expenses_qs.filter(expense_type=expense_type)

    expenses = expenses_qs.order_by('-created_at')
    summary = get_expenses_summary(expenses_qs)
    category_breakdown = get_category_breakdown(
        expenses_qs.filter(expense_type=Expense.TYPE_GENERAL)
    )

    branches = Branch.objects.filter(company=company, is_active=True)
    if not is_admin and not is_viewing_company and user_branch:
        branches = branches.filter(id=user_branch.id)

    context = {
        'company': company,
        'report_date': report_date,
        'expenses': expenses,
        'summary': summary,
        'category_breakdown': category_breakdown,
        'branches': branches,
        'selected_branch': branch_id,
        'selected_type': expense_type,
        'expense_types': Expense.EXPENSE_TYPES,
        'expense_categories': Expense.GENERAL_CATEGORIES,
        'is_expenses': True,
        'is_admin': is_admin,
        'is_viewing_company': is_viewing_company,
        'user_branch': user_branch,
    }
    return render(request, 'company/expenses/daily_detail.html', context)




# ============================================
# SALARIES PAGE
# ============================================
@login_required
def salaries_list(request):
    """Payroll list — one row per salary expense."""
    company, is_admin, user_branch, context = _base_context(request, Expense.TYPE_SALARY)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    qs = Expense.objects.filter(company=company, expense_type=Expense.TYPE_SALARY)
    if not is_admin and not context['is_viewing_company'] and user_branch:
        qs = qs.filter(branch=user_branch)

    # Filters
    status = request.GET.get('status')
    month = request.GET.get('month')  # YYYY-MM
    branch_id = request.GET.get('branch')

    if status:
        qs = qs.filter(status=status)
    if month:
        try:
            month_date = datetime.strptime(month, '%Y-%m').date()
            qs = qs.filter(salary_month=month_date)
        except ValueError:
            pass
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    qs = qs.order_by('-salary_month', 'employee_name')

    summary = get_expenses_summary(qs)
    context.update({
        'expenses': qs,
        'summary': summary,
        'statuses': Expense.EXPENSE_STATUS,
        'selected_status': status,
        'selected_month': month,
        'selected_branch': branch_id,
        'today': timezone.now().date(),
    })
    return render(request, 'company/expenses/salaries_list.html', context)


@login_required
def salary_create(request):
    return _expense_type_create(request, Expense.TYPE_SALARY, 'company-salaries-list')


@login_required
def salary_edit(request, pk):
    return _expense_type_edit(request, pk, Expense.TYPE_SALARY, 'company-salaries-list')


# ============================================
# RENTS PAGE
# ============================================
@login_required
def rents_list(request):
    company, is_admin, user_branch, context = _base_context(request, Expense.TYPE_RENT)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    qs = Expense.objects.filter(company=company, expense_type=Expense.TYPE_RENT)
    if not is_admin and not context['is_viewing_company'] and user_branch:
        qs = qs.filter(branch=user_branch)

    status = request.GET.get('status')
    month = request.GET.get('month')
    branch_id = request.GET.get('branch')

    if status:
        qs = qs.filter(status=status)
    if month:
        try:
            month_date = datetime.strptime(month, '%Y-%m').date()
            qs = qs.filter(rent_month=month_date)
        except ValueError:
            pass
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    qs = qs.order_by('-rent_month', 'branch__name')
    summary = get_expenses_summary(qs)

    context.update({
        'expenses': qs,
        'summary': summary,
        'statuses': Expense.EXPENSE_STATUS,
        'selected_status': status,
        'selected_month': month,
        'selected_branch': branch_id,
        'today': timezone.now().date(),
    })
    return render(request, 'company/expenses/rents_list.html', context)


@login_required
def rent_create(request):
    return _expense_type_create(request, Expense.TYPE_RENT, 'company-rents-list')


@login_required
def rent_edit(request, pk):
    return _expense_type_edit(request, pk, Expense.TYPE_RENT, 'company-rents-list')


# ============================================
# BILLS PAGE
# ============================================
@login_required
def bills_list(request):
    company, is_admin, user_branch, context = _base_context(request, Expense.TYPE_BILL)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    qs = Expense.objects.filter(company=company, expense_type=Expense.TYPE_BILL)
    if not is_admin and not context['is_viewing_company'] and user_branch:
        qs = qs.filter(branch=user_branch)

    status = request.GET.get('status')
    bill_type = request.GET.get('bill_type')
    month = request.GET.get('month')
    branch_id = request.GET.get('branch')

    if status:
        qs = qs.filter(status=status)
    if bill_type:
        qs = qs.filter(bill_type=bill_type)
    if month:
        try:
            month_date = datetime.strptime(month, '%Y-%m').date()
            qs = qs.filter(bill_period=month_date)
        except ValueError:
            pass
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    qs = qs.order_by('-bill_period', 'bill_name')
    summary = get_expenses_summary(qs)

    context.update({
        'expenses': qs,
        'summary': summary,
        'statuses': Expense.EXPENSE_STATUS,
        'bill_types': Expense.BILL_TYPES,
        'selected_status': status,
        'selected_bill_type': bill_type,
        'selected_month': month,
        'selected_branch': branch_id,
        'today': timezone.now().date(),
    })
    return render(request, 'company/expenses/bills_list.html', context)


@login_required
def bill_create(request):
    return _expense_type_create(request, Expense.TYPE_BILL, 'company-bills-list')


@login_required
def bill_edit(request, pk):
    return _expense_type_edit(request, pk, Expense.TYPE_BILL, 'company-bills-list')


# ============================================
# GENERAL EXPENSES PAGE
# ============================================
@login_required
def general_list(request):
    company, is_admin, user_branch, context = _base_context(request, Expense.TYPE_GENERAL)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    qs = Expense.objects.filter(company=company, expense_type=Expense.TYPE_GENERAL)
    if not is_admin and not context['is_viewing_company'] and user_branch:
        qs = qs.filter(branch=user_branch)

    status = request.GET.get('status')
    category = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    branch_id = request.GET.get('branch')

    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    qs = qs.order_by('-expense_date')
    summary = get_expenses_summary(qs)

    context.update({
        'expenses': qs,
        'summary': summary,
        'statuses': Expense.EXPENSE_STATUS,
        'expense_categories': Expense.GENERAL_CATEGORIES,
        'selected_status': status,
        'selected_category': category,
        'date_from': date_from,
        'date_to': date_to,
        'selected_branch': branch_id,
        'today': timezone.now().date(),
    })
    return render(request, 'company/expenses/general_list.html', context)


@login_required
def general_create(request):
    return _expense_type_create(request, Expense.TYPE_GENERAL, 'company-general-list')


@login_required
def general_edit(request, pk):
    return _expense_type_edit(request, pk, Expense.TYPE_GENERAL, 'company-general-list')


# ============================================
# SHARED CREATE / EDIT HANDLERS
# ============================================
def _expense_type_create(request, expense_type, redirect_name):
    company, is_admin, user_branch, context = _base_context(request, expense_type)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            data = _parse_expense_post(request, expense_type, company, is_admin, user_branch)
            if data is None:
                return redirect(request.path)
            Expense.objects.create(**data)
            messages.success(request, f'✅ {expense_type.title()} expense recorded successfully!')
            return redirect(redirect_name)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid amount entered.')
            return redirect(request.path)
        except Exception as e:
            messages.error(request, f'❌ Error saving expense: {str(e)}')
            return redirect(request.path)

    context.update(_form_context(expense_type, None))
    return render(request, 'company/expenses/form.html', context)


def _expense_type_edit(request, pk, expense_type, redirect_name):
    company, is_admin, user_branch, context = _base_context(request, expense_type)
    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    expense = get_object_or_404(Expense, id=pk, company=company, expense_type=expense_type)

    if not is_admin and not context['is_viewing_company'] and user_branch and expense.branch and expense.branch.id != user_branch.id:
        messages.error(request, 'You do not have permission to edit this expense.')
        return redirect(redirect_name)

    if request.method == 'POST':
        try:
            data = _parse_expense_post(request, expense_type, company, is_admin, user_branch, instance=expense)
            if data is None:
                return redirect(request.path)

            for key, value in data.items():
                if key != 'company':
                    setattr(expense, key, value)

            # Handle remove attachment
            if request.POST.get('remove_attachment') == '1' and expense.attachment:
                expense.attachment.delete(save=False)
                expense.attachment = None

            expense.save()
            messages.success(request, f'✅ Expense updated successfully!')
            return redirect(redirect_name)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid amount entered.')
            return redirect(request.path)
        except Exception as e:
            messages.error(request, f'❌ Error updating expense: {str(e)}')
            return redirect(request.path)

    context.update(_form_context(expense_type, expense))
    return render(request, 'company/expenses/form.html', context)


def _parse_expense_post(request, expense_type, company, is_admin, user_branch, instance=None):
    """Parse POST data into a dict suitable for Expense create/update."""
    expense_date_str = request.POST.get('expense_date')
    description = request.POST.get('description', '').strip()
    amount = Decimal(request.POST.get('amount', '0'))
    branch_id = request.POST.get('branch')
    payment_method = request.POST.get('payment_method', 'cash')
    reference = request.POST.get('reference', '').strip()
    notes = request.POST.get('notes', '').strip()
    attachment = request.FILES.get('attachment')

    if not expense_date_str or not description or amount <= 0:
        messages.error(request, 'Please fill all required fields with valid values.')
        return None

    attachment_error = validate_attachment(attachment)
    if attachment_error:
        messages.error(request, attachment_error)
        return None

    # Branch
    branch = None
    if branch_id:
        try:
            branch = Branch.objects.get(id=branch_id, company=company)
        except Branch.DoesNotExist:
            messages.error(request, 'Selected branch does not exist.')
            return None
        if not is_admin and user_branch and branch.id != user_branch.id:
            messages.error(request, 'You do not have access to this branch.')
            return None
    elif not is_admin and user_branch:
        branch = user_branch

    data = {
        'company': company,
        'branch': branch,
        'expense_type': expense_type,
        'expense_date': datetime.strptime(expense_date_str, '%Y-%m-%d').date(),
        'description': description,
        'amount': amount,
        'payment_method': payment_method,
        'reference': reference,
        'notes': notes,
        'created_by': request.user,
        'status': Expense.STATUS_PENDING,
    }

    if attachment:
        data['attachment'] = attachment
    elif instance is None:
        data['attachment'] = None

    # ---- Type-specific fields ----
    if expense_type == Expense.TYPE_SALARY:
        salary_month_str = request.POST.get('salary_month', '')
        data.update({
            'employee_name': request.POST.get('employee_name', '').strip(),
            'employee_id': request.POST.get('employee_id', '').strip(),
            'employee_phone': request.POST.get('employee_phone', '').strip(),
            'salary_month': datetime.strptime(salary_month_str + '-01', '%Y-%m-%d').date() if salary_month_str else None,
        })
        if not data['employee_name'] or not data['salary_month']:
            messages.error(request, 'Employee name and salary month are required.')
            return None

    elif expense_type == Expense.TYPE_RENT:
        rent_month_str = request.POST.get('rent_month', '')
        data.update({
            'rent_month': datetime.strptime(rent_month_str + '-01', '%Y-%m-%d').date() if rent_month_str else None,
            'landlord_name': request.POST.get('landlord_name', '').strip(),
            'landlord_phone': request.POST.get('landlord_phone', '').strip(),
            'receipt_number': request.POST.get('receipt_number', '').strip(),
        })
        if not data['rent_month']:
            messages.error(request, 'Rent month is required.')
            return None

    elif expense_type == Expense.TYPE_BILL:
        bill_period_str = request.POST.get('bill_period', '')
        data.update({
            'bill_type': request.POST.get('bill_type', '').strip(),
            'bill_name': request.POST.get('bill_name', '').strip(),
            'bill_period': datetime.strptime(bill_period_str + '-01', '%Y-%m-%d').date() if bill_period_str else None,
            'receipt_number': request.POST.get('receipt_number', '').strip(),
        })
        if not data['bill_name']:
            messages.error(request, 'Bill name is required.')
            return None

    elif expense_type == Expense.TYPE_GENERAL:
        data['category'] = request.POST.get('category', '').strip()
        if not data['category']:
            messages.error(request, 'Category is required.')
            return None

    return data


def _form_context(expense_type, expense):
    """Extra context for the form template based on expense type."""
    ctx = {
        'expense': expense,
        'expense_type': expense_type,
        'is_edit': expense is not None,
        'today': timezone.now().date(),
        'payment_methods': Expense.PAYMENT_METHODS,
        'general_categories': Expense.GENERAL_CATEGORIES,
        'bill_types': Expense.BILL_TYPES,
    }
    return ctx


# ============================================
# DETAIL / DELETE / APPROVE / REJECT / PAY
# ============================================
@login_required
def expense_detail(request, pk):
    company, is_viewing_company = get_active_company(request)
    if not company:
        return redirect('/dashboard/')
    expense = get_object_or_404(Expense, id=pk, company=company)
    user_branch = get_user_branch(request.user)
    is_admin = is_viewing_company or request.user.role in ['super_admin', 'company_admin']
    if not is_admin and user_branch and expense.branch and expense.branch.id != user_branch.id:
        messages.error(request, 'You do not have permission to view this expense.')
        return redirect('company-expenses-dashboard')

    context = {
        'expense': expense,
        'company': company,
        'is_expenses': True,
        'is_admin': is_admin,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/expenses/detail.html', context)


@login_required
def expense_delete(request, pk):
    company, is_viewing_company = get_active_company(request)
    if not company:
        return redirect('/dashboard/')
    expense = get_object_or_404(Expense, id=pk, company=company)
    user_branch = get_user_branch(request.user)
    is_admin = is_viewing_company or request.user.role in ['super_admin', 'company_admin']
    if not is_admin and user_branch and expense.branch and expense.branch.id != user_branch.id:
        messages.error(request, 'You do not have permission to delete this expense.')
        return redirect('company-expenses-dashboard')

    # Determine redirect based on type
    redirect_map = {
        Expense.TYPE_SALARY: 'company-salaries-list',
        Expense.TYPE_RENT: 'company-rents-list',
        Expense.TYPE_BILL: 'company-bills-list',
        Expense.TYPE_GENERAL: 'company-general-list',
    }
    redirect_name = redirect_map.get(expense.expense_type, 'company-expenses-dashboard')

    if request.method == 'POST':
        try:
            if expense.attachment:
                expense.attachment.delete(save=False)
            expense.delete()
            messages.success(request, '✅ Expense deleted successfully!')
        except Exception as e:
            messages.error(request, f'❌ Error deleting expense: {str(e)}')
        return redirect(redirect_name)

    context = {
        'expense': expense,
        'company': company,
        'is_expenses': True,
        'is_admin': is_admin,
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/expenses/confirm_delete.html', context)


@login_required
def expense_approve(request, pk):
    company, _ = get_active_company(request)
    if not company:
        return redirect('/dashboard/')
    expense = get_object_or_404(Expense, id=pk, company=company)
    if request.method == 'POST':
        try:
            expense.approve(request.user)
            messages.success(request, f'✅ Expense approved!')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
        return redirect(request.META.get('HTTP_REFERER', 'company-expenses-dashboard'))
    return render(request, 'company/expenses/approve.html', {'expense': expense, 'company': company})


@login_required
def expense_reject(request, pk):
    company, _ = get_active_company(request)
    if not company:
        return redirect('/dashboard/')
    expense = get_object_or_404(Expense, id=pk, company=company)
    if request.method == 'POST':
        try:
            expense.reject()
            messages.success(request, f'✅ Expense rejected!')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
        return redirect(request.META.get('HTTP_REFERER', 'company-expenses-dashboard'))
    return render(request, 'company/expenses/reject.html', {'expense': expense, 'company': company})


@login_required
def expense_mark_paid(request, pk):
    """Mark salary/rent/bill as paid."""
    company, _ = get_active_company(request)
    if not company:
        return redirect('/dashboard/')
    expense = get_object_or_404(Expense, id=pk, company=company)
    if request.method == 'POST':
        try:
            expense.mark_paid(request.user)
            messages.success(request, f'✅ Expense marked as Paid!')
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
    return redirect(request.META.get('HTTP_REFERER', 'company-expenses-dashboard'))





# ============================================
# HELPER FUNCTIONS
# ============================================

def get_expenses_summary(expenses_qs):
    """Calculate summary for expenses queryset."""
    total_expenses = expenses_qs.count()
    total_amount = expenses_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return {
        'total_expenses': total_expenses,
        'total_amount': total_amount,
    }


def get_daily_expense_records_with_submitters(expenses_qs, start_date, end_date):
    """
    Get daily expense records with submitter information.
    Returns a list of dicts — one per day in the range.
    """
    records = []
    current_date = start_date
    today = timezone.now().date()

    while current_date <= end_date:
        day_expenses = expenses_qs.filter(expense_date=current_date)
        summary = get_expenses_summary(day_expenses)

        # Collect distinct submitters for this day
        submitters_qs = day_expenses.values(
            'created_by__id',
            'created_by__username',
            'created_by__first_name',
            'created_by__last_name',
        ).distinct()

        submitter_names = []
        submitter_usernames = []
        submitter_ids = []

        for submitter in submitters_qs:
            first_name = submitter.get('created_by__first_name', '') or ''
            last_name = submitter.get('created_by__last_name', '') or ''
            username = submitter.get('created_by__username', '') or ''
            user_id = submitter.get('created_by__id')

            if first_name or last_name:
                full_name = f"{first_name} {last_name}".strip()
                submitter_names.append(full_name)
            elif username:
                submitter_names.append(username)

            if username:
                submitter_usernames.append(username)
            if user_id:
                submitter_ids.append(user_id)

        if submitter_names:
            if len(submitter_names) == 1:
                submitted_by_display = submitter_names[0]
                submitter_count = 1
            else:
                submitted_by_display = f"{submitter_names[0]} +{len(submitter_names) - 1} more"
                submitter_count = len(submitter_names)
        else:
            submitted_by_display = 'N/A'
            submitter_count = 0

        records.append({
            'date': current_date,
            'day_name': current_date.strftime('%A'),
            'expense_count': summary['total_expenses'],
            'total_amount': summary['total_amount'],
            'is_today': current_date == today,
            'submitted_by': submitted_by_display,
            'submitted_by_full': ', '.join(submitter_names) if submitter_names else 'N/A',
            'submitted_by_usernames': submitter_usernames,
            'submitted_by_ids': submitter_ids,
            'submitter_count': submitter_count,
            'submitters': submitters_qs,
        })
        current_date += timedelta(days=1)

    return records


def get_category_breakdown(expenses_qs):
    """Get expense breakdown by general expense category."""
    from .models import Expense as _Expense  # local import avoids circular issues

    breakdown = {}
    for category in _Expense.GENERAL_CATEGORIES:
        breakdown[category[0]] = {
            'label': category[1],
            'count': 0,
            'amount': Decimal('0.00'),
        }

    category_data = expenses_qs.values('category').annotate(
        count=Count('id'),
        total=Sum('amount'),
    )

    for data in category_data:
        key = data['category']
        if key in breakdown:
            breakdown[key]['count'] = data['count'] or 0
            breakdown[key]['amount'] = data['total'] or Decimal('0.00')

    return breakdown


def get_user_branch(user):
    """Get the user's branch (if assigned)."""
    if hasattr(user, 'branch') and user.branch:
        return user.branch
    return None


def validate_attachment(file):
    """Validate an uploaded attachment file."""
    if not file:
        return None
    if file.size > MAX_ATTACHMENT_SIZE:
        return f'Attachment is too large (max {MAX_ATTACHMENT_SIZE // (1024 * 1024)} MB).'
    name = file.name.lower()
    if not name.endswith(ALLOWED_ATTACHMENT_EXTENSIONS):
        allowed = ', '.join(ALLOWED_ATTACHMENT_EXTENSIONS)
        return f'Invalid file type. Allowed: {allowed}'
    return None