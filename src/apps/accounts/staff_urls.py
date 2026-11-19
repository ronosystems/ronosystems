# apps/accounts/staff_urls.py
from django.urls import path
from . import staff_views

app_name = 'staff'  

urlpatterns = [
    path('employees/', staff_views.employee_list, name='employee-list'),
    path('employees/add/', staff_views.employee_create, name='add-employee'),
    path('employees/<int:pk>/', staff_views.employee_detail, name='employee-detail'),
    path('employees/<int:pk>/edit/', staff_views.employee_edit, name='edit-employee'),
    path('employees/<int:pk>/delete/', staff_views.employee_delete, name='delete-employee'),
    path('employees/<int:pk>/toggle-status/', staff_views.employee_toggle_status, name='toggle-employee-status'),
]