from django.urls import path
from . import employee_views

app_name = 'employees'

urlpatterns = [
    # ============================================
    # Employee Management (Super Admin)
    # ============================================
    path('', employee_views.employee_list, name='superadmin-employee-list'),
    path('<int:pk>/', employee_views.employee_detail, name='superadmin-employee-detail'),
    path('<int:pk>/edit/', employee_views.employee_edit, name='superadmin-employee-edit'),
    path('<int:pk>/delete/', employee_views.employee_delete, name='superadmin-employee-delete'),
    path('<int:pk>/toggle-status/', employee_views.employee_toggle_status, name='superadmin-employee-toggle-status'),
]