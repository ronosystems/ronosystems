from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from decimal import Decimal

from apps.companies.models import Company
from apps.companies.support_utils import get_active_company
from apps.company.models import Branch
from .models import LossReturn
from .forms import LossReturnForm


# ============================================
# PERMISSIONS
# ============================================

def is_admin_or_manager(user):
    """Full edit rights on unverified records."""
    return user.role in [
        'super_admin',
        'company_admin',
        'company_manager',
        'company_cashier',
        'stock_controller',
    ]


def can_verify(user):
    """Only company admins, super admins, and stock controllers can verify/un-verify."""
    return user.role in ['company_admin', 'super_admin']


def can_edit_loss(user, record):
    """
    Editing/deleting a loss is allowed only if:
      • User has admin/manager rights, AND
      • Record is not yet verified (locked)
    Returns (allowed: bool, reason: str)
    """
    if not is_admin_or_manager(user):
        return False, 'Only authorized users can edit losses.'
    if record.is_verified:
        return False, (
            f'This record ({record.reference}) is verified and locked. '
            'Un-verify it first to make changes.'
        )
    return True, ''


def get_user_branch(user):
    if hasattr(user, 'branch') and user.branch:
        return user.branch
    return None


def _resolve_branch(request, company, branch_id=None):
    """Return the branch the user is allowed to act on, or None."""
    user_branch = get_user_branch(request.user)

    if request.user.role in ['super_admin', 'company_admin']:
        if branch_id:
            return get_object_or_404(Branch, id=branch_id, company=company)
        return Branch.objects.filter(company=company, is_active=True).first()

    if not user_branch:
        return None

    if branch_id and int(branch_id) != user_branch.id:
        return None

    return user_branch


# ============================================
# LIST
# ============================================

@login_required
def loss_list(request, company_id=None, branch_id=None):
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    # ─────────────────────────────────────────
    # BASE QUERYSET — drives STAT CARDS (whole branch)
    # ─────────────────────────────────────────
    base_qs = LossReturn.objects.filter(company=company, branch=branch)

    # Grand totals (whole branch)
    total_amount = base_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_cost   = base_qs.aggregate(total=Sum('cost_amount'))['total'] or Decimal('0.00')
    record_count = base_qs.count()

    # ── Pending (unverified) ──
    pending_qs = base_qs.filter(is_verified=False)
    pending_count = pending_qs.count()
    pending_selling = pending_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    pending_cost    = pending_qs.aggregate(total=Sum('cost_amount'))['total'] or Decimal('0.00')
    pending_value = pending_selling + pending_cost

    # ── Verified (locked) ──
    verified_qs = base_qs.filter(is_verified=True)
    verified_count = verified_qs.count()
    verified_selling = verified_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    verified_cost    = verified_qs.aggregate(total=Sum('cost_amount'))['total'] or Decimal('0.00')
    verified_value = verified_selling + verified_cost

    # ─────────────────────────────────────────
    # FILTERED QUERYSET — drives the TABLE only
    # ─────────────────────────────────────────
    category   = request.GET.get('category')
    status     = request.GET.get('status')
    date_from  = request.GET.get('date_from')
    date_to    = request.GET.get('date_to')
    search     = request.GET.get('search')

    qs = base_qs.select_related('recorded_by', 'verified_by')

    if category:
        qs = qs.filter(category=category)
    if status == 'verified':
        qs = qs.filter(is_verified=True)
    elif status == 'pending':
        qs = qs.filter(is_verified=False)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if search:
        qs = qs.filter(
            Q(reference__icontains=search) |
            Q(product_name__icontains=search) |
            Q(customer_name__icontains=search) |
            Q(description__icontains=search)
        )

    qs = qs.order_by('-created_at')

    # ─────────────────────────────────────────
    # PAGINATION
    # ─────────────────────────────────────────
    try:
        per_page = int(request.GET.get('per_page', 25))
    except (TypeError, ValueError):
        per_page = 25
    if per_page not in (10, 25, 50, 100):
        per_page = 25

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    query = request.GET.copy()
    query.pop('page', None)

    context = {
        'company': company,
        'branch': branch,

        # Table
        'records': page_obj,
        'paginator': paginator,
        'per_page': per_page,
        'querystring': query.urlencode(),

        # Filter state
        'category_choices': LossReturn.CATEGORY_CHOICES,
        'selected_category': category,
        'selected_status': status,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,

        # ── GRAND TOTALS ──
        'total_amount': total_amount,
        'total_cost': total_cost,
        'record_count': record_count,

        # ── PENDING (unverified) ──
        'pending_count':   pending_count,
        'pending_selling': pending_selling,
        'pending_cost':    pending_cost,
        'pending_value':   pending_value,

        # ── VERIFIED (locked) ──
        'verified_count':   verified_count,
        'verified_selling': verified_selling,
        'verified_cost':    verified_cost,
        'verified_value':   verified_value,

        # Permissions
        'is_admin': is_admin_or_manager(request.user),
        'can_verify': can_verify(request.user),
    }
    return render(request, 'losses/loss_list.html', context)


