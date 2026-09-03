# apps/company/urls.py

from django.urls import path
from . import employee_views

urlpatterns = [
    # Employee management
    path('employees/', employee_views.employee_list, name='employee-list'),
    path('employees/add/', employee_views.employee_create, name='add-employee'),
    path('employees/<int:pk>/', employee_views.employee_detail, name='employee-detail'),
    path('employees/<int:pk>/edit/', employee_views.employee_edit, name='edit-employee'),
    path('employees/<int:pk>/delete/', employee_views.employee_delete, name='delete-employee'),
    path('employees/<int:pk>/toggle-status/', employee_views.employee_toggle_status, name='toggle-employee-status'),
]