# apps/workshop/views.py

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import (
    Case,
    Count,
    IntegerField,
    Q,
    Sum,
    When,
)
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.company.models import Branch

from .forms import (
    JobMaterialForm,
    JobNoteForm,
    JobPaymentForm,
    JobStatusForm,
    PayoutEditForm,
    PayoutPayForm,
    TechnicianRateForm,
    WorkshopCustomerForm,
    WorkshopJobForm,
)
from .models import (
    JobMaterial,
    JobPayment,
    JobNote,
    RepairCategory,
    TechnicianPayout,
    TechnicianRate,
    WorkshopCustomer,
    WorkshopJob,
)
from .permissions import (
    WORKSHOP_ROLES,
    user_has_workshop_access,
    workshop_required,
)


# ================================================================
# CONSTANTS
# ================================================================

OPEN_STATUSES = [
    'received',
    'diagnosed',
    'awaiting_approval',
    'approved',
    'in_progress',
    'on_hold',
    'completed',
]

CLOSED_STATUSES = ['delivered', 'cancelled', 'unrepairable']


# ================================================================
# HELPERS
# ================================================================

def _week_start(d):
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def _company_or_404(request):
    """Return the request user's company (or None)."""
    return getattr(request.user, 'company', None)


def _scope_jobs_to_user(request):
    """
    Base queryset of jobs visible to request.user.

    - Super admin:      all jobs (optionally filtered by ?company=)
    - Company admin:    all jobs for their company
    - Manager:          all jobs for their company
    - Stock controller: all jobs for their company
    - Technician:       assigned jobs + unassigned queue
    """
    user = request.user
    qs = WorkshopJob.objects.select_related(
        'customer', 'assigned_technician', 'branch', 'company',
    )

    if user.role == 'super_admin':
        company_id = request.GET.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    company = getattr(user, 'company', None)
    if not company:
        return qs.none()

    qs = qs.filter(company=company)

    if user.role == 'company_technician':
        qs = qs.filter(
            Q(assigned_technician=user) |
            Q(assigned_technician__isnull=True)
        )

    return qs


def _payout_scope(request):
    """Base queryset of payouts visible to request.user."""
    user = request.user
    qs = TechnicianPayout.objects.select_related(
        'job', 'job__company', 'technician', 'paid_by',
    )

    if user.role == 'super_admin':
        return qs

    company = getattr(user, 'company', None)
    if not company:
        return qs.none()

    qs = qs.filter(job__company=company)

    if user.role == 'company_technician':
        qs = qs.filter(technician=user)

    return qs


def _can_edit_job(user, job):
    if user.role in ('super_admin', 'company_admin', 'company_manager'):
        return True
    if user.role == 'company_technician':
        return (
            job.assigned_technician_id == user.id
            or job.assigned_technician_id is None
        )
    return False


def _can_pay_payouts(user):
    return user.role in ('super_admin', 'company_admin')


def _can_manage_rates(user):
    return user.role in ('super_admin', 'company_admin')


def _paginate(request, qs, default_per_page=25):
    """Shared pagination helper. Returns (page_obj, per_page)."""
    try:
        per_page = int(request.GET.get('per_page', default_per_page))
    except (TypeError, ValueError):
        per_page = default_per_page
    if per_page not in (10, 25, 50, 100):
        per_page = default_per_page
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return page_obj, per_page


# ================================================================
# DASHBOARD
# ================================================================

