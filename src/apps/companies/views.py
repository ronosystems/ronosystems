from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Company, BusinessType
from .serializers import CompanySerializer, BusinessTypeSerializer
from apps.accounts.permissions import IsSuperAdmin
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

User = get_user_model()


# ============================================
# COMPANY SWITCH VIEW
# ============================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from apps.companies.models import Company


@login_required
@staff_member_required
def support_mode(request, pk):
    """
    Support Mode - Super admin views company as if they are a user
    Shows a banner indicating support mode
    """
    company = get_object_or_404(Company, id=pk)
    
    # Store the company ID in session
    request.session['viewing_company_id'] = company.id
    request.session['support_mode'] = True  # Flag for support mode
    
    # Store the original user ID for easy return
    if 'original_user_id' not in request.session:
        request.session['original_user_id'] = request.user.id
    
    messages.success(request, f'🔧 Support Mode: Coming Soon')
    
    # ============================================
    # Redirect based on business type
    # ============================================
    
    business_type = company.business_type
    
    # DEBUG - Print to see what's happening
    print(f"Company: {company.name}")
    print(f"Business Type: {business_type}")
    if business_type:
        print(f"Business Type Name: {business_type.name}")
    
    # Check if company has EPA Shop business type
    if business_type and ('epa' in business_type.name.lower() or 'electronics' in business_type.name.lower()):
        return redirect('/epa_shop/dashboard/')
    
    # Check for other business types
    if business_type:
        business_name = business_type.name.lower()
        
        # Supermarket
        if 'supermarket' in business_name or 'grocery' in business_name:
            return redirect('/supermarket/dashboard/')
        
        # Healthcare
        elif 'healthcare' in business_name or 'medical' in business_name:
            return redirect('/healthcare/dashboard/')
        
        # Education
        elif 'education' in business_name or 'school' in business_name:
            return redirect('/education/dashboard/')
        
        # Restaurant
        elif 'restaurant' in business_name or 'food' in business_name:
            return redirect('/restaurant/dashboard/')
        
        # Retail
        elif 'retail' in business_name:
            return redirect('/retail/dashboard/')
    
    # If no specific business type, redirect to company dashboard
    return redirect('/company/dashboard/')

    


@login_required
def exit_company_view(request):
    """Exit company view and return to super admin dashboard"""
    
    if 'viewing_company_id' in request.session:
        company_name = None
        try:
            company = Company.objects.get(id=request.session['viewing_company_id'])
            company_name = company.name
        except:
            pass
        
        # Clear the viewing company session
        del request.session['viewing_company_id']
        
        if company_name:
            messages.success(request, f'✅ Exited {company_name}. Returned to your dashboard.')
        else:
            messages.success(request, '✅ Exited company view. Returned to your dashboard.')
    else:
        messages.warning(request, 'You are not viewing any company.')
    
    return redirect('/dashboard/')


# ============================================
# COMPANY LIST VIEW (Web)
# ============================================

@login_required
@staff_member_required
def company_list(request):
    """List all companies"""
    companies = Company.objects.all().order_by('-created_at')
    
    # Stats
    total_companies = companies.count()
    active_companies = companies.filter(is_active=True).count()
    inactive_companies = companies.filter(is_active=False).count()
    
    # Pagination
    paginator = Paginator(companies, 20)
    page = request.GET.get('page', 1)
    
    try:
        companies_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        companies_page = paginator.page(1)
    
    context = {
        'companies': companies_page,
        'total_companies': total_companies,
        'active_companies': active_companies,
        'inactive_companies': inactive_companies,
        'page_title': 'Companies',
        'page_subtitle': 'Manage all companies',
    }
    return render(request, 'companies/list.html', context)


# ============================================
# COMPANY DETAIL VIEW
# ============================================

@login_required
@staff_member_required
def company_detail(request, pk):
    """View company details"""
    company = get_object_or_404(Company, id=pk)
    
    context = {
        'company': company,
        'page_title': f'Company: {company.name}',
        'page_subtitle': 'Company details',
    }
    return render(request, 'companies/detail.html', context)


# ============================================
# COMPANY CREATE VIEW
# ============================================

