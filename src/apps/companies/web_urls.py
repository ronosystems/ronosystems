# apps/companies/urls.py
from django.urls import path
from . import web_views
from . import views 
from . import branches_views
from . import reports_views
from . import expenses_views
from . import settings_views
from apps.kuku_biz import settings_views as kuku_settings_views
from apps.companies import branches_views
from django.urls import path


app_name = 'companies'


urlpatterns = [
    path('mpesa/callback/', web_views.company_payments_callback, name='mpesa-callback'),
    path('apply/', web_views.apply_company, name='apply-company'),
    path('applications/', web_views.company_application_list, name='company-application-list'),
    path('applications/<int:app_id>/approve/', web_views.approve_company_application, name='approve-company-application'),
    path('applications/<int:app_id>/reject/', web_views.reject_company_application, name='reject-company-application'),


    path('', web_views.company_list, name='company-list'),
    path('create/', web_views.company_create, name='company-create'),
    path('<int:pk>/', web_views.company_detail, name='company-detail'),
    path('<int:pk>/edit/', web_views.company_edit, name='company-edit'),
    path('<int:pk>/delete/', web_views.company_delete, name='company-delete'),


    path('<int:company_id>/join-requests/', web_views.company_join_requests, name='company-join-requests'),
    path('<int:company_id>/join-requests/<int:request_id>/approve/', web_views.company_join_request_approve, name='company-join-request-approve'),
    path('<int:company_id>/join-requests/<int:request_id>/reset/', web_views.company_join_request_reset, name='company-join-request-reset'),
    path('<int:company_id>/join-requests/<int:request_id>/reject/', web_views.company_join_request_reject, name='company-join-request-reject'),


    path('<int:pk>/payments/initiate/', web_views.company_payments_initiate, name='company-payments-initiate'),
    path('<int:pk>/payments/status/', web_views.company_payments_status, name='company-payments-status'),
    path('<int:pk>/payments/dev-confirm/', web_views.company_payments_dev_confirm, name='company-payments-dev-confirm'),
    path('<int:pk>/payments/', web_views.company_payments, name='company-payments'),
    path('<int:pk>/payments/manual/', web_views.company_payments_manual, name='company-payments-manual'),


    path('payments/pending/', web_views.pending_payments, name='pending-payments'),
    path('payments/<int:sub_id>/approve/', web_views.approve_payment, name='approve-payment'),
    path('payments/<int:sub_id>/reject/', web_views.reject_payment, name='reject-payment'),


    path('company/<int:pk>/verify-domain/', web_views.company_verify_domain, name='company-verify-domain'),
    path('feedback/submit/', web_views.tenant_feedback_submit, name='tenant-feedback-submit'),
    path('hub/feedback/', web_views.hub_feedback_list, name='hub-feedback-list'),
    path('hub/feedback/<int:pk>/', web_views.hub_feedback_detail, name='hub-feedback-detail'),


    path('branches/', branches_views.branch_list, name='company-branches'),
    path('branches/create/', branches_views.branch_create, name='company-branch-create'),
    path('branches/<int:pk>/edit/', branches_views.branch_edit, name='company-branch-edit'),
    path('branches/<int:pk>/delete/', branches_views.branch_delete, name='company-branch-delete'),


    path('reports/', reports_views.reports_dashboard, name='company-reports-dashboard'),
    path('reports/daily/<str:date_str>/', reports_views.reports_daily_detail, name='company-reports-daily-detail'),
    path('reports/weekly/<int:year>/<int:week>/', reports_views.reports_weekly_detail, name='company-reports-weekly-detail'),
    path('reports/monthly/<int:year>/<int:month>/', reports_views.reports_monthly_detail, name='company-reports-monthly-detail'),
    path('reports/export/<str:report_type>/', reports_views.reports_export_csv, name='company-reports-export'),
    path('reports/export/daily/<str:date_str>/', reports_views.reports_export_csv, name='company-reports-export-daily'),
    path('reports/export/weekly/<int:year>/<int:week>/', reports_views.reports_export_csv, name='company-reports-export-weekly'),
    path('reports/export/monthly/<int:year>/<int:month>/', reports_views.reports_export_csv, name='company-reports-export-monthly'),
    path('reports/api/data/', reports_views.reports_api_data, name='company-reports-api-data'),


    # ── Expenses ──
    path('expenses/', expenses_views.expenses_dashboard, name='company-expenses-dashboard'),
    path('expenses/daily/<str:date_str>/', expenses_views.expenses_daily_detail, name='company-expenses-daily-detail'),
    path('expenses/salaries/', expenses_views.salaries_list, name='company-salaries-list'),
    path('expenses/salaries/create/', expenses_views.salary_create, name='company-salaries-create'),
    path('expenses/salaries/<int:pk>/edit/', expenses_views.salary_edit, name='company-salaries-edit'),
    path('expenses/rents/', expenses_views.rents_list, name='company-rents-list'),
    path('expenses/rents/create/', expenses_views.rent_create, name='company-rents-create'),
    path('expenses/rents/<int:pk>/edit/', expenses_views.rent_edit, name='company-rents-edit'),
    path('expenses/bills/', expenses_views.bills_list, name='company-bills-list'),
    path('expenses/bills/create/', expenses_views.bill_create, name='company-bills-create'),
    path('expenses/bills/<int:pk>/edit/', expenses_views.bill_edit, name='company-bills-edit'),
    path('expenses/general/', expenses_views.general_list, name='company-general-list'),
    path('expenses/general/create/', expenses_views.general_create, name='company-general-create'),
    path('expenses/general/<int:pk>/edit/', expenses_views.general_edit, name='company-general-edit'),
    path('expenses/<int:pk>/', expenses_views.expense_detail, name='company-expenses-detail'),
    path('expenses/<int:pk>/delete/', expenses_views.expense_delete, name='company-expenses-delete'),
    path('expenses/<int:pk>/approve/', expenses_views.expense_approve, name='company-expenses-approve'),
    path('expenses/<int:pk>/reject/', expenses_views.expense_reject, name='company-expenses-reject'),
    path('expenses/<int:pk>/paid/', expenses_views.expense_mark_paid, name='company-expenses-paid'),
    path('expenses/pay-all/', expenses_views.expenses_pay_all, name='company-expenses-pay-all'),
    path('expenses/all/', expenses_views.expenses_all, name='company-expenses-all'),


    path('settings/', settings_views.settings_dashboard, name='company-settings-dashboard'),
    path('settings/company/', settings_views.settings_company, name='company-settings-company'),
    path('settings/payment/', settings_views.settings_payment, name='company-settings-payment'),
    path('settings/receipt/', settings_views.settings_receipt, name='company-settings-receipt'),
    path('settings/preview-receipt/', settings_views.settings_preview_receipt, name='company-settings-preview-receipt'),
    path('settings/kuku/', kuku_settings_views.settings_kuku, name='company-settings-kuku'),
    path('settings/api/branch-mpesa/', settings_views.api_get_branch_mpesa_config, name='api_branch_mpesa'),
    path("company/gallery/upload/", settings_views.company_gallery_upload, name="company-gallery-upload"),
    path('settings/gallery/<int:pk>/delete/', settings_views.settings_gallery_delete, name='company-gallery-delete'),
]