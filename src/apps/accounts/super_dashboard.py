# apps/company/dashboard_views.py (or wherever this view lives)

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q

from apps.companies.models import Company
from apps.plans.models import Plan, Subscription
from apps.accounts.models import User


@login_required
def super_admin_dashboard(request):
    """
    Super admin dashboard — platform-level view only.

    Shows YOUR business metrics:
      - How many tenants you have
      - How much YOU earn monthly (MRR)
      - Renewals coming up
      - Growth trends

    Does NOT show tenants' internal sales/revenue — that's their data.
    """
    if request.user.role != 'super_admin' and not request.user.is_superuser:
        messages.warning(request, 'Access denied.')
        return redirect('/dashboard/')

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    seven_days_from_now = now + timedelta(days=7)

    # ============================================
    # TOP-LEVEL KPIs — your business
    # ============================================
    total_companies = Company.objects.count()
    active_companies = Company.objects.filter(is_active=True, status='active').count()
    suspended_companies = Company.objects.filter(status='suspended').count()

    total_users = User.objects.filter(is_active=True).count()
    new_users_30d = User.objects.filter(created_at__gte=thirty_days_ago).count()

    # ============================================
    # SUBSCRIPTION HEALTH
    # ============================================
    active_subs = Subscription.objects.filter(
        status='active',
        end_date__gt=now,
    )
    expiring_soon = Subscription.objects.filter(
        status='active',
        end_date__gte=now,
        end_date__lte=seven_days_from_now,
    )
    # Only count TRULY expired (avoid double-counting with active filter)
    expired_subs = Subscription.objects.filter(
        Q(status='expired') |
        Q(status='active', end_date__lt=now)
    )

    # ============================================
    # MONTHLY RECURRING REVENUE (MRR) — your money
    # ============================================
    # Sum the price of each ACTIVE company's current plan (monthly-normalized).
    # Uses Company.plan (single source of truth per company), not raw subscription rows.
    mrr = 0
    mrr_by_plan = {}

    for company in Company.objects.filter(is_active=True, status='active').select_related('plan'):
        plan = company.current_plan
        if not plan or not plan.price:
            continue

        # Normalize to monthly
        if plan.billing_cycle == 'monthly':
            monthly_amount = float(plan.price)
        elif plan.billing_cycle == 'yearly':
            monthly_amount = float(plan.price) / 12
        elif plan.billing_cycle == 'lifetime':
            monthly_amount = 0  # no recurring revenue
        else:
            monthly_amount = float(plan.price)

        mrr += monthly_amount

        # Track per-plan totals
        plan_name = plan.display_name
        if plan_name not in mrr_by_plan:
            mrr_by_plan[plan_name] = {
                'plan': plan,
                'companies': 0,
                'monthly_total': 0,
            }
        mrr_by_plan[plan_name]['companies'] += 1
        mrr_by_plan[plan_name]['monthly_total'] += monthly_amount

    # Yearly forecast (simple: MRR × 12)
    yearly_forecast = mrr * 12

    # Average revenue per company
    arpc = (mrr / active_companies) if active_companies else 0

    # ============================================
    # RECENT COMPANIES (last 5)
    # ============================================
    recent_companies = (
        Company.objects
        .select_related('business_type', 'plan')
        .order_by('-created_at')[:5]
    )

    # ============================================
    # COMPANIES EXPIRING SOON (need attention)
    # ============================================
    attention_companies = []
    for sub in expiring_soon.select_related('company', 'plan').order_by('end_date')[:5]:
        days_left = (sub.end_date - now).days if sub.end_date else None
        attention_companies.append({
            'company': sub.company,
            'plan': sub.plan,
            'days_left': days_left,
            'end_date': sub.end_date,
            'renewal_amount': sub.plan.price if sub.plan else 0,
        })

    # ============================================
    # PLAN DISTRIBUTION (companies per plan)
    # ============================================
    plan_distribution = []
    for plan in Plan.objects.filter(is_active=True).order_by('order'):
        count = Company.objects.filter(plan=plan, is_active=True).count()
        plan_distribution.append({
            'plan': plan,
            'count': count,
            'mrr': mrr_by_plan.get(plan.display_name, {}).get('monthly_total', 0),
        })

    # ============================================
    # BUSINESS TYPE BREAKDOWN
    # ============================================
    business_type_breakdown = (
        Company.objects
        .values('business_type__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )

    # ============================================
    # RECENT SIGNUPS (last 30 days)
    # ============================================
    recent_signups = (
        Company.objects
        .filter(created_at__gte=thirty_days_ago)
        .select_related('business_type', 'plan')
        .order_by('-created_at')[:5]
    )

    # ============================================
    # PLATFORM HEALTH INDICATORS
    # ============================================
    health = {
        'active_rate': round((active_companies / total_companies * 100), 1) if total_companies else 0,
        'suspended_rate': round((suspended_companies / total_companies * 100), 1) if total_companies else 0,
        'growth_rate_30d': new_users_30d,
        'arpc': round(arpc, 2),
    }

    context = {
        'stats': {
            # Your tenants
            'total_companies': total_companies,
            'active_companies': active_companies,
            'suspended_companies': suspended_companies,
            'total_users': total_users,
            'new_users_30d': new_users_30d,

            # Your subscriptions
            'active_subscriptions': active_subs.count(),
            'expiring_soon': expiring_soon.count(),
            'expired_subscriptions': expired_subs.count(),

            # Your money
            'mrr': round(mrr, 2),
            'yearly_forecast': round(yearly_forecast, 2),
            'arpc': round(arpc, 2),
        },
        'mrr_by_plan': list(mrr_by_plan.values()),
        'recent_companies': recent_companies,
        'recent_signups': recent_signups,
        'attention_companies': attention_companies,
        'plan_distribution': plan_distribution,
        'business_type_breakdown': business_type_breakdown,
        'health': health,
    }
    return render(request, 'superadmin/super_dashboard.html', context)