# ============================================
# CREATE
# ============================================

@login_required
def loss_create(request, company_id=None, branch_id=None):
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    if not is_admin_or_manager(request.user):
        messages.error(request, 'Only admins and managers can record losses.')
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    if request.method == 'POST':
        form = LossReturnForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.company = company
            record.branch = branch
            record.recorded_by = request.user

            # Zero out the unused amount side for cleanliness
            if record.is_loss_style:
                record.amount = Decimal('0.00')
            else:
                record.cost_amount = Decimal('0.00')

            record.save()
            messages.success(
                request,
                f'✅ {record.get_category_display()} recorded — {record.reference} '
                f'(pending verification).'
            )
            return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        # Prefill the barcode when the list page redirects with ?barcode=...
        initial = {'quantity': 1}
        barcode = (request.GET.get('barcode') or '').strip()
        if barcode:
            initial['sale_barcode'] = barcode
        form = LossReturnForm(initial=initial)

    context = {
        'company': company,
        'branch': branch,
        'form': form,
        'is_edit': False,
        'category_choices': LossReturn.CATEGORY_CHOICES,
        'refund_type_choices': LossReturn.REFUND_TYPE_CHOICES,
        'return_style_categories': LossReturn.RETURN_STYLE_CATEGORIES,
        'loss_style_categories': LossReturn.LOSS_STYLE_CATEGORIES,
        'can_verify': can_verify(request.user),
    }
    return render(request, 'losses/loss_form.html', context)


# ============================================
# DETAIL
# ============================================

@login_required
def loss_detail(request, company_id=None, branch_id=None, pk=None):
    """Read-only detail view for a single loss/return record."""
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    record = get_object_or_404(
        LossReturn.objects.select_related('recorded_by', 'verified_by'),
        id=pk,
        company=company,
        branch=branch,
    )

    context = {
        'company': company,
        'branch': branch,
        'record': record,
        'is_admin': is_admin_or_manager(request.user),
        'can_verify': can_verify(request.user),
    }
    return render(request, 'losses/loss_detail.html', context)


# ============================================
# EDIT
# ============================================

@login_required
def loss_edit(request, company_id=None, branch_id=None, pk=None):
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    record = get_object_or_404(LossReturn, id=pk, company=company, branch=branch)

    # ── Lock check (verified records cannot be edited) ──
    allowed, reason = can_edit_loss(request.user, record)
    if not allowed:
        messages.error(request, reason)
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    if request.method == 'POST':
        form = LossReturnForm(request.POST, instance=record)
        if form.is_valid():
            updated = form.save(commit=False)
            if updated.is_loss_style:
                updated.amount = Decimal('0.00')
            else:
                updated.cost_amount = Decimal('0.00')
            updated.save()
            messages.success(request, f'✅ {record.reference} updated.')
            return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        # Load the record's existing data, but if the caller supplied
        # ?barcode=..., overlay it as the initial value for that field.
        initial = {}
        barcode = (request.GET.get('barcode') or '').strip()
        if barcode:
            initial['sale_barcode'] = barcode
        form = LossReturnForm(instance=record, initial=initial)

    context = {
        'company': company,
        'branch': branch,
        'form': form,
        'record': record,
        'is_edit': True,
        'category_choices': LossReturn.CATEGORY_CHOICES,
        'refund_type_choices': LossReturn.REFUND_TYPE_CHOICES,
        'return_style_categories': LossReturn.RETURN_STYLE_CATEGORIES,
        'loss_style_categories': LossReturn.LOSS_STYLE_CATEGORIES,
        'can_verify': can_verify(request.user),
    }
    return render(request, 'losses/loss_form.html', context)


# ============================================
# DELETE
# ============================================

