from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from .models import Plan, Subscription, PlanFeature
from apps.companies.models import Company, BusinessType
import json


# ============================================
# PLAN LIST - Super Admin
# ============================================

@login_required
@staff_member_required
def plan_list(request):
    """List all plans (Super Admin)"""
    plans = Plan.objects.all().order_by('order', 'price')
    
    context = {
        'plans': plans,
        'total_count': plans.count(),
        'page_title': 'Plans',
        'page_subtitle': 'Manage subscription plans',
    }
    return render(request, 'plans/list.html', context)


# ============================================
# PLAN CREATE - Super Admin
# ============================================

@login_required
@staff_member_required
def plan_create(request):
    """Create a new plan (Super Admin)"""
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name')
            display_name = request.POST.get('display_name')
            description = request.POST.get('description', '')
            price = float(request.POST.get('price', 0))
            billing_cycle = request.POST.get('billing_cycle', 'monthly')
            currency = request.POST.get('currency', 'KES')
            
            max_employees = int(request.POST.get('max_employees', 5))
            max_companies = int(request.POST.get('max_companies', 1))
            max_branches = int(request.POST.get('max_branches', 1))
            max_storage = int(request.POST.get('max_storage', 100))
            
            has_api_access = request.POST.get('has_api_access') == 'on'
            has_advanced_reports = request.POST.get('has_advanced_reports') == 'on'
            has_custom_branding = request.POST.get('has_custom_branding') == 'on'
            has_priority_support = request.POST.get('has_priority_support') == 'on'
            has_bulk_import = request.POST.get('has_bulk_import') == 'on'
            has_custom_domain = request.POST.get('has_custom_domain') == 'on'
            has_mpesa_intergration = request.POST.get('has_mpesa_intergration') == 'on'
            
            is_active = request.POST.get('is_active') == 'on'
            is_featured = request.POST.get('is_featured') == 'on'
            order = int(request.POST.get('order', 0))
            
            # Validate
            if not name:
                messages.error(request, 'Plan name is required.')
                return render(request, 'plans/plan_form.html', {
                    'business_types': business_types,
                    'plan_types': Plan.PLAN_TYPES,
                    'billing_cycles': Plan.BILLING_CYCLES,
                    'form_data': request.POST,
                    'is_edit': False,
                    'page_title': 'Create Plan',
                    'page_subtitle': 'Add a new subscription plan',
                })
            
            if Plan.objects.filter(name=name).exists():
                messages.error(request, f'Plan "{name}" already exists.')
                return render(request, 'plans/plan_form.html', {
                    'business_types': business_types,
                    'plan_types': Plan.PLAN_TYPES,
                    'billing_cycles': Plan.BILLING_CYCLES,
                    'form_data': request.POST,
                    'is_edit': False,
                    'page_title': 'Create Plan',
                    'page_subtitle': 'Add a new subscription plan',
                })
            
            # Create plan
            plan = Plan.objects.create(
                name=name,
                display_name=display_name or name.title(),
                description=description,
                price=price,
                billing_cycle=billing_cycle,
                currency=currency,
                max_employees=max_employees,
                max_companies=max_companies,
                max_branches=max_branches,
                max_storage=max_storage,
                has_api_access=has_api_access,
                has_advanced_reports=has_advanced_reports,
                has_custom_branding=has_custom_branding,
                has_priority_support=has_priority_support,
                has_bulk_import=has_bulk_import,
                has_custom_domain=has_custom_domain,
                has_mpesa_intergration=has_mpesa_intergration,
                is_active=is_active,
                is_featured=is_featured,
                order=order
            )
            
            # Add allowed business types
            allowed_business_types = request.POST.getlist('allowed_business_types')
            if allowed_business_types:
                plan.allowed_business_types.set(allowed_business_types)
            
            messages.success(request, f'Plan "{plan.display_name}" created successfully!')
            return redirect('plans:plan-list')
            
        except Exception as e:
            messages.error(request, f'Error creating plan: {str(e)}')
            return render(request, 'plans/plan_form.html', {
                'business_types': business_types,
                'plan_types': Plan.PLAN_TYPES,
                'billing_cycles': Plan.BILLING_CYCLES,
                'form_data': request.POST,
                'is_edit': False,
                'page_title': 'Create Plan',
                'page_subtitle': 'Add a new subscription plan',
            })
    
    context = {
        'business_types': business_types,
        'plan_types': Plan.PLAN_TYPES,
        'billing_cycles': Plan.BILLING_CYCLES,
        'page_title': 'Create Plan',
        'page_subtitle': 'Add a new subscription plan',
        'is_edit': False,
    }
    return render(request, 'plans/form.html', context)


