from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def general_dashboard(request):
    company = request.user.company
    employees = User.objects.filter(company=company) if company else []
    
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
