from datetime import timedelta
from urllib.parse import parse_qs

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Visit


# ============================================
# PERMISSION HELPER
# ============================================

def _can_view_visits(user):
    return user.is_authenticated and user.role in ['super_admin', 'company_admin']


# ============================================
# FILTER APPLICATION (shared by dashboard + erase-all)
# ============================================

def _apply_filters(qs, params):
    """
    Apply the dashboard's filter set to a queryset.

    `params` is a dict-like (QueryDict or dict from parse_qs) with keys:
      range, date_from, date_to, page_q, search

    Returns the filtered queryset.
    """
    range_key = (params.get('range') or ['today'])[0] if isinstance(params.get('range'), list) else (params.get('range') or 'today')
    date_from = (params.get('date_from') or [''])[0] if isinstance(params.get('date_from'), list) else (params.get('date_from') or '')
    date_to   = (params.get('date_to') or [''])[0] if isinstance(params.get('date_to'), list) else (params.get('date_to') or '')
    page_q    = (params.get('page_q') or [''])[0] if isinstance(params.get('page_q'), list) else (params.get('page_q') or '')
    search    = (params.get('search') or [''])[0] if isinstance(params.get('search'), list) else (params.get('search') or '')

    range_key = (range_key or '').strip()
    date_from = (date_from or '').strip()
    date_to   = (date_to or '').strip()
    page_q    = (page_q or '').strip()
    search    = (search or '').strip()

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_key == 'today':
        qs = qs.filter(created_at__gte=today_start)
    elif range_key == '7d':
        qs = qs.filter(created_at__gte=now - timedelta(days=7))
    elif range_key == '30d':
        qs = qs.filter(created_at__gte=now - timedelta(days=30))
    elif range_key == 'custom' and (date_from or date_to):
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
    else:
        # Default to today
        qs = qs.filter(created_at__gte=today_start)

    if page_q:
        qs = qs.filter(page__icontains=page_q)

    if search:
        qs = qs.filter(
            Q(ip_address__icontains=search) |
            Q(city__icontains=search) |
            Q(country__icontains=search) |
            Q(user_name__icontains=search)
        )

    return qs


# ============================================
# DASHBOARD
# ============================================

@login_required
def visit_dashboard(request):
    if not _can_view_visits(request.user):
        return redirect('/dashboard/')

    range_key = request.GET.get('range', 'today')
    date_from = request.GET.get('date_from', '').strip()
    date_to   = request.GET.get('date_to', '').strip()
    page_q    = request.GET.get('page_q', '').strip()
    search    = request.GET.get('search', '').strip()

    # Base queryset
    qs = Visit.objects.all()

    # Apply filters via the shared helper
    qs = _apply_filters(qs, {
        'range':     [range_key],
        'date_from': [date_from],
        'date_to':   [date_to],
        'page_q':    [page_q],
        'search':    [search],
    })

    # ── Stats ──
    total_visits = qs.count()
    unread_count = qs.filter(read_at__isnull=True).count()
    unique_ips = (
        qs.exclude(ip_address__isnull=True)
          .values('ip_address')
          .distinct()
          .count()
    )

    top_page_row = (
        qs.values('page')
          .annotate(c=Count('id'))
          .order_by('-c')
          .first()
    )
    top_page = top_page_row['page'] if top_page_row else '—'
    top_page_count = top_page_row['c'] if top_page_row else 0

    top_city_row = (
        qs.exclude(city='')
          .values('city', 'country')
          .annotate(c=Count('id'))
          .order_by('-c')
          .first()
    )
    top_city = f"{top_city_row['city']}, {top_city_row['country']}" if top_city_row else '—'
    top_city_count = top_city_row['c'] if top_city_row else 0

    # ── Pagination ──
    qs = qs.order_by('-created_at')
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Querystring without `page`
    qp = request.GET.copy()
    qp.pop('page', None)

    # Distinct pages for the autocomplete
    page_options = (
        Visit.objects.values_list('page', flat=True)
             .distinct()
             .order_by('page')[:200]
    )

    context = {
        'records': page_obj,
        'paginator': paginator,
        'querystring': qp.urlencode(),

        # Filter state
        'range_key': range_key,
        'date_from': date_from,
        'date_to': date_to,
        'page_q': page_q,
        'search': search,
        'page_options': page_options,

        # Stats
        'total_visits': total_visits,
        'unread_count': unread_count,
        'unique_ips': unique_ips,
        'top_page': top_page,
        'top_page_count': top_page_count,
        'top_city': top_city,
        'top_city_count': top_city_count,
    }
    return render(request, 'analytics/visit_dashboard.html', context)


# ============================================
# MARK AS READ
# ============================================

@login_required
@require_POST
def mark_visits_read(request):
    """
    Mark visits as read.

    Modes:
      - ids=[1,2,3]   → mark only those rows
      - (no ids)      → mark ALL unread visits in the DB
    """
    if not _can_view_visits(request.user):
        return JsonResponse({'ok': False, 'error': 'Permission denied'}, status=403)

    ids_raw = request.POST.getlist('ids')
    ids = []
    for raw in ids_raw:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            pass

    qs = Visit.objects.filter(read_at__isnull=True)
    if ids:
        qs = qs.filter(id__in=ids)

    updated = qs.update(read_at=timezone.now())
    return JsonResponse({'ok': True, 'updated': updated})


# ============================================
# ERASE
# ============================================

@login_required
@require_POST
def erase_visits(request):
    """
    Permanently delete visits.

    Modes:
      - ids=[1,2,3]              → delete those rows
      - all=1                    → delete ALL visits (dangerous)
      - all=1 & filters=<qs>     → delete only rows matching the current
                                   dashboard filters (querystring)
    """
    if not _can_view_visits(request.user):
        return JsonResponse({'ok': False, 'error': 'Permission denied'}, status=403)

    ids_raw    = request.POST.getlist('ids')
    erase_all  = request.POST.get('all') == '1'
    filters_qs = request.POST.get('filters', '').strip()

    qs = Visit.objects.all()

    # ── Case 1: specific IDs ──
    if ids_raw:
        ids = []
        for raw in ids_raw:
            try:
                ids.append(int(raw))
            except (TypeError, ValueError):
                pass
        if not ids:
            return JsonResponse({'ok': False, 'error': 'No valid IDs provided'}, status=400)
        qs = qs.filter(id__in=ids)

    # ── Case 2: all in view (filter-aware) ──
    elif erase_all:
        if filters_qs:
            params = parse_qs(filters_qs)
            qs = _apply_filters(qs, params)
        # else: no filters → delete everything (full wipe)

    # ── Case 3: nothing specified ──
    else:
        return JsonResponse({'ok': False, 'error': 'No rows selected'}, status=400)

    deleted, _ = qs.delete()
    return JsonResponse({'ok': True, 'deleted': deleted})