# ============================================
# PLAN DETAIL - Super Admin
# ============================================

@login_required
@staff_member_required
def plan_detail(request, pk):
    """View plan details (Super Admin)"""
    plan = get_object_or_404(Plan, pk=pk)
    subscriptions = Subscription.objects.filter(plan=plan).select_related('company')
    
    context = {
        'plan': plan,
        'subscriptions': subscriptions,
        'subscription_count': subscriptions.count(),
        'page_title': plan.display_name,
        'page_subtitle': 'Plan details',
    }
    return render(request, 'plans/detail.html', context)


# ============================================
# PLAN EDIT - Super Admin
# ============================================

@login_required
@staff_member_required
def plan_edit(request, pk):
    """Edit a plan (Super Admin)"""
    plan = get_object_or_404(Plan, pk=pk)
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name')
            display_name = request.POST.get('display_name')
            description = request.POST.get('description', '')
            price = float(request.POST.get('price', 0))
            billing_cycle = request.POST.get('billing_cycle', 'monthly')
            currency = request.POST.get('currency', 'KES')
            
            max_employees = int(request.POST.get('max_employees', 5))
            max_companies = int(request.POST.get('max_companies', 1))
            max_branches = int(request.POST.get('max_branches', 1))
            max_storage = int(request.POST.get('max_storage', 100))
            
            has_api_access = request.POST.get('has_api_access') == 'on'
            has_advanced_reports = request.POST.get('has_advanced_reports') == 'on'
            has_custom_branding = request.POST.get('has_custom_branding') == 'on'
            has_priority_support = request.POST.get('has_priority_support') == 'on'
            has_bulk_import = request.POST.get('has_bulk_import') == 'on'
            has_custom_domain = request.POST.get('has_custom_domain') == 'on'
            has_mpesa_intergration = request.POST.get('has_mpesa_intergration') == 'on'
            
            is_active = request.POST.get('is_active') == 'on'
            is_featured = request.POST.get('is_featured') == 'on'
            order = int(request.POST.get('order', 0))
            
            # Validate
            if not name:
                messages.error(request, 'Plan name is required.')
                return render(request, 'plans/plan_form.html', {
                    'plan': plan,
                    'business_types': business_types,
                    'plan_types': Plan.PLAN_TYPES,
                    'billing_cycles': Plan.BILLING_CYCLES,
                    'is_edit': True,
                    'form_data': request.POST,
                    'page_title': f'Edit {plan.display_name}',
                    'page_subtitle': 'Edit plan details',
                })
            
            # Check if name is taken by another plan
            if Plan.objects.filter(name=name).exclude(pk=pk).exists():
                messages.error(request, f'Plan "{name}" already exists.')
                return render(request, 'plans/plan_form.html', {
                    'plan': plan,
                    'business_types': business_types,
                    'plan_types': Plan.PLAN_TYPES,
                    'billing_cycles': Plan.BILLING_CYCLES,
                    'is_edit': True,
                    'form_data': request.POST,
                    'page_title': f'Edit {plan.display_name}',
                    'page_subtitle': 'Edit plan details',
                })
            
            # Update plan
            plan.name = name
            plan.display_name = display_name or name.title()
            plan.description = description
            plan.price = price
            plan.billing_cycle = billing_cycle
            plan.currency = currency
            plan.max_employees = max_employees
            plan.max_companies = max_companies
            plan.max_branches = max_branches
            plan.max_storage = max_storage
            plan.has_api_access = has_api_access
            plan.has_advanced_reports = has_advanced_reports
            plan.has_custom_branding = has_custom_branding
            plan.has_priority_support = has_priority_support
            plan.has_bulk_import = has_bulk_import
            plan.has_custom_domain = has_custom_domain
            plan.has_mpesa_intergration = has_mpesa_intergration 
            plan.is_active = is_active
            plan.is_featured = is_featured
            plan.order = order
            plan.save()
            
            # Update allowed business types
            allowed_business_types = request.POST.getlist('allowed_business_types')
            plan.allowed_business_types.set(allowed_business_types)
            
            messages.success(request, f'Plan "{plan.display_name}" updated successfully!')
            return redirect('plans:plan-detail', pk=plan.id)
            
        except Exception as e:
            messages.error(request, f'Error updating plan: {str(e)}')
            return render(request, 'plans/plan_form.html', {
                'plan': plan,
                'business_types': business_types,
                'plan_types': Plan.PLAN_TYPES,
                'billing_cycles': Plan.BILLING_CYCLES,
                'is_edit': True,
                'form_data': request.POST,
                'page_title': f'Edit {plan.display_name}',
                'page_subtitle': 'Edit plan details',
            })
    
    context = {
        'plan': plan,
        'business_types': business_types,
        'plan_types': Plan.PLAN_TYPES,
        'billing_cycles': Plan.BILLING_CYCLES,
        'page_title': f'Edit {plan.display_name}',
        'page_subtitle': 'Edit plan details',
        'is_edit': True,
    }
    return render(request, 'plans/form.html', context)


