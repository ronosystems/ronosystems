from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import models
from apps.accounts.permissions import IsCompanyAdmin, IsSameCompany
from django.contrib.auth import get_user_model

User = get_user_model()

class CompanyDashboardView(APIView):
    """
    Company Admin: Company-specific dashboard
    """
    permission_classes = [IsAuthenticated, IsCompanyAdmin, IsSameCompany]
    
    def get(self, request):
        company = request.user.company
        
        # Employee stats
        total_employees = User.objects.filter(company=company).count()
        
        # Employee by role
        admins = User.objects.filter(company=company, role='company_admin').count()
        managers = User.objects.filter(company=company, role='company_manager').count()
        staff = User.objects.filter(company=company, role='company_staff').count()
        employees = User.objects.filter(company=company, role='employee').count()
        
        # Recent activity (simplified)
        recent_employees = User.objects.filter(
            company=company
        ).order_by('-created_at')[:5]
        
        # Company info
        company_info = {
            'id': company.id,
            'name': company.name,
            'plan': company.plan,
            'subscription_active': company.is_subscription_active,
            'subscription_end': company.subscription_end,
            'business_type': company.business_type.name if company.business_type else None,
        }
        
        return Response({
            'company': company_info,
            'stats': {
                'total_employees': total_employees,
                'company_admins': admins,
                'company_managers': managers,
                'company_staff': staff,
                'employees': employees,
            },
            'recent_employees': UserSerializer(recent_employees, many=True).data,
            'timestamp': timezone.now()
        })
