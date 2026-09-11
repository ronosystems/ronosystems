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
    path('<int:pk>/', web_views.company_detail, name='company-detail'),
    path('<int:pk>/edit/', web_views.company_edit, name='company-edit'),
    path('<int:pk>/delete/', web_views.company_delete, name='company-delete'),

    path('<int:pk>/payments/', web_views.company_payments, name='company-payments'),
    path('<int:pk>/payments/', web_views.company_payments, name='company-payments'),
    path('<int:pk>/payments/initiate/', web_views.company_payments_initiate, name='company-payments-initiate'),
    path('<int:pk>/payments/status/', web_views.company_payments_status, name='company-payments-status'),
    path('<int:pk>/payments/callback/', web_views.company_payments_callback, name='company-payments-callback'),
]