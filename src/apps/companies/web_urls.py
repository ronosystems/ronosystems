# apps/companies/urls.py

from django.urls import path

from . import web_views
from . import views  # noqa: F401  (kept for existing imports elsewhere)

app_name = 'companies'


urlpatterns = [
    # ============================================
    # COMPANY MANAGEMENT (Super Admin)
    # ============================================
    path('',        web_views.company_list,   name='company-list'),
    path('create/', web_views.company_create, name='company-create'),

    # ============================================
    # COMPANY DETAIL / EDIT / DELETE
    # ============================================
    path('<int:pk>/',        web_views.company_detail, name='company-detail'),
    path('<int:pk>/edit/',   web_views.company_edit,   name='company-edit'),
    path('<int:pk>/delete/', web_views.company_delete, name='company-delete'),

    # ============================================
    # EMPLOYEES
    # ============================================
    path(
        '<int:company_id>/employees/',
        web_views.company_employee_list,
        name='company-employees',
    ),

    # ============================================
    # JOIN REQUESTS (Company Admin / Super Admin)
    # ============================================
    path(
        '<int:company_id>/join-requests/',
        web_views.company_join_requests,
        name='company-join-requests',
    ),
    path(
        '<int:company_id>/join-requests/<int:request_id>/approve/',
        web_views.company_join_request_approve,
        name='company-join-request-approve',
    ),
    path(
        '<int:company_id>/join-requests/<int:request_id>/reset/',
        web_views.company_join_request_reset,
        name='company-join-request-reset',
    ),
    path(
        '<int:company_id>/join-requests/<int:request_id>/reject/',
        web_views.company_join_request_reject,
        name='company-join-request-reject',
    ),

    # ============================================
    # PAYMENTS — specific routes FIRST
    # ============================================
    path(
        '<int:pk>/payments/initiate/',
        web_views.company_payments_initiate,
        name='company-payments-initiate',
    ),
    path(
        '<int:pk>/payments/status/',
        web_views.company_payments_status,
        name='company-payments-status',
    ),
    path(
        '<int:pk>/payments/callback/',
        web_views.company_payments_callback,
        name='company-payments-callback',
    ),
    path(
        '<int:pk>/payments/dev-confirm/',
        web_views.company_payments_dev_confirm,
        name='company-payments-dev-confirm',
    ),

    # Catch-all payments page LAST
    path(
        '<int:pk>/payments/',
        web_views.company_payments,
        name='company-payments',
    ),

    # ============================================
    # MISC
    # ============================================
    path(
        'company/<int:pk>/verify-domain/',
        web_views.company_verify_domain,
        name='company-verify-domain',
    ),
]