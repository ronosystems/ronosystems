from django.urls import path
from . import views

app_name = 'treasury'

urlpatterns = [
    # ============================================
    # DASHBOARD
    # ============================================
    path(
        '<int:company_id>/',
        views.treasury_dashboard,
        name='dashboard'
    ),
    
    # ============================================
    # BRANCH TREASURY
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/',
        views.branch_treasury,
        name='branch_treasury'
    ),
    
    # ============================================
    # BANK ACCOUNT CRUD
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/bank-account/create/',
        views.bank_account_create,
        name='bank_account_create'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/bank-account/<int:account_id>/edit/',
        views.bank_account_edit,
        name='bank_account_edit'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/bank-account/<int:account_id>/delete/',
        views.bank_account_delete,
        name='bank_account_delete'
    ),
    
    # ============================================
    # MPESA ACCOUNT CRUD
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/mpesa-account/create/',
        views.mpesa_account_create,
        name='mpesa_account_create'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/mpesa-account/<int:account_id>/edit/',
        views.mpesa_account_edit,
        name='mpesa_account_edit'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/mpesa-account/<int:account_id>/delete/',
        views.mpesa_account_delete,
        name='mpesa_account_delete'
    ),
    
    # ============================================
    # DAILY RECORDS
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/daily-records/',
        views.daily_records_list,
        name='daily_records_list'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/daily-record/create/',
        views.daily_record_create,
        name='daily_record_create'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/daily-record/<int:record_id>/edit/',
        views.daily_record_edit,
        name='daily_record_edit'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/daily-record/<int:record_id>/detail/',
        views.daily_record_detail,
        name='daily_record_detail'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/daily-record/<int:record_id>/delete/',
        views.daily_record_delete,
        name='daily_record_delete'
    ),
    
    # ============================================
    # MOVEMENTS (BOOST & TRANSFERS)
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/movements/',
        views.movements_list,
        name='movements_list'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/movement/create/',
        views.movement_create,
        name='movement_create'
    ),
    
    # ============================================
    # EXPORT
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/export/daily-records/',
        views.export_daily_records_csv,
        name='export_daily_records_csv'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/export/movements/',
        views.export_movements_csv,
        name='export_movements_csv'
    ),
    
    # ============================================
    # API ENDPOINTS
    # ============================================
    path(
        '<int:company_id>/branch/<int:branch_id>/api/balances/',
        views.api_get_balances,
        name='api_balances'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/api/daily-record/',
        views.api_get_daily_record,
        name='api_daily_record'
    ),
    path(
        '<int:company_id>/branch/<int:branch_id>/api/daily-record/<str:date>/',
        views.api_get_daily_record,
        name='api_daily_record_date'
    ),
]