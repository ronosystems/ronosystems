from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.company.models import Branch
from apps.companies.models import Company
from apps.companies.support_utils import (
    get_active_company,
    is_support_mode,
    is_effective_admin,
    get_effective_branch,
)


@login_required
def branch_list(request):
    """List all branches for the user's company"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    branches = (
        Branch.objects
        .filter(company=company)
        .select_related('parent')
        .prefetch_related('children')
        .order_by('name')
    )

    active_count = branches.filter(is_active=True).count()
    mother_branch = branches.filter(is_mother_branch=True).first()

    context = {
        'company': company,
        'branches': branches,
        'total_count': branches.count(),
        'active_count': active_count,
        'mother_branch': mother_branch,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Branches',
        'page_subtitle': 'Manage your branches',
    }
    return render(request, 'company/branches/list.html', context)


@login_required
def branch_create(request):
    """Create a new branch"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    # Existing mother (for the "currently X is the mother" warning)
    existing_mother = Branch.objects.filter(
        company=company, is_mother_branch=True
    ).first()

    # All branches (for the parent dropdown)
    all_branches = (
        Branch.objects
        .filter(company=company, is_active=True)
        .order_by('name')
    )

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        country = request.POST.get('country', '').strip()
        currency = request.POST.get('currency', 'KES')
        currency_symbol = request.POST.get('currency_symbol', 'KSh')
        is_mother_branch = request.POST.get('is_mother_branch') == 'on'
        parent_id = request.POST.get('parent') or None

        if not name:
            messages.error(request, 'Branch name is required.')
            return render(request, 'company/branches/form.html', {
                'branch': None,
                'company': company,
                'is_viewing_company': is_viewing_company,
                'existing_mother_branch': existing_mother,
                'all_branches': all_branches,
                'page_title': 'Create Branch',
                'page_subtitle': 'Add a new branch',
            })

        try:
            # Resolve parent
            parent = None
            if parent_id:
                parent = Branch.objects.filter(
                    id=parent_id, company=company
                ).first()

            # If marking as mother, unset any existing mother
            if is_mother_branch:
                Branch.objects.filter(
                    company=company, is_mother_branch=True
                ).update(is_mother_branch=False)
                parent = None  # a mother branch can't have a parent

            branch = Branch.objects.create(
                company=company,
                name=name,
                code=code or name[:3].upper(),
                address=address,
                phone=phone,
                email=email,
                city=city,
                country=country,
                is_active=True,
                currency=currency,
                currency_symbol=currency_symbol,
                is_mother_branch=is_mother_branch,
                parent=parent,
            )
            messages.success(request, f'Branch "{name}" created successfully!')
            return redirect('/company/branches/')
        except Exception as e:
            messages.error(request, f'Error creating branch: {str(e)}')

    context = {
        'branch': None,
        'company': company,
        'is_viewing_company': is_viewing_company,
        'existing_mother_branch': existing_mother,
        'all_branches': all_branches,
        'page_title': 'Create Branch',
        'page_subtitle': 'Add a new branch',
    }
    return render(request, 'company/branches/form.html', context)


@login_required
def branch_edit(request, pk):
    """Edit a branch"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    branch = get_object_or_404(Branch, pk=pk, company=company)

    # Existing mother — excluding this branch
    existing_mother = (
        Branch.objects
        .filter(company=company, is_mother_branch=True)
        .exclude(pk=branch.pk)
        .first()
    )

    # All branches (for parent dropdown) — excluding self and self's descendants
    # to prevent circular references
    descendant_ids = [branch.pk]
    stack = [branch.pk]
    while stack:
        current_id = stack.pop()
        children = Branch.objects.filter(
            company=company, parent_id=current_id
        ).values_list('id', flat=True)
        for cid in children:
            if cid not in descendant_ids:
                descendant_ids.append(cid)
                stack.append(cid)

    all_branches = (
        Branch.objects
        .filter(company=company, is_active=True)
        .exclude(pk__in=descendant_ids)
        .order_by('name')
    )

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        city = request.POST.get('city', '').strip()
        country = request.POST.get('country', '').strip()
        currency = request.POST.get('currency', 'KES')
        currency_symbol = request.POST.get('currency_symbol', 'KSh')
        is_active = request.POST.get('is_active') == 'on'
        is_mother_branch = request.POST.get('is_mother_branch') == 'on'
        parent_id = request.POST.get('parent') or None

        if not name:
            messages.error(request, 'Branch name is required.')
            return render(request, 'company/branches/form.html', {
                'branch': branch,
                'company': company,
                'is_viewing_company': is_viewing_company,
                'existing_mother_branch': existing_mother,
                'all_branches': all_branches,
                'page_title': 'Edit Branch',
                'page_subtitle': f'Editing {branch.name}',
            })

        try:
            # Resolve parent
            parent = None
            if parent_id:
                parent = Branch.objects.filter(
                    id=parent_id, company=company
                ).exclude(pk=branch.pk).first()

            # If marking as mother, unset any other mother
            if is_mother_branch:
                Branch.objects.filter(
                    company=company, is_mother_branch=True
                ).exclude(pk=branch.pk).update(is_mother_branch=False)
                parent = None  # a mother branch can't have a parent

            branch.name = name
            branch.code = code or name[:3].upper()
            branch.address = address
            branch.phone = phone
            branch.email = email
            branch.city = city
            branch.country = country
            branch.currency = currency
            branch.currency_symbol = currency_symbol
            branch.is_active = is_active
            branch.is_mother_branch = is_mother_branch
            branch.parent = parent
            branch.save()

            messages.success(request, f'Branch "{name}" updated successfully!')
            return redirect('/company/branches/')
        except Exception as e:
            messages.error(request, f'Error updating branch: {str(e)}')

    context = {
        'branch': branch,
        'company': company,
        'is_viewing_company': is_viewing_company,
        'existing_mother_branch': existing_mother,
        'all_branches': all_branches,
        'page_title': 'Edit Branch',
        'page_subtitle': f'Editing {branch.name}',
    }
    return render(request, 'company/branches/form.html', context)


@login_required
def branch_delete(request, pk):
    """Delete a branch"""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    branch = get_object_or_404(Branch, pk=pk, company=company)

    if request.method == 'POST':
        try:
            name = branch.name

            # Safety: if this is the mother branch and it has children,
            # warn the user before deleting.
            if branch.is_mother_branch:
                child_count = branch.children.count()
                if child_count > 0:
                    messages.warning(
                        request,
                        f'"{name}" is the mother branch with '
                        f'{child_count} child branch{"" if child_count == 1 else "es"}. '
                        f'Those branches will be orphaned (parent set to blank).'
                    )

            branch.delete()
            messages.success(request, f'Branch "{name}" deleted successfully!')
            return redirect('/company/branches/')
        except Exception as e:
            messages.error(request, f'Error deleting branch: {str(e)}')

    context = {
        'branch': branch,
        'company': company,
        'is_viewing_company': is_viewing_company,
        'page_title': 'Delete Branch',
        'page_subtitle': f'Confirm deletion of {branch.name}',
    }
    return render(request, 'company/branches/delete.html', context)