@login_required
@staff_member_required
def company_create(request):
    """Create a new company"""
    business_types = BusinessType.objects.filter(is_active=True)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            business_type_id = request.POST.get('business_type')
            registration_number = request.POST.get('registration_number')
            address = request.POST.get('address')
            city = request.POST.get('city')
            state = request.POST.get('state')
            country = request.POST.get('country')
            postal_code = request.POST.get('postal_code')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            website = request.POST.get('website')
            plan = request.POST.get('plan', 'free')
            
            if not name:
                messages.error(request, 'Company name is required.')
                return render(request, 'companies/form.html', {
                    'business_types': business_types,
                    'page_title': 'Add Company',
                    'page_subtitle': 'Create a new company',
                })
            
            company = Company.objects.create(
                name=name,
                business_type_id=business_type_id if business_type_id else None,
                registration_number=registration_number or '',
                address=address or '',
                city=city or '',
                state=state or '',
                country=country or '',
                postal_code=postal_code or '',
                email=email or '',
                phone=phone or '',
                website=website or '',
                plan=plan,
                created_by=request.user,
                is_active=True
            )
            
            messages.success(request, f'Company "{company.name}" created successfully!')
            return redirect('/companies/')
            
        except Exception as e:
            messages.error(request, f'Error creating company: {str(e)}')
    
    context = {
        'business_types': business_types,
        'page_title': 'Add Company',
        'page_subtitle': 'Create a new company',
    }
    return render(request, 'companies/form.html', context)


# ============================================
# COMPANY EDIT VIEW
# ============================================

@login_required
@staff_member_required
def company_edit(request, pk):
    """Edit company"""
    company = get_object_or_404(Company, id=pk)
    business_types = BusinessType.objects.filter(is_active=True)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            business_type_id = request.POST.get('business_type')
            registration_number = request.POST.get('registration_number')
            address = request.POST.get('address')
            city = request.POST.get('city')
            state = request.POST.get('state')
            country = request.POST.get('country')
            postal_code = request.POST.get('postal_code')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            website = request.POST.get('website')
            plan = request.POST.get('plan', 'free')
            is_active = request.POST.get('is_active') == 'on'
            
            if not name:
                messages.error(request, 'Company name is required.')
                return render(request, 'companies/form.html', {
                    'company': company,
                    'business_types': business_types,
                    'page_title': 'Edit Company',
                    'page_subtitle': f'Edit {company.name}',
                })
            
            company.name = name
            company.business_type_id = business_type_id if business_type_id else None
            company.registration_number = registration_number or ''
            company.address = address or ''
            company.city = city or ''
            company.state = state or ''
            company.country = country or ''
            company.postal_code = postal_code or ''
            company.email = email or ''
            company.phone = phone or ''
            company.website = website or ''
            company.plan = plan
            company.is_active = is_active
            company.save()
            
            messages.success(request, f'Company "{company.name}" updated successfully!')
            return redirect('/companies/')
            
        except Exception as e:
            messages.error(request, f'Error updating company: {str(e)}')
    
    context = {
        'company': company,
        'business_types': business_types,
        'page_title': 'Edit Company',
        'page_subtitle': f'Edit {company.name}',
    }
    return render(request, 'companies/form.html', context)


# ============================================
# COMPANY DELETE VIEW
# ============================================

@login_required
@staff_member_required
def company_delete(request, pk):
    """Delete company"""
    company = get_object_or_404(Company, id=pk)
    
    if request.method == 'POST':
        try:
            company_name = company.name
            company.delete()
            messages.success(request, f'Company "{company_name}" deleted successfully!')
            return redirect('/companies/')
        except Exception as e:
            messages.error(request, f'Error deleting company: {str(e)}')
    
    context = {
        'company': company,
        'page_title': 'Delete Company',
        'page_subtitle': f'Delete {company.name}',
    }
    return render(request, 'companies/delete.html', context)


# ============================================
# API VIEWS
# ============================================

class DashboardStatsView(APIView):
    """Super Admin Dashboard Statistics"""
    permission_classes = [IsSuperAdmin]
    
    def get(self, request):
        total_companies = Company.objects.count()
        active_companies = Company.objects.filter(is_active=True).count()
        total_users = User.objects.count()
        
        # Users by role
        users_by_role = User.objects.values('role').annotate(count=Count('id'))
        
        # Companies by plan
        companies_by_plan = Company.objects.values('plan').annotate(count=Count('id'))
        
        # Recent companies
        recent_companies = Company.objects.order_by('-created_at')[:5]
        
        # Expiring subscriptions (next 30 days)
        thirty_days_from_now = timezone.now() + timezone.timedelta(days=30)
        expiring_subscriptions = Company.objects.filter(
            subscription_end__lte=thirty_days_from_now,
            subscription_end__gte=timezone.now(),
            is_active=True
        ).count()
        
        return Response({
            'total_companies': total_companies,
            'active_companies': active_companies,
            'total_users': total_users,
            'users_by_role': users_by_role,
            'companies_by_plan': companies_by_plan,
            'recent_companies': CompanySerializer(recent_companies, many=True).data,
            'expiring_subscriptions': expiring_subscriptions,
            'timestamp': timezone.now()
        })


class CompanyListView(APIView):
    """List and create companies"""
    permission_classes = [IsSuperAdmin]
    
    def get(self, request):
        companies = Company.objects.all()
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