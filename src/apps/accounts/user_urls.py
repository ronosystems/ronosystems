# apps/accounts/user_urls.py
from django.urls import path
from . import user_views

app_name = 'users'  # <-- Changed from 'employees' to 'users'

urlpatterns = [
    path('', user_views.employee_list, name='superadmin-employee-list'),
    path('<int:pk>/', user_views.employee_detail, name='superadmin-employee-detail'),
    path('create/', user_views.employee_create, name='superadmin-employee-create'),
    path('<int:pk>/edit/', user_views.employee_edit, name='superadmin-employee-edit'),
    path('<int:pk>/toggle-status/', user_views.employee_toggle_status, name='superadmin-employee-toggle-status'),
    path('<int:pk>/delete/', user_views.employee_delete, name='superadmin-employee-delete'),
]