@login_required
def loss_delete(request, company_id=None, branch_id=None, pk=None):
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    record = get_object_or_404(LossReturn, id=pk, company=company, branch=branch)

    # ── Lock check (verified records cannot be deleted) ──
    allowed, reason = can_edit_loss(request.user, record)
    if not allowed:
        messages.error(request, reason)
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    if request.method == 'POST':
        ref = record.reference
        record.delete()
        messages.success(request, f'🗑️ {ref} deleted.')
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    context = {
        'company': company,
        'branch': branch,
        'record': record,
    }
    return render(request, 'losses/loss_confirm_delete.html', context)


# ============================================
# VERIFY / UN-VERIFY
# ============================================

@login_required
def loss_verify(request, company_id=None, branch_id=None, pk=None):
    """Company admin / stock controller marks a record as verified (locked)."""
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    if not can_verify(request.user):
        messages.error(
            request,
            'Only company admins and stock controllers can verify records.'
        )
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    record = get_object_or_404(LossReturn, id=pk, company=company, branch=branch)

    if request.method == 'POST':
        if record.is_verified:
            messages.info(request, f'{record.reference} is already verified.')
        else:
            record.is_verified = True
            record.verified_by = request.user
            record.verified_at = timezone.now()
            record.verification_notes = request.POST.get('verification_notes', '').strip()
            record.save(update_fields=[
                'is_verified', 'verified_by', 'verified_at', 'verification_notes',
            ])
            messages.success(
                request,
                f'✅ {record.reference} verified and locked. It can no longer be edited.'
            )
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    context = {
        'company': company,
        'branch': branch,
        'record': record,
        'action': 'verify',
    }
    return render(request, 'losses/loss_verify.html', context)


@login_required
def loss_unverify(request, company_id=None, branch_id=None, pk=None):
    """Company admin / stock controller removes verification, unlocking the record."""
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    branch = _resolve_branch(request, company, branch_id)
    if not branch:
        messages.error(request, 'No branch available or you do not have access.')
        return redirect('/dashboard/')

    if not can_verify(request.user):
        messages.error(
            request,
            'Only company admins and stock controllers can un-verify records.'
        )
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    record = get_object_or_404(LossReturn, id=pk, company=company, branch=branch)

    if request.method == 'POST':
        if not record.is_verified:
            messages.info(request, f'{record.reference} is not verified.')
        else:
            record.is_verified = False
            record.verified_by = None
            record.verified_at = None
            record.save(update_fields=['is_verified', 'verified_by', 'verified_at'])
            messages.warning(
                request,
                f'⚠️ Verification for {record.reference} removed. The record is editable again.'
            )
        return redirect('losses:loss_list', company_id=company.id, branch_id=branch.id)

    context = {
        'company': company,
        'branch': branch,
        'record': record,
        'action': 'unverify',
    }
    return render(request, 'losses/loss_verify.html', context)


# ============================================
# API — Auto-fill cost price from product
# ============================================

@login_required
def api_product_lookup(request):
    """
    Look up a product by name/code and return its purchase price.
    Used to auto-fill cost_amount for damage / shrinkage.

    Query params:
      ?q=<search>       → list matching products
      ?name=<exact>     → single product purchase price
    """
    company, _ = get_active_company(request)
    if not company:
        return JsonResponse({'error': 'No company'}, status=400)

    from apps.epa_shop.models import Phone, Electronic, Accessory

    q = request.GET.get('q', '').strip()
    exact = request.GET.get('name', '').strip()

    # Single lookup
    if exact:
        for Model in (Phone, Electronic, Accessory):
            obj = Model.objects.filter(
                company=company, name__iexact=exact, is_active=True
            ).first()
            if obj:
                return JsonResponse({
                    'found': True,
                    'name': obj.name,
                    'model': getattr(obj, 'model', '') or getattr(obj, 'model_number', ''),
                    'purchase_price': float(obj.purchase_price),
                    'selling_price': float(obj.selling_price),
                })
        return JsonResponse({'found': False})

    # Search
    results = []
    if q:
        for Model in (Phone, Electronic, Accessory):
            for obj in Model.objects.filter(
                company=company, name__icontains=q, is_active=True
            )[:5]:
                results.append({
                    'name': obj.name,
                    'model': getattr(obj, 'model', '') or getattr(obj, 'model_number', ''),
                    'purchase_price': float(obj.purchase_price),
                    'selling_price': float(obj.selling_price),
                })

    return JsonResponse({'results': results})


# ============================================
# API — Look up a Sale by barcode (for returns form)
# ============================================