# ============================================
# PLAN DELETE - Super Admin
# ============================================

@login_required
@staff_member_required
def plan_delete(request, pk):
    """Delete a plan (Super Admin)"""
    plan = get_object_or_404(Plan, pk=pk)
    
    if request.method == 'POST':
        try:
            # Check if plan has active subscriptions
            active_subscriptions = Subscription.objects.filter(plan=plan, status='active').count()
            if active_subscriptions > 0:
                messages.error(request, f'Cannot delete plan "{plan.display_name}" because it has {active_subscriptions} active subscriptions.')
                return redirect('plans:plan-list')
            
            plan_name = plan.display_name
            plan.delete()
            messages.success(request, f'Plan "{plan_name}" deleted successfully!')
            return redirect('plans:plan-list')
        except Exception as e:
            messages.error(request, f'Error deleting plan: {str(e)}')
    
    context = {
        'plan': plan,
        'page_title': f'Delete {plan.display_name}',
        'page_subtitle': 'Confirm deletion',
    }
    return render(request, 'plans/delete.html', context)


# ============================================
# PLAN TOGGLE STATUS - Super Admin
# ============================================

@login_required
@staff_member_required
def plan_toggle_status(request, pk):
    """Toggle plan active status (Super Admin)"""
    plan = get_object_or_404(Plan, pk=pk)
    
    if request.method == 'POST':
        plan.is_active = not plan.is_active
        plan.save()
        status = 'activated' if plan.is_active else 'deactivated'
        messages.success(request, f'Plan "{plan.display_name}" has been {status}.')
        return redirect('plans:plan-list')
    
    return redirect('plans:plan-list')


# ============================================
# SUBSCRIPTION LIST - Super Admin
# ============================================

