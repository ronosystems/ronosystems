from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DeleteView, TemplateView, UpdateView
from django.urls import reverse_lazy
from django.db.models import Count, Q
from apps.epa_shop.models import Branch

User = get_user_model()

class CompanyAdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role == 'company_admin'

# ============================================
# 5.1 CREATE EMPLOYEE
# ============================================

class AddEmployeeView(LoginRequiredMixin, CompanyAdminRequiredMixin, TemplateView):
    template_name = 'company/add_employee.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.request.user.company
        
        branches = Branch.objects.filter(company=company, is_active=True)
        
        context['company'] = company
        context['branches'] = branches
        context['roles'] = [
            {'value': 'company_manager', 'label': 'Manager'},
            {'value': 'company_staff', 'label': 'Staff'},
            {'value': 'employee', 'label': 'Employee'},
        ]
        return context
    
    def post(self, request):
        company = request.user.company
        
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        role = request.POST.get('role', 'employee')
        branch_id = request.POST.get('branch', '')
        department = request.POST.get('department', '').strip()
        position = request.POST.get('position', '').strip()
        employee_id = request.POST.get('employee_id', '').strip()
        hire_date = request.POST.get('hire_date', '')
        
        if not all([first_name, last_name, email, username, password]):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })
        
        if not branch_id:
            messages.error(request, 'Please select a branch for the employee.')
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })
        
        try:
            branch = Branch.objects.get(id=branch_id, company=company)
        except Branch.DoesNotExist:
            messages.error(request, 'Selected branch does not exist.')
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })
        
        if User.objects.filter(email=email).exists():
            messages.error(request, f'User with email "{email}" already exists.')
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })
        
        if User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })
        
        try:
            validate_password(password)
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=role,
                company=company,
                branch=branch,
                phone=phone,
                first_name=first_name,
                last_name=last_name,
                department=department,
                position=position,
                employee_id=employee_id,
                hire_date=hire_date if hire_date else None,
                is_active=True
            )
            
            messages.success(request, f'✅ Employee {user.first_name} {user.last_name} added successfully to {branch.name}!')
            return redirect('/company/employees/')
            
        except Exception as e:
            messages.error(request, f'Error creating employee: {str(e)}')
            return render(request, self.template_name, {
                'company': company,
                'branches': Branch.objects.filter(company=company, is_active=True)
            })

# ============================================
# 5.2 LIST EMPLOYEES
# ============================================

class EmployeeListView(LoginRequiredMixin, CompanyAdminRequiredMixin, ListView):
    model = User
    template_name = 'company/employees.html'
    context_object_name = 'employees'
    
    def get_queryset(self):
        queryset = User.objects.filter(
            company=self.request.user.company
        ).exclude(
            role='super_admin'
        ).order_by('-created_at')
        
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(employee_id__icontains=search)
            )
        
        role = self.request.GET.get('role', '')
        if role:
            queryset = queryset.filter(role=role)
        
        branch = self.request.GET.get('branch', '')
        if branch:
            queryset = queryset.filter(branch_id=branch)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.request.user.company
        employees = User.objects.filter(company=company)
        
        branches = Branch.objects.filter(company=company, is_active=True)
        
        context['stats'] = {
            'total_employees': employees.count(),
            'managers': employees.filter(role='company_manager').count(),
            'staff': employees.filter(role='company_staff').count(),
            'employees': employees.filter(role='employee').count(),
        }
        
        context['departments'] = employees.exclude(
            department=''
        ).values_list('department', flat=True).distinct()
        
        context['branches'] = branches
        context['company'] = company
        return context

# ============================================
# 5.3 EDIT EMPLOYEE
# ============================================

class EmployeeEditView(LoginRequiredMixin, CompanyAdminRequiredMixin, UpdateView):
    model = User
    template_name = 'company/employee_edit.html'
    fields = ['first_name', 'last_name', 'email', 'phone', 'role', 'branch', 
              'department', 'position', 'employee_id', 'hire_date', 'is_active']
    success_url = reverse_lazy('employee-list')
    
    def get_queryset(self):
        return User.objects.filter(company=self.request.user.company)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = self.request.user.company
        branches = Branch.objects.filter(company=company, is_active=True)
        context['branches'] = branches
        context['company'] = company
        context['roles'] = [
            {'value': 'company_manager', 'label': 'Manager'},
            {'value': 'company_staff', 'label': 'Staff'},
            {'value': 'employee', 'label': 'Employee'},
        ]
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f'✅ Employee {form.instance.get_full_name()} updated successfully!')
        return super().form_valid(form)

# ============================================
# 5.4 DELETE EMPLOYEE
# ============================================

class DeleteEmployeeView(LoginRequiredMixin, CompanyAdminRequiredMixin, DeleteView):
    model = User
    template_name = 'company/delete_employee.html'
    success_url = reverse_lazy('employee-list')
    
    def get_queryset(self):
        return User.objects.filter(company=self.request.user.company)
    
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if user.id == request.user.id:
            messages.error(request, '❌ You cannot delete your own account!')
            return redirect('/company/employees/')
        
        name = f"{user.first_name} {user.last_name}"
        messages.success(request, f'✅ Employee {name} deleted successfully.')
        return super().delete(request, *args, **kwargs)
        
