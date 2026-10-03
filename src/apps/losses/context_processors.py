from apps.companies.support_utils import get_active_company


def pending_losses_count(request):
    """
    Expose `pending_losses_count` to every template — the number of
    unverified LossReturn records for the current company.

    - Super admin not in support mode: skip (no single company).
    - Unauthenticated users: skip.
    - No active company: skip.
    """
    if not request.user.is_authenticated:
        return {'pending_losses_count': 0}

    if request.user.role == 'super_admin' and not request.session.get('support_company_id'):
        return {'pending_losses_count': 0}

    try:
        company, _ = get_active_company(request)
    except Exception:
        return {'pending_losses_count': 0}

    if not company:
        return {'pending_losses_count': 0}

    # Local import to avoid app-loading ordering issues
    from apps.losses.models import LossReturn

    count = LossReturn.objects.filter(
        company=company,
        is_verified=False,
    ).count()

    return {'pending_losses_count': count}