from django.urls import path
from . import web_views
from . import views

app_name = 'companies'

urlpatterns = [
    # ============================================
    # Company Management (Super Admin)
    # ============================================
    path('', web_views.company_list, name='company-list'),
    path('create/', web_views.company_create, name='company-create'),

    # ============================================
    # Company detail + edit + delete
    # ============================================
    path('<int:pk>/',        web_views.company_detail, name='company-detail'),
    path('<int:pk>/edit/',   web_views.company_edit,   name='company-edit'),
    path('<int:pk>/delete/', web_views.company_delete, name='company-delete'),

    # ============================================
    # Employees
    # ============================================
    path('<int:company_id>/employees/', web_views.company_employee_list, name='company-employees'),

    # ============================================
    # Payments — specific routes FIRST
    # ============================================
    path('<int:pk>/payments/initiate/',     web_views.company_payments_initiate,     name='company-payments-initiate'),
    path('<int:pk>/payments/status/',       web_views.company_payments_status,       name='company-payments-status'),
    path('<int:pk>/payments/callback/',     web_views.company_payments_callback,     name='company-payments-callback'),
    path('<int:pk>/payments/dev-confirm/',  web_views.company_payments_dev_confirm,  name='company-payments-dev-confirm'),

    # Catch-all payments page LAST
    path('<int:pk>/payments/',              web_views.company_payments,              name='company-payments'),

    # ============================================
    # Misc
    # ============================================
    path('company/<int:pk>/verify-domain/', web_views.company_verify_domain, name='company-verify-domain'),
]