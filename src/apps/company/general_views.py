from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from apps.companies.utils import get_current_company

User = get_user_model()


@login_required
def general_dashboard(request):
    company = get_current_company(request)
    employees = User.objects.filter(company=company) if company else User.objects.none()

    context = {
        'company': company,
        'stats': {
            'total': employees.count(),
            'managers': employees.filter(role='company_manager').count(),
            'staff': employees.filter(role='company_staff').count(),
            'employees': employees.filter(role='employee').count(),
        }
    }
    return render(request, 'company/general_dashboard.html', context)