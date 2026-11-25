from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum
from django.utils import timezone
from apps.customers.models import Customer
from apps.companies.models import Company
import json
from decimal import Decimal, InvalidOperation
from apps.chama.models import Loan



# Define admin roles for this file
ADMIN_ROLES = [
    'super_admin', 'company_admin', 'company_manager',
    'chairperson', 'vice_chairperson', 'treasurer', 'secretary',
    'vice_secretary', 'loan_officer',
]



def _get_company(request):
    """Helper to resolve the active company for the current request."""
    company = getattr(request, 'company', None) or getattr(request, 'current_company', None)
    if company:
        return company
    if request.user.is_authenticated and getattr(request.user, 'company_id', None):
        return request.user.company
    company_id = request.session.get('viewing_company_id') or request.session.get('company_id')
    if company_id:
        return Company.objects.filter(pk=company_id).first()
    return None






@login_required
def external_loan_limits(request):
    """View to manage external loan limits for customers."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    is_officer = request.user.role in ADMIN_ROLES
    if not is_officer:
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('chama:dashboard')

    customers = Customer.objects.filter(company=company).order_by('full_name')

    rows = []
    for c in customers:
        # 👇 FIX: Calculate active loans based on Guest phone or ID
        identifier = c.national_id or c.phone_number
        
        # Find all approved/disbursed external loans for this customer's Guest profile
        active_loans_qs = Loan.objects.filter(
            company=company,
            loan_category='external',
            status__in=['approved', 'disbursed'],
            guest__national_id=identifier
        )
        
        # Calculate the total principal (or you can use total_repayable if you want interest included)
        active_loan_total = active_loans_qs.aggregate(total=Sum('principal'))['total'] or Decimal('0.00')

        rows.append({
            'customer': c,
            'custom_limit': c.custom_loan_limit,
            'active_loans_total': active_loan_total,
            'available_borrowing_power': max(Decimal('0.00'), c.custom_loan_limit - active_loan_total),
        })

    # Fetch pending external loan requests
    pending_loans = Loan.objects.filter(
        company=company,
        loan_category='external',
        status='pending'
    ).select_related('guest', 'loan_type').order_by('-requested_on')

    return render(request, 'chama/external_loan_limits.html', {
        'rows': rows,
        'is_officer': True,
        'pending_loans': pending_loans,
        'pending_count': pending_loans.count(),
    })




@login_required
def chama_customer_list(request):
    """View to list customers registered under this Chama's company."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    is_officer = request.user.role in ADMIN_ROLES
    if not is_officer:
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('chama:dashboard')

    customers = Customer.objects.filter(company=company).order_by('-created_at')

    return render(request, 'customers/chama/list.html', {
        'customers': customers,
        'is_officer': is_officer,
    })


@login_required
def customer_loan_history(request, customer_pk):
    """AJAX endpoint for the Review History modal."""
    company = _get_company(request)
    if not company:
        return JsonResponse({'error': 'No company assigned.'}, status=400)

    if request.user.role not in ADMIN_ROLES:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    customer = get_object_or_404(Customer, pk=customer_pk, company=company)

    loans = [] 

    return JsonResponse({
        'member': {
            'id': customer.pk,
            'full_name': customer.full_name,
            'member_number': customer.phone_number,
            'membership_type': 'External Customer',
            'total_contributions_paid': 0,
            'has_good_repayment_history': False,
            'custom_loan_limit': float(customer.custom_loan_limit),
            'active_loans_total': 0,
            'available_borrowing_power': float(customer.custom_loan_limit),
        },
        'contributions': [],
        'loans': loans,
    })


@login_required
def customer_loan_limit_adjust(request, customer_pk):
    """AJAX POST endpoint to update a customer's custom limit."""
    company = _get_company(request)
    if not company:
        return JsonResponse({'error': 'No company assigned.'}, status=400)

    if request.user.role not in ADMIN_ROLES:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    customer = get_object_or_404(Customer, pk=customer_pk, company=company)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    raw = payload.get('custom_limit', '')
    try:
        new_limit = Decimal(str(raw).strip() or '0')
    except (InvalidOperation, ValueError):
        return JsonResponse({'error': 'Invalid amount.'}, status=400)

    if new_limit < 0:
        return JsonResponse({'error': 'Limit cannot be negative.'}, status=400)

    customer.custom_loan_limit = new_limit
    customer.save(update_fields=['custom_loan_limit'])

    return JsonResponse({
        'ok': True,
        'custom_loan_limit': float(customer.custom_loan_limit),
        'message': f'Limit updated to KES {customer.custom_loan_limit:,.2f}',
    })


@login_required
def customer_review_view(request, customer_pk):
    """Page to review a customer's KYC documents and assign a loan limit."""
    company = _get_company(request)
    if not company:
        messages.error(request, 'No company assigned.')
        return redirect('chama:dashboard')

    is_officer = request.user.role in ADMIN_ROLES
    if not is_officer:
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('chama:dashboard')

    customer = get_object_or_404(Customer, pk=customer_pk, company=company)

    if request.method == 'POST':
        new_limit = request.POST.get('custom_limit')
        new_comment = request.POST.get('reviewer_comment', '').strip()
        
        if new_limit is not None:
            try:
                customer.custom_loan_limit = float(new_limit)
                customer.reviewer_comment = new_comment
                
                # Record who made the comment and when
                if new_comment:
                    customer.reviewed_by = request.user
                    customer.reviewed_at = timezone.now()
                
                customer.save()
                messages.success(request, f"Review saved for {customer.full_name}. Limit updated to KES {new_limit}.")
                
                # 👇 CHANGED: Redirect back to the SAME review page
                return redirect('chama:customer_review', customer_pk=customer.pk)
                
            except ValueError:
                messages.error(request, "Invalid limit amount.")

    return render(request, 'customers/chama/review.html', {
        'customer': customer,
    })