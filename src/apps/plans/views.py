# apps/plans/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Plan, Subscription
from apps.companies.models import Company, BusinessType


# ============================================
# HELPERS
# ============================================

def _parse_dt(value):
    """Parse datetime string from form into aware datetime."""
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _sync_company_from_subscription(company, plan, start_dt, end_dt, status):
    """
    Single source of truth for updating Company.plan + subscription dates
    and keeping the Subscription row consistent.
    """
    company.plan = plan
    company.subscription_start = start_dt
    company.subscription_end = end_dt
    company.save(update_fields=['plan', 'subscription_start', 'subscription_end'])

    if not plan:
        return None

    # Prefer existing active row; fallback to latest row
    sub = (
        company.subscriptions.filter(status='active').order_by('-created_at').first()
        or company.subscriptions.order_by('-created_at').first()
    )

    if sub:
        sub.plan = plan
        sub.start_date = start_dt or sub.start_date
        sub.end_date = end_dt
        if status:
            sub.status = status
        sub.save()
        return sub

    return Subscription.objects.create(
        company=company,
        plan=plan,
        start_date=start_dt or timezone.now(),
        end_date=end_dt,
        status=status or 'active',
    )


# ============================================
# PLAN LIST
# ============================================

@login_required
@staff_member_required
def plan_list(request):
    plans = Plan.objects.all().order_by('order', 'price')
    context = {
        'plans': plans,
        'total_count': plans.count(),
        'page_title': 'Plans',
        'page_subtitle': 'Manage subscription plans',
    }
    return render(request, 'plans/list.html', context)


# ============================================
# PLAN CREATE
# ============================================

@login_required
@staff_member_required
def plan_create(request):
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            display_name = request.POST.get('display_name') or name.title()

            if not name:
                messages.error(request, 'Plan name is required.')
                return _render_plan_form(request, business_types, is_edit=False)

            if Plan.objects.filter(name=name).exists():
                messages.error(request, f'Plan "{name}" already exists.')
                return _render_plan_form(request, business_types, is_edit=False)

            plan = Plan.objects.create(
                name=name,
                display_name=display_name,
                description=request.POST.get('description', ''),
                price=float(request.POST.get('price', 0)),
                billing_cycle=request.POST.get('billing_cycle', 'monthly'),
                currency=request.POST.get('currency', 'KES'),
                max_employees=int(request.POST.get('max_employees', 5)),
                max_companies=int(request.POST.get('max_companies', 1)),
                max_branches=int(request.POST.get('max_branches', 1)),
                max_storage=int(request.POST.get('max_storage', 100)),
                has_api_access=request.POST.get('has_api_access') == 'on',
                has_advanced_reports=request.POST.get('has_advanced_reports') == 'on',
                has_custom_branding=request.POST.get('has_custom_branding') == 'on',
                has_priority_support=request.POST.get('has_priority_support') == 'on',
                has_bulk_import=request.POST.get('has_bulk_import') == 'on',
                has_custom_domain=request.POST.get('has_custom_domain') == 'on',
                has_mpesa_intergration=request.POST.get('has_mpesa_intergration') == 'on',
                is_active=request.POST.get('is_active') == 'on',
                is_featured=request.POST.get('is_featured') == 'on',
                order=int(request.POST.get('order', 0)),
            )

            allowed_types = request.POST.getlist('allowed_business_types')
            if allowed_types:
                plan.allowed_business_types.set(allowed_types)

            messages.success(request, f'Plan "{plan.display_name}" created successfully!')
            return redirect('plans:plan-list')

        except Exception as e:
            messages.error(request, f'Error creating plan: {str(e)}')
            return _render_plan_form(request, business_types, is_edit=False)

    return _render_plan_form(request, business_types, is_edit=False)


# ============================================
# PLAN DETAIL
# ============================================