@login_required
@workshop_required
def dashboard(request):
    """
    Workshop landing page.
    Admin view:    branch selector, period stats, top technicians, last 5 jobs
    Technician view: their own period stats, last 5 jobs
    """
    user = request.user
    today = timezone.now().date()
    is_technician = user.role == 'company_technician'
    is_admin_view = not is_technician

    # ---------- Base scope ----------
    base_qs = WorkshopJob.objects.all()
    if user.role == 'super_admin':
        company_id = request.GET.get('company')
        if company_id:
            base_qs = base_qs.filter(company_id=company_id)
    else:
        base_qs = (
            base_qs.filter(company=user.company)
            if user.company_id
            else base_qs.none()
        )

    if is_technician:
        base_qs = base_qs.filter(assigned_technician=user)

    # ---------- Branch selector (admins only) ----------
    selected_branch = None
    branches = Branch.objects.none()
    if is_admin_view:
        if user.role == 'super_admin':
            branches = Branch.objects.all().order_by('name')
        elif user.company_id:
            branches = Branch.objects.filter(company=user.company).order_by('name')

        branch_id = request.GET.get('branch')
        if branch_id:
            selected_branch = branches.filter(id=branch_id).first()
            if selected_branch:
                base_qs = base_qs.filter(branch=selected_branch)

    # ---------- Period stats ----------
    open_filter = ~Q(status__in=CLOSED_STATUSES)
    completed_filter = Q(status__in=['completed', 'delivered'])

    def period_stats(qs):
        agg = qs.aggregate(
            total=Count('id'),
            open=Count('id', filter=open_filter),
            completed=Count('id', filter=completed_filter),
        )
        return {
            'total': agg['total'] or 0,
            'open': agg['open'] or 0,
            'completed': agg['completed'] or 0,
        }

    year_start = today.replace(month=1, day=1)
    month_start = today.replace(day=1)
    week_start = _week_start(today)

    stats = {
        'year': period_stats(base_qs.filter(received_at__date__gte=year_start)),
        'month': period_stats(base_qs.filter(received_at__date__gte=month_start)),
        'week': period_stats(base_qs.filter(received_at__date__gte=week_start)),
        'today': period_stats(base_qs.filter(received_at__date=today)),
    }

    # ---------- Top technicians (admin only) ----------
    top_technicians = []
    if is_admin_view:
        if user.role == 'super_admin':
            tech_qs = User.objects.filter(role='company_technician')
        elif user.company_id:
            tech_qs = User.objects.filter(
                role='company_technician',
                company=user.company,
            )
        else:
            tech_qs = User.objects.none()

        year_scope = base_qs.filter(received_at__date__gte=year_start)
        counts = dict(
            year_scope
            .values_list('assigned_technician')
            .annotate(c=Count('id'))
            .values_list('assigned_technician', 'c')
        )
        tech_list = list(tech_qs)
        for t in tech_list:
            t.job_count = counts.get(t.id, 0)
        tech_list.sort(key=lambda t: t.job_count, reverse=True)
        top_technicians = tech_list[:10]

    # ---------- Pending payouts ----------
    pending_payouts_qs = TechnicianPayout.objects.filter(
        status='pending',
        job__in=base_qs,
    )
    pending_payouts_count = pending_payouts_qs.count()
    pending_payouts_total = (
        pending_payouts_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    )

    # ---------- Recent jobs ----------
    recent_jobs = (
        base_qs
        .select_related('customer', 'assigned_technician')
        .order_by('-created_at')[:5]
    )

    context = {
        'page_title': 'Workshop',
        'page_subtitle': 'Repairs overview',
        'is_technician_view': is_technician,
        'selected_branch': selected_branch,
        'branches': branches,
        'stats': stats,
        'top_technicians': top_technicians,
        'pending_payouts_count': pending_payouts_count,
        'pending_payouts_total': pending_payouts_total,
        'recent_jobs': recent_jobs,
    }
    return render(request, 'workshop/dashboard.html', context)


# ================================================================
# MY WORK
# ================================================================

