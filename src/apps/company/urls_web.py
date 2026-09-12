from django.urls import path
from . import views_web
from . import employee_views 
from . import branch_views
from . import reports_views
from . import expenses_views
from . import settings_views

urlpatterns = [
    # ============================================
    # Employee Management (Company Admin)
    # ============================================
    path('employees/', employee_views.employee_list, name='employee-list'),
    path('employees/add/', employee_views.employee_create, name='add-employee'),
    path('employees/<int:pk>/edit/', employee_views.employee_edit, name='edit-employee'),
    path('employees/<int:pk>/delete/', employee_views.employee_delete, name='delete-employee'),

    
    # ============================================
    # Branch Management
    # ============================================
    path('branches/', branch_views.branch_list, name='branch-list'),
    path('branches/create/', branch_views.branch_create, name='branch-create'),
    path('branches/<int:pk>/edit/', branch_views.branch_edit, name='branch-edit'),
    path('branches/<int:pk>/delete/', branch_views.branch_delete, name='branch-delete'),

    # ============================================
    # REPORTS
    # ============================================
    path('reports/', reports_views.reports_dashboard, name='company-reports-dashboard'),
    path('reports/daily/<str:date_str>/', reports_views.reports_daily_detail, name='company-reports-daily-detail'),
    path('reports/weekly/<int:year>/<int:week>/', reports_views.reports_weekly_detail, name='company-reports-weekly-detail'),
    path('reports/monthly/<int:year>/<int:month>/', reports_views.reports_monthly_detail, name='company-reports-monthly-detail'),
    path('reports/export/<str:report_type>/', reports_views.reports_export_csv, name='company-reports-export'),
    path('reports/export/daily/<str:date_str>/', reports_views.reports_export_csv, name='company-reports-export-daily'),
    path('reports/export/weekly/<int:year>/<int:week>/', reports_views.reports_export_csv, name='company-reports-export-weekly'),
    path('reports/export/monthly/<int:year>/<int:month>/', reports_views.reports_export_csv, name='company-reports-export-monthly'),
    path('reports/api/data/', reports_views.reports_api_data, name='company-reports-api-data'),

    # ============================================
    # EXPENSES
    # ============================================
    path('expenses/', expenses_views.expenses_dashboard, name='company-expenses-dashboard'),

    # Daily detail (used by dashboard's "View" button)
    path('expenses/daily/<str:date_str>/', expenses_views.expenses_daily_detail, name='company-expenses-daily-detail'),

    # Salaries
    path('expenses/salaries/', expenses_views.salaries_list, name='company-salaries-list'),
    path('expenses/salaries/create/', expenses_views.salary_create, name='company-salaries-create'),
    path('expenses/salaries/<int:pk>/edit/', expenses_views.salary_edit, name='company-salaries-edit'),

    # Rents
    path('expenses/rents/', expenses_views.rents_list, name='company-rents-list'),
    path('expenses/rents/create/', expenses_views.rent_create, name='company-rents-create'),
    path('expenses/rents/<int:pk>/edit/', expenses_views.rent_edit, name='company-rents-edit'),

    # Bills
    path('expenses/bills/', expenses_views.bills_list, name='company-bills-list'),
    path('expenses/bills/create/', expenses_views.bill_create, name='company-bills-create'),
    path('expenses/bills/<int:pk>/edit/', expenses_views.bill_edit, name='company-bills-edit'),

    # General
    path('expenses/general/', expenses_views.general_list, name='company-general-list'),
    path('expenses/general/create/', expenses_views.general_create, name='company-general-create'),
    path('expenses/general/<int:pk>/edit/', expenses_views.general_edit, name='company-general-edit'),

    # Shared detail / delete / status actions
    path('expenses/<int:pk>/', expenses_views.expense_detail, name='company-expenses-detail'),
    path('expenses/<int:pk>/delete/', expenses_views.expense_delete, name='company-expenses-delete'),
    path('expenses/<int:pk>/approve/', expenses_views.expense_approve, name='company-expenses-approve'),
    path('expenses/<int:pk>/reject/', expenses_views.expense_reject, name='company-expenses-reject'),
    path('expenses/<int:pk>/paid/', expenses_views.expense_mark_paid, name='company-expenses-paid'),

    # ============================================
    # SETTINGS
    # ============================================
    path('settings/', settings_views.settings_dashboard, name='company-settings-dashboard'),
    path('settings/company/', settings_views.settings_company, name='company-settings-company'),
    path('settings/payment/', settings_views.settings_payment, name='company-settings-payment'),
    path('settings/receipt/', settings_views.settings_receipt, name='company-settings-receipt'),
    path('settings/preview-receipt/', settings_views.settings_preview_receipt, name='company-settings-preview-receipt'),
    
]