@login_required
@staff_member_required
def plan_detail(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    subscriptions = (
        Subscription.objects
        .filter(plan=plan)
        .select_related('company')
        .order_by('-created_at')
    )

    context = {
        'plan': plan,
        'subscriptions': subscriptions,
        'subscription_count': subscriptions.filter(status='active').count(),
        'page_title': plan.display_name,
        'page_subtitle': 'Plan details',
    }
    return render(request, 'plans/detail.html', context)


# ============================================
# PLAN EDIT
# ============================================

@login_required
@staff_member_required
def plan_edit(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    business_types = BusinessType.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            name = request.POST.get('name')

            if not name:
                messages.error(request, 'Plan name is required.')
                return _render_plan_form(request, business_types, plan=plan, is_edit=True)

            if Plan.objects.filter(name=name).exclude(pk=pk).exists():
                messages.error(request, f'Plan "{name}" already exists.')
                return _render_plan_form(request, business_types, plan=plan, is_edit=True)

            plan.name = name
            plan.display_name = request.POST.get('display_name') or name.title()
            plan.description = request.POST.get('description', '')
            plan.price = float(request.POST.get('price', 0))
            plan.billing_cycle = request.POST.get('billing_cycle', 'monthly')
            plan.currency = request.POST.get('currency', 'KES')
            plan.max_employees = int(request.POST.get('max_employees', 5))
            plan.max_companies = int(request.POST.get('max_companies', 1))
            plan.max_branches = int(request.POST.get('max_branches', 1))
            plan.max_storage = int(request.POST.get('max_storage', 100))
            plan.has_api_access = request.POST.get('has_api_access') == 'on'
            plan.has_advanced_reports = request.POST.get('has_advanced_reports') == 'on'
            plan.has_custom_branding = request.POST.get('has_custom_branding') == 'on'
            plan.has_priority_support = request.POST.get('has_priority_support') == 'on'
            plan.has_bulk_import = request.POST.get('has_bulk_import') == 'on'
            plan.has_custom_domain = request.POST.get('has_custom_domain') == 'on'
            plan.has_mpesa_intergration = request.POST.get('has_mpesa_intergration') == 'on'
            plan.is_active = request.POST.get('is_active') == 'on'
            plan.is_featured = request.POST.get('is_featured') == 'on'
            plan.order = int(request.POST.get('order', 0))
            plan.save()

            allowed_types = request.POST.getlist('allowed_business_types')
            plan.allowed_business_types.set(allowed_types)

            messages.success(request, f'Plan "{plan.display_name}" updated successfully!')
            return redirect('plans:plan-detail', pk=plan.id)

        except Exception as e:
            messages.error(request, f'Error updating plan: {str(e)}')
            return _render_plan_form(request, business_types, plan=plan, is_edit=True)

    return _render_plan_form(request, business_types, plan=plan, is_edit=True)


# ============================================
# PLAN DELETE
# ============================================

@login_required
@staff_member_required
def plan_delete(request, pk):
    plan = get_object_or_404(Plan, pk=pk)

    if request.method == 'POST':
        try:
            active_subs = Subscription.objects.filter(plan=plan, status='active').count()
            if active_subs > 0:
                messages.error(
                    request,
                    f'Cannot delete plan "{plan.display_name}" — '
                    f'{active_subs} active subscriptions.'
                )
                return redirect('plans:plan-list')

            name = plan.display_name
            plan.delete()
            messages.success(request, f'Plan "{name}" deleted successfully!')
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
# PLAN TOGGLE STATUS
# ============================================

@login_required
@staff_member_required
def plan_toggle_status(request, pk):
    plan = get_object_or_404(Plan, pk=pk)

    if request.method == 'POST':
        plan.is_active = not plan.is_active
        plan.save(update_fields=['is_active'])
        status = 'activated' if plan.is_active else 'deactivated'
        messages.success(request, f'Plan "{plan.display_name}" has been {status}.')

    return redirect('plans:plan-list')


# ============================================
# SUBSCRIPTION LIST
# ============================================

@login_required
@staff_member_required
def subscription_list(request):
    base_qs = Subscription.objects.select_related('company', 'plan').order_by('-created_at')
    subscriptions = base_qs

    status_filter = request.GET.get('status', '')
    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)

    plan_filter = request.GET.get('plan', '')
    if plan_filter:
        subscriptions = subscriptions.filter(plan_id=plan_filter)

    search_query = request.GET.get('search', '')
    if search_query:
        subscriptions = subscriptions.filter(
            Q(company__name__icontains=search_query) |
            Q(company__email__icontains=search_query)
        )

    context = {
        'subscriptions': subscriptions,
        'total_count': subscriptions.count(),
        'active_count': Subscription.objects.filter(status='active').count(),
        'pending_count': Subscription.objects.filter(status='pending').count(),
        'expired_count': Subscription.objects.filter(status='expired').count(),
        'status_filter': status_filter,
        'plan_filter': plan_filter,
        'search_query': search_query,
        'plans': Plan.objects.filter(is_active=True),
        'page_title': 'Subscriptions',
        'page_subtitle': 'Manage company subscriptions',
    }
    return render(request, 'subscriptions/list.html', context)


# ============================================
# SUBSCRIPTION DETAIL
# ============================================

@login_required
@staff_member_required
def subscription_detail(request, pk):
    subscription = get_object_or_404(
        Subscription.objects.select_related('company', 'plan'),
        pk=pk,
    )
    context = {
        'subscription': subscription,
        'page_title': f'Subscription #{subscription.id}',
        'page_subtitle': 'Subscription details',
    }
    return render(request, 'subscriptions/detail.html', context)


# ============================================
# SUBSCRIPTION CREATE
# ============================================

@login_required
@staff_member_required
def subscription_create(request):
    companies = Company.objects.all().order_by('name')
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')
    preset_plan_id = request.GET.get('plan')

    if request.method == 'POST':
        try:
            company_id = request.POST.get('company')
            plan_id = request.POST.get('plan')
            start_dt = _parse_dt(request.POST.get('start_date')) or timezone.now()
            end_dt = _parse_dt(request.POST.get('end_date'))
            status = request.POST.get('status', 'active')
            payment_method = request.POST.get('payment_method', '')
            payment_reference = request.POST.get('payment_reference', '')

            if not company_id or not plan_id:
                messages.error(request, 'Company and Plan are required.')
                return render(request, 'subscriptions/form.html', {
                    'companies': companies,
                    'plans': plans,
                    'form_data': request.POST,
                })

            company = get_object_or_404(Company, pk=company_id)
            plan = get_object_or_404(Plan, pk=plan_id)

            if Subscription.objects.filter(company=company, status='active').exists():
                messages.warning(
                    request,
                    f'Company "{company.name}" already has an active subscription.'
                )

            subscription = Subscription.objects.create(
                company=company,
                plan=plan,
                start_date=start_dt,
                end_date=end_dt,
                status=status,
                payment_method=payment_method,
                payment_reference=payment_reference,
            )

            # Sync company (FK, not string)
            company.plan = plan
            company.subscription_start = subscription.start_date
            company.subscription_end = subscription.end_date
            if status == 'active':
                company.status = 'active'
                company.is_active = True
            company.save(update_fields=[
                'plan', 'subscription_start', 'subscription_end',
                'status', 'is_active',
            ])

            messages.success(
                request,
                f'Subscription created for "{company.name}" with plan "{plan.display_name}"'
            )
            return redirect('plans:subscription-detail', pk=subscription.id)

        except Exception as e:
            messages.error(request, f'Error creating subscription: {str(e)}')

    context = {
        'companies': companies,
        'plans': plans,
        'preset_plan_id': preset_plan_id,
        'page_title': 'Create Subscription',
        'page_subtitle': 'Assign a plan to a company',
    }
    return render(request, 'subscriptions/form.html', context)


# ============================================
# SUBSCRIPTION EDIT
# ============================================

@login_required
@staff_member_required
def subscription_edit(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk)
    companies = Company.objects.all().order_by('name')
    plans = Plan.objects.filter(is_active=True).order_by('order', 'price')

    if request.method == 'POST':
        try:
            plan_id = request.POST.get('plan')
            start_dt = _parse_dt(request.POST.get('start_date')) or subscription.start_date
            end_dt = _parse_dt(request.POST.get('end_date'))
            status = request.POST.get('status', 'active')
            payment_method = request.POST.get('payment_method', '')
            payment_reference = request.POST.get('payment_reference', '')

            if not plan_id:
                messages.error(request, 'Plan is required.')
                return render(request, 'subscriptions/form.html', {
                    'subscription': subscription,
                    'companies': companies,
                    'plans': plans,
                    'is_edit': True,
                    'form_data': request.POST,
                })

            plan = get_object_or_404(Plan, pk=plan_id)

            subscription.plan = plan
            subscription.start_date = start_dt
            subscription.end_date = end_dt
            subscription.status = status
            subscription.payment_method = payment_method
            subscription.payment_reference = payment_reference
            subscription.save()

            # Sync company
            company = subscription.company
            company.plan = plan
            company.subscription_start = subscription.start_date
            company.subscription_end = subscription.end_date
            if status == 'active':
                company.status = 'active'
                company.is_active = True
            company.save(update_fields=[
                'plan', 'subscription_start', 'subscription_end',
                'status', 'is_active',
            ])

            messages.success(request, 'Subscription updated successfully!')
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
# SUBSCRIPTION CANCEL
# ============================================

@login_required
@staff_member_required
def subscription_cancel(request, pk):
    subscription = get_object_or_404(Subscription, pk=pk)

    if request.method == 'POST':
        try:
            subscription.status = 'cancelled'
            subscription.save(update_fields=['status'])

            # Deactivate company if no other active sub remains
            company = subscription.company
            still_active = (
                company.subscriptions
                .filter(status='active', end_date__gt=timezone.now())
                .exclude(pk=subscription.pk)
                .exists()
            )
            if not still_active:
                company.status = 'inactive'
                company.is_active = False
                company.save(update_fields=['status', 'is_active'])

            messages.success(
                request,
                f'Subscription for "{subscription.company.name}" cancelled.'
            )
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
    plans = Plan.objects.filter(is_active=True).values(
        'id', 'name', 'display_name', 'price', 'billing_cycle', 'currency',
        'max_employees', 'max_companies', 'max_branches', 'max_storage',
    )
    return JsonResponse(list(plans), safe=False)


@login_required
def get_plan_detail_api(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    return JsonResponse({
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
        'has_mpesa_integration': plan.has_mpesa_intergration,
    })


@login_required
def get_company_subscription_api(request, company_id):
    try:
        sub = (
            Subscription.objects
            .filter(company_id=company_id, status='active')
            .select_related('plan')
            .order_by('-created_at')
            .first()
        )

        if sub:
            data = {
                'id': sub.id,
                'plan': sub.plan.name,
                'plan_display': sub.plan.display_name,
                'start_date': sub.start_date.isoformat(),
                'end_date': sub.end_date.isoformat() if sub.end_date else None,
                'status': sub.status,
                'display_state': sub.display_state,
                'days_until_expiry': sub.days_until_expiry,
                'is_active': sub.is_active_subscription(),
            }
        else:
            data = {
                'plan': 'free',
                'plan_display': 'Free',
                'status': 'active',
                'display_state': 'lifetime',
                'is_active': True,
            }

        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ============================================
# PRIVATE HELPERS
# ============================================

def _render_plan_form(request, business_types, plan=None, is_edit=False):
    """Single source for rendering the plan form with correct context."""
    context = {
        'business_types': business_types,
        'plan_types': Plan.PLAN_TYPES,
        'billing_cycles': Plan.BILLING_CYCLES,
        'form_data': request.POST if request.method == 'POST' else None,
        'is_edit': is_edit,
    }
    if plan:
        context['plan'] = plan
        context['page_title'] = f'Edit {plan.display_name}'
        context['page_subtitle'] = 'Edit plan details'
    else:
        context['page_title'] = 'Create Plan'
        context['page_subtitle'] = 'Add a new subscription plan'

    return render(request, 'plans/form.html', context)