@login_required
def api_sale_lookup(request):
    """
    Look up a sale by its barcode_number and return customer + items
    so the Loss/Return form can prefill itself.

    Query params:
      ?barcode=BAR-20261010-000001

    Response (found=True):
      {
        "found": true,
        "sale": {
          "id": <int>,
          "company_sale_id": "FIE-000001",
          "barcode_number": "BAR-...",
          "customer_name": "...",
          "customer_phone": "...",
          "customer_email": "...",
          "customer_id": "...",
          "sold_by": "Full Name / username",
          "net_amount": 123.45,
          "total_amount": 123.45,
          "tax": 0.00,
          "payment_method": "cash",
          "payment_status": "paid",
          "sale_date": "2026-10-10T12:34:56+03:00",
          "branch_id": 1,
          "branch_name": "Main",
          "items": [
            {
              "name": "...",
              "sku": "...",
              "quantity": 1,
              "unit_price": 123.45,
              "total_price": 123.45,
              "unit_identifier": "..."
            }
          ]
        }
      }
    """
    company, _ = get_active_company(request)
    if not company:
        return JsonResponse({'found': False, 'error': 'No company'}, status=400)

    code = (request.GET.get('barcode') or '').strip()
    if not code:
        return JsonResponse({'found': False, 'error': 'No barcode provided'}, status=400)

    from apps.epa_shop.models import Sale  # adjust import path if different

    sale = (
        Sale.objects
        .filter(company=company, barcode_number__iexact=code)
        .select_related('branch', 'customer', 'sold_by')
        .prefetch_related('items', 'items__unit')
        .first()
    )

    if not sale:
        return JsonResponse({'found': False, 'error': f'No sale found for "{code}"'})

    # ── Sold-by display name ──
    sold_by_name = '—'
    if sale.sold_by:
        full_name = ''
        try:
            full_name = sale.sold_by.get_full_name() or ''
        except Exception:
            full_name = ''
        sold_by_name = full_name or getattr(sale.sold_by, 'username', '') or '—'

    # ── Customer national ID (from linked Customer record) ──
    customer_id = ''
    if sale.customer:
        customer_id = getattr(sale.customer, 'id_number', '') or ''

    # ── Items list ──
    items = []
    for it in sale.items.all():
        items.append({
            'name': it.item_name,
            'sku': it.item_sku or '',
            'quantity': it.quantity,
            'unit_price': float(it.unit_price),
            'total_price': float(it.total_price),
            'unit_identifier': it.unit.identifier if it.unit else '',
        })

    return JsonResponse({
        'found': True,
        'sale': {
            'id': sale.id,
            'company_sale_id': sale.company_sale_id,
            'barcode_number': sale.barcode_number,
            # 👇 NEW — short display versions
            'short_sale_id': sale.short_sale_id,
            'short_barcode': sale.short_barcode,

            # ── Customer ──
            'customer_name': sale.customer_name,
            'customer_phone': sale.customer_phone,
            'customer_email': sale.customer_email,
            'customer_id': customer_id,

            # ── Sale meta ──
            'sold_by': sold_by_name,
            'net_amount': float(sale.net_amount),
            'total_amount': float(sale.total_amount),
            'tax': float(sale.tax),
            'payment_method': sale.payment_method,
            'payment_status': sale.payment_status,
            'sale_date': sale.sale_date.isoformat(),

            'branch_id': sale.branch_id,
            'branch_name': sale.branch.name if sale.branch else '',

            'items': items,
        },
    })


# ============================================
# BRANCH-OPTIONAL ENTRY
# ============================================

@login_required
def loss_list_entry(request, company_id=None):
    """
    Branch-optional entry point for the losses list.

    - Users with a branch → routed to their own branch.
    - Admins / managers / stock_controllers without a branch → routed to
      the first active branch of the company.
    - No branch available at all → friendly message, back to dashboard.
    """
    company, _ = get_active_company(request)
    if not company:
        messages.warning(request, 'No company assigned.')
        return redirect('/dashboard/')

    user_branch = get_user_branch(request.user)

    roles_with_any_branch = [
        'super_admin',
        'company_admin',
        'company_manager',
        'stock_controller',
    ]

    if not user_branch and request.user.role in roles_with_any_branch:
        user_branch = Branch.objects.filter(
            company=company, is_active=True
        ).order_by('name').first()

    if not user_branch:
        messages.warning(
            request,
            'You are not assigned to a branch, and no branches exist yet. '
            'Please create a branch first.'
        )
        return redirect('/dashboard/')

    return redirect(
        'losses:loss_list',
        company_id=company.id,
        branch_id=user_branch.id,
    )