@login_required
@staff_member_required
def subscription_list(request):
    """List all subscriptions (Super Admin)"""
    subscriptions = Subscription.objects.all().select_related('company', 'plan').order_by('-created_at')
    
    # Store original queryset for counts
    all_subscriptions = Subscription.objects.all()
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)
    
    # Filter by plan
    plan_filter = request.GET.get('plan', '')
    if plan_filter:
        subscriptions = subscriptions.filter(plan_id=plan_filter)
    
    # Search by company
    search_query = request.GET.get('search', '')
    if search_query:
        subscriptions = subscriptions.filter(
            Q(company__name__icontains=search_query) |
            Q(company__email__icontains=search_query)
        )
    
    # Get counts for stats
    active_count = all_subscriptions.filter(status='active').count()
    pending_count = all_subscriptions.filter(status='pending').count()
    expired_count = all_subscriptions.filter(status='expired').count()
    
    context = {
        'subscriptions': subscriptions,
        'total_count': subscriptions.count(),
        'active_count': active_count,
        'pending_count': pending_count,
        'expired_count': expired_count,
        'status_filter': status_filter,
        'plan_filter': plan_filter,
        'search_query': search_query,
        'plans': Plan.objects.filter(is_active=True),
        'page_title': 'Subscriptions',
        'page_subtitle': 'Manage company subscriptions',
    }
    return render(request, 'subscriptions/list.html', context)

# ============================================
# SUBSCRIPTION DETAIL - Super Admin
# ============================================

@login_required
@staff_member_required
def subscription_detail(request, pk):
    """View subscription details (Super Admin)"""
    subscription = get_object_or_404(Subscription, pk=pk)
    
    context = {
        'subscription': subscription,
        'page_title': f'Subscription #{subscription.id}',
        'page_subtitle': 'Subscription details',
    }
    return render(request, 'subscriptions/detail.html', context)


# ============================================
# SUBSCRIPTION CREATE - Super Admin
# ============================================

@login_required
@staff_member_required
def subscription_create(request):
    """Create a new subscription (Super Admin)"""
    companies = Company.objects.filter(is_active=True).order_by('name')
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')
    
    if request.method == 'POST':
        try:
            company_id = request.POST.get('company')
            plan_id = request.POST.get('plan')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            status = request.POST.get('status', 'active')
            payment_method = request.POST.get('payment_method', '')
            payment_reference = request.POST.get('payment_reference', '')
            
            if not company_id or not plan_id:
                messages.error(request, 'Company and Plan are required.')
                return render(request, 'plans/subscription_form.html', {
                    'companies': companies,
                    'plans': plans,
                    'form_data': request.POST
                })
            
            company = get_object_or_404(Company, pk=company_id)
            plan = get_object_or_404(Plan, pk=plan_id)
            
            # Check if company already has an active subscription
            if Subscription.objects.filter(company=company, status='active').exists():
                messages.warning(request, f'Company "{company.name}" already has an active subscription.')
            
            subscription = Subscription.objects.create(
                company=company,
                plan=plan,
                start_date=start_date or timezone.now(),
                end_date=end_date if end_date else None,
                status=status,
                payment_method=payment_method,
                payment_reference=payment_reference
            )
            
            # Update company plan
            company.plan = plan.name
            company.subscription_start = subscription.start_date
            company.subscription_end = subscription.end_date
            company.save()
            
            messages.success(request, f'Subscription created for "{company.name}" with plan "{plan.display_name}"')
            return redirect('plans:subscription-detail', pk=subscription.id)
            
        except Exception as e:
            messages.error(request, f'Error creating subscription: {str(e)}')
    
    context = {
        'companies': companies,
        'plans': plans,
        'page_title': 'Create Subscription',
        'page_subtitle': 'Assign a plan to a company',
    }
    return render(request, 'subscriptions/form.html', context)


# ============================================
# SUBSCRIPTION EDIT - Super Admin
# ============================================

