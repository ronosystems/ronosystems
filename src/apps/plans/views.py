# apps/plans/views.py

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.companies.models import BusinessType, Company

from .models import (
    Plan,
    Subscription,
    sync_company_from_subscription,
)


# ============================================
# HELPERS
# ============================================

def _parse_dt(value):
    """Parse a datetime string from a form into an aware datetime."""
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _as_decimal(value, default='0'):
    """Safe Decimal coercion — never raises on '', None, or junk."""
    if value in (None, ''):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _as_int(value, default=0):
    """Safe int coercion — never raises on '', None, or junk."""
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _apply_plan_form(plan, post):
    """
    Populate a Plan from POST data. Single source of truth for
    create + edit so they can never drift apart.

    Returns (plan, error_message_or_None).
    """
    name = (post.get('name') or '').strip()
    if not name:
        return plan, 'Plan name is required.'

    plan_kind = post.get('plan_kind') or 'basic'
    valid_kinds = {k for k, _ in Plan.PLAN_TYPES}
    if plan_kind not in valid_kinds:
        plan_kind = 'basic'

    billing_cycle = post.get('billing_cycle') or 'monthly'
    valid_cycles = {c for c, _ in Plan.BILLING_CYCLES}
    if billing_cycle not in valid_cycles:
        billing_cycle = 'monthly'

    plan.name = name
    plan.plan_kind = plan_kind
    plan.display_name = (post.get('display_name') or name.title()).strip()
    plan.description = post.get('description', '')
    plan.price = _as_decimal(post.get('price', 0))
    plan.billing_cycle = billing_cycle
    plan.currency = (post.get('currency') or 'KES').strip().upper()[:3]
    plan.max_employees = _as_int(post.get('max_employees'), 5)
    plan.max_companies = _as_int(post.get('max_companies'), 1)
    plan.max_branches = _as_int(post.get('max_branches'), 1)
    plan.max_storage = _as_int(post.get('max_storage'), 100)
    plan.is_active = post.get('is_active') == 'on'
    plan.is_featured = post.get('is_featured') == 'on'
    plan.order = _as_int(post.get('order'), 0)

    # Iterate FEATURE_FLAGS so adding a new flag never needs a view edit.
    for flag, _label in Plan.FEATURE_FLAGS:
        setattr(plan, flag, post.get(flag) == 'on')

    return plan, None


def _subscription_features(plan):
    """Feature dict for a plan — safe when plan is None."""
    if plan is None:
        return {}
    return plan.enabled_features()