@login_required
@workshop_required
def my_work(request):
    """
    Technician's own job queue.
    Shows jobs assigned to the current user. Optionally includes
    unassigned jobs so they can pick up work.
    """
    user = request.user

    base_qs = WorkshopJob.objects.select_related(
        'customer', 'branch', 'company', 'assigned_technician',
    )
    if user.company_id:
        base_qs = base_qs.filter(company_id=user.company_id)
    else:
        base_qs = base_qs.none()

    include_unassigned = request.GET.get('include_unassigned') == '1'
    if include_unassigned:
        qs = base_qs.filter(
            Q(assigned_technician=user) | Q(assigned_technician__isnull=True)
        )
    else:
        qs = base_qs.filter(assigned_technician=user)

    status_filter = request.GET.get('status', '').strip()
    search = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(job_number__icontains=search) |
            Q(device_name__icontains=search) |
            Q(device_serial__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search)
        )

    qs = qs.annotate(
        sort_open=Case(
            When(status__in=OPEN_STATUSES, then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by('sort_open', '-created_at')

    open_count = qs.filter(status__in=OPEN_STATUSES).count()
    in_progress_count = qs.filter(status='in_progress').count()
    completed_count = qs.filter(status='completed').count()
    total_count = qs.count()

    page_obj, per_page = _paginate(request, qs)

    context = {
        'page_title': 'My Work',
        'page_subtitle': 'Jobs assigned to me',
        'jobs': page_obj,
        'per_page': per_page,
        'total_count': total_count,
        'status_filter': status_filter,
        'search': search,
        'include_unassigned': include_unassigned,
        'status_choices': WorkshopJob.STATUS_CHOICES,
        'open_count': open_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
    }
    return render(request, 'workshop/my_work.html', context)


# ================================================================
# JOBS
# ================================================================

@login_required
@workshop_required
def job_list(request):
    """Filterable list of all jobs."""
    qs = _scope_jobs_to_user(request)

    status_filter = request.GET.get('status', '').strip()
    category_filter = request.GET.get('category', '').strip()
    technician_filter = request.GET.get('technician', '').strip()
    search = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if category_filter:
        qs = qs.filter(repair_category=category_filter)
    if technician_filter:
        qs = qs.filter(assigned_technician_id=technician_filter)
    if search:
        qs = qs.filter(
            Q(job_number__icontains=search) |
            Q(device_name__icontains=search) |
            Q(device_serial__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search)
        )

    qs = qs.order_by('-created_at')

    # Counts (based on the pre-paginated queryset)
    total_count = qs.count()
    open_count = qs.filter(status__in=OPEN_STATUSES).count()
    in_progress_count = qs.filter(status='in_progress').count()
    completed_count = qs.filter(status='completed').count()

    page_obj, per_page = _paginate(request, qs)

    # Technician dropdown
    if request.user.role == 'super_admin':
        techs = User.objects.filter(role='company_technician')
    elif request.user.company:
        techs = User.objects.filter(
            company=request.user.company,
            role='company_technician',
        )
    else:
        techs = User.objects.none()

    context = {
        'page_title': 'Jobs',
        'page_subtitle': 'All repair jobs',
        'jobs': page_obj,
        'per_page': per_page,
        'total_count': total_count,
        'open_count': open_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'technician_filter': technician_filter,
        'search': search,
        'status_choices': WorkshopJob.STATUS_CHOICES,
        'category_choices': WorkshopJob.REPAIR_CATEGORIES,
        'technicians': techs,
    }
    return render(request, 'workshop/job_list.html', context)


@login_required
@workshop_required
def job_detail(request, pk):
    """Job detail with materials, payments, notes, and payout."""
    job = get_object_or_404(_scope_jobs_to_user(request), pk=pk)

    context = {
        'page_title': f'Job {job.job_number}',
        'page_subtitle': job.device_name,
        'job': job,
        'materials': job.materials.select_related('added_by').all(),
        'payments': job.payments.select_related('received_by').all(),
        'notes': job.notes.select_related('created_by').all(),
        'payout': getattr(job, 'technician_payout', None),
        'can_edit': _can_edit_job(request.user, job),
        'can_pay': _can_pay_payouts(request.user),
        'status_choices': WorkshopJob.STATUS_CHOICES,
    }
    return render(request, 'workshop/job_detail.html', context)


@login_required
@workshop_required
def job_create(request):
    """Create a new job."""
    company = _company_or_404(request)
    if not company and request.user.role != 'super_admin':
        messages.error(request, 'You must belong to a company to create jobs.')
        return redirect('workshop:dashboard')

    if request.method == 'POST':
        form = WorkshopJobForm(
            request.POST,
            company=company,
            user=request.user,
        )
        if form.is_valid():
            job = form.save(commit=False)
            job.company = company or form.cleaned_data.get('company')
            job.received_by = request.user
            job.save()
            messages.success(request, f'Job {job.job_number} created.')
            return redirect('workshop:job-detail', pk=job.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        # Prefill customer from ?customer=<id>
        initial = {}
        customer_id = request.GET.get('customer')
        if customer_id:
            initial['customer'] = customer_id
        form = WorkshopJobForm(
            company=company,
            user=request.user,
            initial=initial,
        )

    context = {
        'page_title': 'New Job',
        'page_subtitle': 'Create a repair job',
        'form': form,
        'is_edit': False,
    }
    return render(request, 'workshop/job_form.html', context)


@login_required
@workshop_required
def job_edit(request, pk):
    """Edit an existing job."""
    job = get_object_or_404(_scope_jobs_to_user(request), pk=pk)
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        form = WorkshopJobForm(
            request.POST,
            instance=job,
            company=job.company,
            user=request.user,
        )
        if form.is_valid():
            form.save()
            messages.success(request, 'Job updated.')
            return redirect('workshop:job-detail', pk=job.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = WorkshopJobForm(
            instance=job,
            company=job.company,
            user=request.user,
        )

    context = {
        'page_title': f'Edit {job.job_number}',
        'page_subtitle': 'Update job details',
        'form': form,
        'job': job,
        'is_edit': True,
    }
    return render(request, 'workshop/job_form.html', context)


@login_required
@workshop_required
def job_status_update(request, pk):
    """Change job status via POST. Handles side-effects (timestamps, payout)."""
    job = get_object_or_404(_scope_jobs_to_user(request), pk=pk)
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot change this job.')

    if request.method != 'POST':
        return redirect('workshop:job-detail', pk=job.pk)

    form = JobStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid status.')
        return redirect('workshop:job-detail', pk=job.pk)

    new_status = form.cleaned_data['status']
    old_status = job.status
    job.status = new_status

    now = timezone.now()
    if new_status == 'diagnosed' and not job.diagnosed_at:
        job.diagnosed_at = now
    if new_status == 'approved' and not job.approved_at:
        job.approved_at = now
    if new_status == 'in_progress' and not job.started_at:
        job.started_at = now
    if new_status == 'completed' and not job.completed_at:
        job.completed_at = now
        if not job.completed_by_id:
            job.completed_by = request.user
    if new_status == 'delivered' and not job.delivered_at:
        job.delivered_at = now

    if job.warranty_days and new_status == 'delivered':
        job.warranty_expires_at = now.date() + timedelta(days=job.warranty_days)

    job.save()

    if new_status == 'completed' and job.assigned_technician_id:
        try:
            job.compute_technician_payout()
        except Exception as e:
            messages.warning(request, f'Could not compute technician payout: {e}')

    messages.success(request, f'Status changed: {old_status} → {new_status}')
    return redirect('workshop:job-detail', pk=job.pk)


# ================================================================
# MATERIALS
# ================================================================

@login_required
@workshop_required
def material_add(request, job_pk):
    job = get_object_or_404(_scope_jobs_to_user(request), pk=job_pk)
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        form = JobMaterialForm(request.POST, request.FILES)
        if form.is_valid():
            mat = form.save(commit=False)
            mat.job = job
            mat.added_by = request.user
            mat.save()
            job.save()  # refresh actual_material_cost
            messages.success(request, f'Material "{mat.name}" added.')
            return redirect('workshop:job-detail', pk=job.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = JobMaterialForm()

    context = {
        'page_title': 'Add Material',
        'page_subtitle': f'Job {job.job_number}',
        'form': form,
        'job': job,
        'is_edit': False,
    }
    return render(request, 'workshop/materials_form.html', context)


@login_required
@workshop_required
def material_edit(request, pk):
    mat = get_object_or_404(JobMaterial, pk=pk)
    job = mat.job
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        form = JobMaterialForm(request.POST, request.FILES, instance=mat)
        if form.is_valid():
            form.save()
            job.save()
            messages.success(request, 'Material updated.')
            return redirect('workshop:job-detail', pk=job.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = JobMaterialForm(instance=mat)

    context = {
        'page_title': 'Edit Material',
        'page_subtitle': f'Job {job.job_number}',
        'form': form,
        'job': job,
        'material': mat,
        'is_edit': True,
    }
    return render(request, 'workshop/materials_form.html', context)


@login_required
@workshop_required
def material_delete(request, pk):
    mat = get_object_or_404(JobMaterial, pk=pk)
    job = mat.job
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        mat.delete()
        job.save()
        messages.success(request, 'Material removed.')
        return redirect('workshop:job-detail', pk=job.pk)

    context = {
        'page_title': 'Delete Material',
        'material': mat,
        'job': job,
    }
    return render(request, 'workshop/materials_form.html', context)


# ================================================================
# CUSTOMER PAYMENTS
# ================================================================

@login_required
@workshop_required
def payment_add(request, job_pk):
    job = get_object_or_404(_scope_jobs_to_user(request), pk=job_pk)
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        form = JobPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.job = job
            payment.received_by = request.user
            payment.save()
            messages.success(request, f'Payment of {payment.amount} recorded.')
            return redirect('workshop:job-detail', pk=job.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = JobPaymentForm(initial={'amount': job.balance_due})

    context = {
        'page_title': 'Record Payment',
        'page_subtitle': f'Job {job.job_number}',
        'form': form,
        'job': job,
        'is_edit': False,
    }
    return render(request, 'workshop/payment_form.html', context)


@login_required
@workshop_required
def payment_delete(request, pk):
    payment = get_object_or_404(JobPayment, pk=pk)
    job = payment.job
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        payment.delete()
        total = job.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        WorkshopJob.objects.filter(pk=job.pk).update(amount_paid=total)
        messages.success(request, 'Payment removed.')
        return redirect('workshop:job-detail', pk=job.pk)

    context = {
        'page_title': 'Delete Payment',
        'payment': payment,
        'job': job,
    }
    return render(request, 'workshop/payment_form.html', context)


# ================================================================
# NOTES
# ================================================================

@login_required
@workshop_required
def note_add(request, job_pk):
    job = get_object_or_404(_scope_jobs_to_user(request), pk=job_pk)
    if not _can_edit_job(request.user, job):
        return HttpResponseForbidden('You cannot edit this job.')

    if request.method == 'POST':
        form = JobNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.job = job
            note.created_by = request.user
            note.save()
            messages.success(request, 'Note added.')
        else:
            messages.error(request, 'Invalid note.')
    return redirect('workshop:job-detail', pk=job.pk)


# ================================================================
# PAYOUTS
# ================================================================

@login_required
@workshop_required
def payout_list(request):
    """
    Technician payouts table.
    Columns: date, job id, technician, repair type, material cost,
             customer paid, tech amount, status, actions.
    """
    qs = _payout_scope(request)

    status_filter = request.GET.get('status', '').strip()
    technician_filter = request.GET.get('technician', '').strip()
    search = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if technician_filter:
        qs = qs.filter(technician_id=technician_filter)
    if search:
        qs = qs.filter(
            Q(job__job_number__icontains=search) |
            Q(job__device_name__icontains=search) |
            Q(technician__first_name__icontains=search) |
            Q(technician__last_name__icontains=search) |
            Q(technician__username__icontains=search)
        )

    qs = qs.order_by('-created_at')

    total_count = qs.count()
    page_obj, per_page = _paginate(request, qs)

    if request.user.role == 'super_admin':
        techs = User.objects.filter(role='company_technician')
    else:
        techs = User.objects.filter(
            company=request.user.company,
            role='company_technician',
        )

    # Summary tiles (unfiltered, for the top stats)
    all_qs = _payout_scope(request)
    pending_qs = all_qs.filter(status='pending')
    paid_qs = all_qs.filter(status='paid')

    context = {
        'page_title': 'Technician Payouts',
        'page_subtitle': 'Amounts owed to technicians',
        'payouts': page_obj,
        'per_page': per_page,
        'total_count': total_count,
        'status_filter': status_filter,
        'technician_filter': technician_filter,
        'search': search,
        'technicians': techs,
        'status_choices': TechnicianPayout.STATUS_CHOICES,
        'pending_count': pending_qs.count(),
        'pending_total': pending_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
        'paid_count': paid_qs.count(),
        'paid_total': paid_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
        'can_pay': _can_pay_payouts(request.user),
    }
    return render(request, 'workshop/payout_list.html', context)


@login_required
@workshop_required
def payout_detail(request, pk):
    payout = get_object_or_404(_payout_scope(request), pk=pk)

    context = {
        'page_title': f'Payout — {payout.job.job_number}',
        'page_subtitle': (
            payout.technician.full_name if payout.technician else 'Unassigned'
        ),
        'payout': payout,
        'job': payout.job,
        'can_pay': _can_pay_payouts(request.user),
        'can_edit': _can_manage_rates(request.user),
    }
    return render(request, 'workshop/payout_detail.html', context)


@login_required
@workshop_required
def payout_edit(request, pk):
    """Adjust the payout amount (admin only)."""
    payout = get_object_or_404(_payout_scope(request), pk=pk)
    if not _can_manage_rates(request.user):
        return HttpResponseForbidden('Only admins can edit payouts.')

    if payout.status == 'paid':
        messages.error(request, 'A paid payout cannot be edited.')
        return redirect('workshop:payout-detail', pk=payout.pk)

    if request.method == 'POST':
        form = PayoutEditForm(request.POST, instance=payout)
        if form.is_valid():
            payout = form.save(commit=False)
            payout.basis = 'manual'
            payout.computed_by = request.user
            payout.save()
            messages.success(request, 'Payout amount updated.')
            return redirect('workshop:payout-detail', pk=payout.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = PayoutEditForm(instance=payout)

    context = {
        'page_title': 'Edit Payout',
        'page_subtitle': payout.job.job_number,
        'form': form,
        'payout': payout,
        'job': payout.job,
        'mode': 'edit',
    }
    return render(request, 'workshop/payout_form.html', context)


@login_required
@workshop_required
def payout_mark_paid(request, pk):
    """Record a payout payment (admin only)."""
    payout = get_object_or_404(_payout_scope(request), pk=pk)
    if not _can_pay_payouts(request.user):
        return HttpResponseForbidden('Only admins can pay technicians.')

    if payout.status == 'paid':
        messages.info(request, 'This payout is already marked paid.')
        return redirect('workshop:payout-detail', pk=payout.pk)

    if request.method == 'POST':
        form = PayoutPayForm(request.POST, instance=payout)
        if form.is_valid():
            payout = form.save(commit=False)
            payout.status = 'paid'
            payout.paid_at = timezone.now()
            payout.paid_by = request.user
            payout.save()
            messages.success(
                request,
                f'Payout of {payout.amount} to '
                f'{payout.technician.full_name if payout.technician else "technician"} recorded.'
            )
            return redirect('workshop:payout-detail', pk=payout.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = PayoutPayForm(instance=payout)

    context = {
        'page_title': f'Pay {payout.amount}',
        'page_subtitle': payout.job.job_number,
        'form': form,
        'payout': payout,
        'job': payout.job,
        'mode': 'pay',
    }
    return render(request, 'workshop/payout_form.html', context)


# ================================================================
# TECHNICIAN RATES
# ================================================================

@login_required
@workshop_required
def rate_list(request):
    if not _can_manage_rates(request.user):
        return HttpResponseForbidden('Only admins can manage technician rates.')

    qs = TechnicianRate.objects.select_related('technician')
    if request.user.role != 'super_admin':
        qs = qs.filter(company=request.user.company)

    context = {
        'page_title': 'Technician Rates',
        'page_subtitle': 'Default payout percentages',
        'rates': qs.order_by('technician__first_name', 'repair_category'),
    }
    return render(request, 'workshop/rate_list.html', context)


@login_required
@workshop_required
def rate_create(request):
    if not _can_manage_rates(request.user):
        return HttpResponseForbidden('Only admins can manage technician rates.')

    company = _company_or_404(request)

    if request.method == 'POST':
        form = TechnicianRateForm(request.POST, company=company)
        if form.is_valid():
            rate = form.save(commit=False)
            rate.company = company or form.cleaned_data.get('company')
            rate.save()
            messages.success(request, 'Rate created.')
            return redirect('workshop:rate-list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = TechnicianRateForm(company=company)

    context = {
        'page_title': 'New Technician Rate',
        'form': form,
        'is_edit': False,
    }
    return render(request, 'workshop/rate_form.html', context)


@login_required
@workshop_required
def rate_edit(request, pk):
    if not _can_manage_rates(request.user):
        return HttpResponseForbidden('Only admins can manage technician rates.')

    qs = TechnicianRate.objects.all()
    if request.user.role != 'super_admin':
        qs = qs.filter(company=request.user.company)
    rate = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        form = TechnicianRateForm(request.POST, instance=rate, company=rate.company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rate updated.')
            return redirect('workshop:rate-list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = TechnicianRateForm(instance=rate, company=rate.company)

    context = {
        'page_title': 'Edit Technician Rate',
        'form': form,
        'rate': rate,
        'is_edit': True,
    }
    return render(request, 'workshop/rate_form.html', context)


@login_required
@workshop_required
def rate_delete(request, pk):
    if not _can_manage_rates(request.user):
        return HttpResponseForbidden('Only admins can manage technician rates.')

    qs = TechnicianRate.objects.all()
    if request.user.role != 'super_admin':
        qs = qs.filter(company=request.user.company)
    rate = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        rate.delete()
        messages.success(request, 'Rate deleted.')
        return redirect('workshop:rate-list')

    context = {
        'page_title': 'Delete Rate',
        'rate': rate,
    }
    return render(request, 'workshop/rate_form.html', context)


# ================================================================
# CUSTOMERS
# ================================================================

@login_required
@workshop_required
def customer_list(request):
    company = _company_or_404(request)
    qs = WorkshopCustomer.objects.all()
    if request.user.role != 'super_admin':
        qs = qs.filter(company=company)

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search)
        )

    qs = qs.order_by('-created_at')

    total_count = qs.count()

    # Simple stats for the header tiles (unfiltered numbers)
    unfiltered = WorkshopCustomer.objects.all()
    if request.user.role != 'super_admin':
        unfiltered = unfiltered.filter(company=company)
    with_phone_count = unfiltered.exclude(phone='').count()
    month_start = timezone.now().replace(day=1).date()
    new_this_month = unfiltered.filter(created_at__date__gte=month_start).count()

    page_obj, per_page = _paginate(request, qs)

    context = {
        'page_title': 'Customers',
        'page_subtitle': 'Workshop clients',
        'customers': page_obj,
        'per_page': per_page,
        'total_count': total_count,
        'with_phone_count': with_phone_count,
        'new_this_month': new_this_month,
        'search': search,
    }
    return render(request, 'workshop/customer_list.html', context)


@login_required
@workshop_required
def customer_create(request):
    company = _company_or_404(request)

    if request.method == 'POST':
        form = WorkshopCustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.company = company or form.cleaned_data.get('company')
            customer.save()
            messages.success(request, f'Customer "{customer.name}" created.')
            return redirect('workshop:customer-list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = WorkshopCustomerForm()

    context = {
        'page_title': 'New Customer',
        'page_subtitle': 'Add a new workshop client',
        'form': form,
        'is_edit': False,
    }
    return render(request, 'workshop/customer_form.html', context)


@login_required
@workshop_required
def customer_edit(request, pk):
    company = _company_or_404(request)
    qs = WorkshopCustomer.objects.all()
    if request.user.role != 'super_admin':
        qs = qs.filter(company=company)
    customer = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        form = WorkshopCustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated.')
            return redirect('workshop:customer-list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = WorkshopCustomerForm(instance=customer)

    context = {
        'page_title': 'Edit Customer',
        'page_subtitle': f'Editing {customer.name}',
        'form': form,
        'customer': customer,
        'is_edit': True,
    }
    return render(request, 'workshop/customer_form.html', context)


# ================================================================
# RECEIPT
# ================================================================

@login_required
@workshop_required
def job_receipt(request, pk):
    """Printable receipt for a job."""
    job = get_object_or_404(_scope_jobs_to_user(request), pk=pk)

    context = {
        'job': job,
        'company': job.company,
        'customer': job.customer,
        'materials': job.materials.all(),
        'payments': job.payments.all(),
        'notes': job.notes.filter(is_customer_visible=True),
        'printed_at': timezone.now(),
    }
    return render(request, 'workshop/receipt.html', context)