@login_required
@staff_member_required
def subscription_edit(request, pk):
    """Edit a subscription (Super Admin)"""
    subscription = get_object_or_404(Subscription, pk=pk)
    companies = Company.objects.filter(is_active=True).order_by('name')
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')
    
    if request.method == 'POST':
        try:
            plan_id = request.POST.get('plan')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            status = request.POST.get('status', 'active')
            payment_method = request.POST.get('payment_method', '')
            payment_reference = request.POST.get('payment_reference', '')
            
            if not plan_id:
                messages.error(request, 'Plan is required.')
                return render(request, 'plans/subscription_form.html', {
                    'subscription': subscription,
                    'companies': companies,
                    'plans': plans,
                    'is_edit': True,
                    'form_data': request.POST
                })
            
            plan = get_object_or_404(Plan, pk=plan_id)
            
            subscription.plan = plan
            subscription.start_date = start_date or timezone.now()
            subscription.end_date = end_date if end_date else None
            subscription.status = status
            subscription.payment_method = payment_method
            subscription.payment_reference = payment_reference
            subscription.save()
            
            # Update company plan
            company = subscription.company
            company.plan = plan.name
            company.subscription_start = subscription.start_date
            company.subscription_end = subscription.end_date
            company.save()
            
            messages.success(request, f'Subscription updated successfully!')
            return redirect('plans:subscription-detail', pk=subscription.id)
            
        except Exception as e:
            messages.error(request, f'Error updating subscription: {str(e)}')
    
    context = {
        'subscription': subscription,
        'companies': companies,
        'plans': plans,
        'is_edit': True,
        'page_title': f'Edit Subscription #{subscription.id}',
        'page_subtitle': 'Edit subscription details',
    }
    return render(request, 'subscriptions/form.html', context)


# ============================================
# SUBSCRIPTION CANCEL - Super Admin
# ============================================

@login_required
@staff_member_required
def subscription_cancel(request, pk):
    """Cancel a subscription (Super Admin)"""
    subscription = get_object_or_404(Subscription, pk=pk)
    
    if request.method == 'POST':
        try:
            subscription.status = 'cancelled'
            subscription.save()
            
            messages.success(request, f'Subscription for "{subscription.company.name}" has been cancelled.')
            return redirect('plans:subscription-detail', pk=subscription.id)
        except Exception as e:
            messages.error(request, f'Error cancelling subscription: {str(e)}')
    
    context = {
        'subscription': subscription,
        'page_title': f'Cancel Subscription #{subscription.id}',
        'page_subtitle': 'Confirm cancellation',
    }
    return render(request, 'subscriptions/cancel.html', context)


# ============================================
# API ENDPOINTS
# ============================================

@login_required
def get_plans_api(request):
    """API endpoint to get all active plans"""
    plans = Plan.objects.filter(is_active=True).values(
        'id', 'name', 'display_name', 'price', 'billing_cycle', 'currency',
        'max_employees', 'max_companies', 'max_branches', 'max_storage'
    )
    return JsonResponse(list(plans), safe=False)


@login_required
def get_plan_detail_api(request, pk):
    """API endpoint to get plan details"""
    plan = get_object_or_404(Plan, pk=pk)
    data = {
        'id': plan.id,
        'name': plan.name,
        'display_name': plan.display_name,
        'description': plan.description,
        'price': float(plan.price),
        'billing_cycle': plan.billing_cycle,
        'currency': plan.currency,
        'max_employees': plan.max_employees,
        'max_companies': plan.max_companies,
        'max_branches': plan.max_branches,
        'max_storage': plan.max_storage,
        'features': plan.get_feature_list(),
        'has_api_access': plan.has_api_access,
        'has_advanced_reports': plan.has_advanced_reports,
        'has_custom_branding': plan.has_custom_branding,
        'has_priority_support': plan.has_priority_support,
        'has_bulk_import': plan.has_bulk_import,
        'has_custom_domain': plan.has_custom_domain,
        'has_mpesa_intergration': plan.has_mpesa_intergration, 
    }
    return JsonResponse(data)


@login_required
def get_company_subscription_api(request, company_id):
    """API endpoint to get company's current subscription"""
    try:
        subscription = Subscription.objects.filter(
            company_id=company_id,
            status='active'
        ).select_related('plan').first()
        
        if subscription:
            data = {
                'id': subscription.id,
                'plan': subscription.plan.name,
                'plan_display': subscription.plan.display_name,
                'start_date': subscription.start_date.isoformat(),
                'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
                'status': subscription.status,
                'is_active': subscription.is_active_subscription()
            }
        else:
            data = {
                'plan': 'free',
                'plan_display': 'Free',
                'status': 'active',
                'is_active': True
            }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)