def _can_view_company_subscription(user, company):
    """
    Authorization for get_company_subscription_api.
    Staff always allowed. Otherwise user must belong to the company.
    Adjust the `.users` / `.members` accessor to match your Company model.
    """
    if user.is_staff or user.is_superuser:
        return True
    # Company membership: try common accessors, first one that exists wins.
    for accessor in ('users', 'members', 'employees'):
        manager = getattr(company, accessor, None)
        if manager is not None and hasattr(manager, 'filter'):
            try:
                if manager.filter(pk=user.pk).exists():
                    return True
            except Exception:
                pass
    # Fallback: a direct FK on the user model.
    return getattr(user, 'company_id', None) == company.pk


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
        plan = Plan()
        plan, error = _apply_plan_form(plan, request.POST)

        if error:
            messages.error(request, error)
            return _render_plan_form(request, business_types, is_edit=False)

        # Uniqueness check (name, billing_cycle) — matches the model constraint.
        if Plan.objects.filter(
            name=plan.name, billing_cycle=plan.billing_cycle
        ).exists():
            messages.error(
                request,
                f'A plan named "{plan.name}" already exists '
                f'for the {plan.billing_cycle} billing cycle.',
            )
            return _render_plan_form(request, business_types, is_edit=False)

        try:
            plan.save()
            allowed_types = request.POST.getlist('allowed_business_types')
            if allowed_types:
                plan.allowed_business_types.set(allowed_types)

            messages.success(
                request,
                f'Plan "{plan.display_name}" created successfully!',
            )
            return redirect('plans:plan-list')
        except Exception as e:
            messages.error(request, f'Error creating plan: {e}')
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
        plan, error = _apply_plan_form(plan, request.POST)

        if error:
            messages.error(request, error)
            return _render_plan_form(
                request, business_types, plan=plan, is_edit=True,
            )

        # Uniqueness check excluding self.
        if Plan.objects.filter(
            name=plan.name, billing_cycle=plan.billing_cycle,
        ).exclude(pk=pk).exists():
            messages.error(
                request,
                f'A plan named "{plan.name}" already exists '
                f'for the {plan.billing_cycle} billing cycle.',
            )
            return _render_plan_form(
                request, business_types, plan=plan, is_edit=True,
            )

        try:
            plan.save()
            allowed_types = request.POST.getlist('allowed_business_types')
            plan.allowed_business_types.set(allowed_types)

            messages.success(
                request,
                f'Plan "{plan.display_name}" updated successfully!',
            )
            return redirect('plans:plan-list')
        except Exception as e:
            messages.error(request, f'Error updating plan: {e}')
            return _render_plan_form(
                request, business_types, plan=plan, is_edit=True,
            )

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
            active_subs = Subscription.objects.filter(
                plan=plan, status='active',
            ).count()
            if active_subs > 0:
                messages.error(
                    request,
                    f'Cannot delete plan "{plan.display_name}" — '
                    f'{active_subs} active subscriptions.',
                )
                return redirect('plans:plan-list')

            name = plan.display_name
            plan.delete()
            messages.success(request, f'Plan "{name}" deleted successfully!')
            return redirect('plans:plan-list')
        except Exception as e:
            messages.error(request, f'Error deleting plan: {e}')

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
    base_qs = (
        Subscription.objects
        .select_related('company', 'plan')
        .order_by('-created_at')
    )
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
            Q(company__name__icontains=search_query)
            | Q(company__email__icontains=search_query)
        )

    try:
        per_page = int(request.GET.get('per_page', 10))
    except (TypeError, ValueError):
        per_page = 10
    if per_page not in (10, 25, 50, 100):
        per_page = 10

    paginator = Paginator(subscriptions, per_page)
    page_number = request.GET.get('page', 1)
    subscriptions_page = paginator.get_page(page_number)

    context = {
        'subscriptions': subscriptions_page,
        'per_page': per_page,
        'total_count': base_qs.count(),
        # Use the paginator's already-computed count — one fewer query.
        'filtered_count': subscriptions_page.paginator.count,
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

            if not company_id or not plan_id:
                messages.error(request, 'Company and Plan are required.')
                return render(request, 'subscriptions/form.html', {
                    'companies': companies,
                    'plans': plans,
                    'form_data': request.POST,
                    'page_title': 'Create Subscription',
                    'page_subtitle': 'Assign a plan to a company',
                })

            company = get_object_or_404(Company, pk=company_id)
            plan = get_object_or_404(Plan, pk=plan_id)

            start_dt = _parse_dt(request.POST.get('start_date')) or timezone.now()
            end_dt = _parse_dt(request.POST.get('end_date'))
            status = request.POST.get('status', 'active')
            payment_method = request.POST.get('payment_method', '')
            payment_reference = request.POST.get('payment_reference', '')

            # Guard against accidental lifetime grants.
            if end_dt is None and plan.billing_cycle != 'lifetime' and status == 'active':
                messages.error(
                    request,
                    'An end date is required unless the plan is lifetime.',
                )
                return render(request, 'subscriptions/form.html', {
                    'companies': companies,
                    'plans': plans,
                    'form_data': request.POST,
                    'page_title': 'Create Subscription',
                    'page_subtitle': 'Assign a plan to a company',
                })

            if Subscription.objects.filter(company=company, status='active').exists():
                messages.warning(
                    request,
                    f'Company "{company.name}" already has an active subscription.',
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

            # Single writer for the Company cache.
            sync_company_from_subscription(company, active_sub=subscription)

            messages.success(
                request,
                f'Subscription created for "{company.name}" '
                f'with plan "{plan.display_name}"',
            )
            return redirect('plans:subscription-detail', pk=subscription.id)

        except Exception as e:
            messages.error(request, f'Error creating subscription: {e}')

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
            if not plan_id:
                messages.error(request, 'Plan is required.')
                return render(request, 'subscriptions/form.html', {
                    'subscription': subscription,
                    'companies': companies,
                    'plans': plans,
                    'is_edit': True,
                    'form_data': request.POST,
                    'page_title': f'Edit Subscription #{subscription.id}',
                    'page_subtitle': 'Edit subscription details',
                })

            plan = get_object_or_404(Plan, pk=plan_id)
            start_dt = _parse_dt(request.POST.get('start_date')) or subscription.start_date
            end_dt = _parse_dt(request.POST.get('end_date'))
            status = request.POST.get('status', 'active')

            # Same lifetime guard as create.
            if end_dt is None and plan.billing_cycle != 'lifetime' and status == 'active':
                messages.error(
                    request,
                    'An end date is required unless the plan is lifetime.',
                )
                return render(request, 'subscriptions/form.html', {
                    'subscription': subscription,
                    'companies': companies,
                    'plans': plans,
                    'is_edit': True,
                    'form_data': request.POST,
                    'page_title': f'Edit Subscription #{subscription.id}',
                    'page_subtitle': 'Edit subscription details',
                })

            subscription.plan = plan
            subscription.start_date = start_dt
            subscription.end_date = end_dt
            subscription.status = status
            subscription.payment_method = request.POST.get('payment_method', '')
            subscription.payment_reference = request.POST.get('payment_reference', '')
            subscription.save()

            sync_company_from_subscription(subscription.company)

            messages.success(request, 'Subscription updated successfully!')
            return redirect('plans:subscription-detail', pk=subscription.id)

        except Exception as e:
            messages.error(request, f'Error updating subscription: {e}')

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
            # Delegate to the model — it handles atomicity + company sync.
            changed = subscription.cancel(by_user=request.user)

            if changed:
                messages.success(
                    request,
                    f'Subscription for "{subscription.company.name}" cancelled.',
                )
            else:
                messages.info(
                    request,
                    'This subscription was not active — nothing to cancel.',
                )
            return redirect('plans:subscription-detail', pk=subscription.id)
        except Exception as e:
            messages.error(request, f'Error cancelling subscription: {e}')

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
    plans = Plan.objects.filter(is_active=True)
    data = []
    for plan in plans:
        data.append({
            'id': plan.id,
            'name': plan.name,
            'plan_kind': plan.plan_kind,
            'display_name': plan.display_name,
            'price': float(plan.price),
            'billing_cycle': plan.billing_cycle,
            'currency': plan.currency,
            'max_employees': plan.max_employees,
            'max_companies': plan.max_companies,
            'max_branches': plan.max_branches,
            'max_storage': plan.max_storage,
            'features': plan.enabled_features(),
        })
    return JsonResponse(data, safe=False)


@login_required
def get_plan_detail_api(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    return JsonResponse({
        'id': plan.id,
        'name': plan.name,
        'plan_kind': plan.plan_kind,
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
        'feature_flags': plan.enabled_features(),
    })


@login_required
def get_company_subscription_api(request, company_id):
    # AUTHORIZATION: only staff or members of the company may read this.
    company = get_object_or_404(Company, pk=company_id)
    if not _can_view_company_subscription(request.user, company):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        sub = (
            Subscription.objects
            .filter(company=company, status='active')
            .select_related('plan')
            .order_by('-created_at')
            .first()
        )

        if sub:
            data = {
                'id': sub.id,
                'plan': sub.plan.name,
                'plan_kind': sub.plan.plan_kind,
                'plan_display': sub.plan.display_name,
                'start_date': sub.start_date.isoformat(),
                'end_date': sub.end_date.isoformat() if sub.end_date else None,
                'status': sub.status,
                'display_state': sub.display_state,
                'days_until_expiry': sub.days_until_expiry,
                'is_active': sub.is_active_subscription(),
                'has_workshop': sub.has_workshop_access,
                'features': sub.plan.enabled_features(),
            }
        else:
            # No active subscription — return an explicit null plan
            # instead of a fake 'free' entry.
            data = {
                'id': None,
                'plan': None,
                'plan_kind': None,
                'plan_display': None,
                'start_date': None,
                'end_date': None,
                'status': 'inactive',
                'display_state': 'inactive',
                'days_until_expiry': None,
                'is_active': False,
                'has_workshop': False,
                'features': {},
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
        'feature_flags': Plan.FEATURE_FLAGS,   # NEW: drives the form checkboxes
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