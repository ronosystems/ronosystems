"""
Kuku Biz — settings views.

These plug into the existing company settings framework (apps.company).
They add a Kuku-specific tab on /company/settings/.
"""

import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.companies.support_utils import get_active_company


def _get_kuku_settings(company):
    """Return Kuku Biz settings from company.company_settings, with defaults."""
    defaults = {
        'default_tray_price': 360,
        'default_tray_size': 30,
        'default_crate_size': 360,
        'auto_alert_breach_days': 3,   # days a flock can sit at low lay rate
        'notify_email': '',            # send alerts here (optional)
    }
    try:
        data = json.loads(company.company_settings or '{}')
        saved = data.get('kuku_biz', {})
        defaults.update(saved)
    except Exception:
        pass
    return defaults


def _save_kuku_settings(company, payload):
    """Persist Kuku settings back into company.company_settings JSON."""
    try:
        existing = json.loads(company.company_settings or '{}')
    except Exception:
        existing = {}

    existing['kuku_biz'] = payload
    company.company_settings = json.dumps(existing)
    company.save(update_fields=['company_settings'])


@login_required
def settings_kuku(request):
    """Kuku Biz settings — defaults for the Kuku Biz module."""
    company, is_viewing_company = get_active_company(request)

    if not company:
        if request.user.role == 'super_admin':
            return redirect('/api/support/select/')
        messages.warning(request, 'You are not assigned to any company.')
        return redirect('/dashboard/')

    if request.method == 'POST':
        try:
            payload = {
                'default_tray_price': float(request.POST.get('default_tray_price') or 0),
                'default_tray_size':  int(request.POST.get('default_tray_size') or 30),
                'default_crate_size': int(request.POST.get('default_crate_size') or 360),
                'auto_alert_breach_days': int(request.POST.get('auto_alert_breach_days') or 3),
                'notify_email': request.POST.get('notify_email', '').strip(),
            }
            _save_kuku_settings(company, payload)
            messages.success(request, 'Kuku Biz settings updated.')
            return redirect('company-settings-kuku')
        except Exception as e:
            messages.error(request, f'Error saving Kuku Biz settings: {e}')

    kuku = _get_kuku_settings(company)

    context = {
        'company': company,
        'settings': kuku,
        'is_settings': True,
        'active_tab': 'kuku',       # so the settings template highlights the right tab
        'is_viewing_company': is_viewing_company,
    }
    return render(request, 'company/settings/kuku.html', context)