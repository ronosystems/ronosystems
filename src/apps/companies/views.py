# apps/companies/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Count
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Company, BusinessType
from .serializers import CompanySerializer, BusinessTypeSerializer
from apps.accounts.permissions import IsSuperAdmin

User = get_user_model()


# ============================================
# DASHBOARD STATS (API)
# ============================================

class DashboardStatsView(APIView):
    """Super Admin Dashboard Statistics"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        total_companies = Company.objects.count()
        active_companies = Company.objects.filter(is_active=True).count()
        total_users = User.objects.count()

        users_by_role = User.objects.values('role').annotate(count=Count('id'))
        companies_by_plan = Company.objects.values('plan__name').annotate(count=Count('id'))

        recent_companies = Company.objects.select_related('plan', 'business_type').order_by('-created_at')[:5]

        thirty_days_from_now = timezone.now() + timezone.timedelta(days=30)
        expiring_subscriptions = Company.objects.filter(
            subscription_end__lte=thirty_days_from_now,
            subscription_end__gte=timezone.now(),
            is_active=True,
        ).count()

        return Response({
            'total_companies': total_companies,
            'active_companies': active_companies,
            'total_users': total_users,
            'users_by_role': list(users_by_role),
            'companies_by_plan': list(companies_by_plan),
            'recent_companies': CompanySerializer(recent_companies, many=True).data,
            'expiring_subscriptions': expiring_subscriptions,
            'timestamp': timezone.now(),
        })


# ============================================
# COMPANY API
# ============================================

class CompanyListView(APIView):
    """List and create companies"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        companies = Company.objects.select_related('plan', 'business_type').all()
        serializer = CompanySerializer(companies, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CompanySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CompanyDetailView(APIView):
    """Retrieve, update, delete company"""
    permission_classes = [IsSuperAdmin]

    def get_object(self, pk):
        try:
            return Company.objects.get(pk=pk)
        except Company.DoesNotExist:
            return None

    def get(self, request, pk):
        company = self.get_object(pk)
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CompanySerializer(company)
        return Response(serializer.data)

    def put(self, request, pk):
        company = self.get_object(pk)
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CompanySerializer(company, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        company = self.get_object(pk)
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)
        company.delete()
        return Response({'message': 'Company deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


# ============================================
# BUSINESS TYPE API
# ============================================

class BusinessTypeListView(APIView):
    """List and create business types"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        business_types = BusinessType.objects.filter(is_active=True)
        serializer = BusinessTypeSerializer(business_types, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = BusinessTypeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BusinessTypeDetailView(APIView):
    """Retrieve, update, delete business type"""
    permission_classes = [IsSuperAdmin]

    def get_object(self, pk):
        try:
            return BusinessType.objects.get(pk=pk)
        except BusinessType.DoesNotExist:
            return None

    def get(self, request, pk):
        business_type = self.get_object(pk)
        if not business_type:
            return Response({'error': 'Business type not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BusinessTypeSerializer(business_type)
        return Response(serializer.data)

    def put(self, request, pk):
        business_type = self.get_object(pk)
        if not business_type:
            return Response({'error': 'Business type not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = BusinessTypeSerializer(business_type, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        business_type = self.get_object(pk)
        if not business_type:
            return Response({'error': 'Business type not found'}, status=status.HTTP_404_NOT_FOUND)
        business_type.delete()
        return Response({'message': 'Business type deleted successfully'}, status=status.HTTP_204_NO_CONTENT)