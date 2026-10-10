from django.utils import timezone


def visit_count_today(request):
    """
    Expose 'unread' visit count to templates as `visits_today_count`.

    The count shows visits that arrived AFTER the user last opened the
    analytics dashboard. Opening the dashboard resets the badge to 0.

    Only runs for authenticated super admins to keep it cheap.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    if getattr(user, 'role', None) != 'super_admin':
        return {}

    # When the user is currently ON the dashboard, badge = 0.
    if request.path.startswith('/analytics/'):
        # Mark "I've seen everything up to now"
        request.session['visits_last_seen'] = timezone.now().isoformat()
        return {'visits_today_count': 0}

    try:
        from .models import Visit

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # If the user has seen the dashboard before, count only newer rows.
        last_seen_iso = request.session.get('visits_last_seen')
        if last_seen_iso:
            try:
                from datetime import datetime
                last_seen = datetime.fromisoformat(last_seen_iso)
                # Make timezone-aware if naive
                if timezone.is_naive(last_seen):
                    last_seen = timezone.make_aware(last_seen)
                # Don't count before midnight today
                cutoff = max(last_seen, today_start)
            except (ValueError, TypeError):
                cutoff = today_start
        else:
            cutoff = today_start

        count = Visit.objects.filter(created_at__gte=cutoff).count()
    except Exception:
        count = 0

    return {'visits_today_count': count}