from django.urls import path
from . import dashboard_views
from . import product_views
from . import pos_views
from . import sale_views
from . import category_views
from . import inventory_views
from . import finance_views

urlpatterns = [
    # ============================================
    # DASHBOARD
    # ============================================
    path('dashboard/', dashboard_views.epa_dashboard, name='epa-dashboard'),
    
    # ============================================
    # INVENTORY
    # ============================================
    path('inventory/', inventory_views.inventory_list, name='epa-inventory'),
    path('inventory/low-stock/', inventory_views.low_stock, name='epa-low-stock'),
    path('inventory/movement/', inventory_views.stock_movement, name='epa-stock-movement'),
    
    # ============================================
    # PRODUCTS - Full CRUD (Using Product Code)
    # ============================================
    path('products/', product_views.product_list, name='epa-products'),
    path('products/add/', product_views.product_create, name='epa-product-create'),
    path('products/<str:product_code>/', product_views.product_detail, name='epa-product-detail'),
    path('products/<str:product_code>/edit/', product_views.product_edit, name='epa-product-edit'),
    path('products/<str:product_code>/delete/', product_views.product_delete, name='epa-product-delete'),
    path('products/<str:product_code>/restock/', product_views.product_restock, name='epa-product-restock'),
    path('products/<str:product_code>/units/', product_views.product_units, name='epa-product-units'), 
    
    # ============================================
    # UNIT MANAGEMENT
    # ============================================
    path('unit/<int:unit_id>/edit/', product_views.unit_edit, name='epa-unit-edit'),
    path('unit/<int:unit_id>/transfer/', product_views.unit_transfer, name='epa-unit-transfer'),
    path('products/<str:product_code>/unit/<str:identifier>/delete/', product_views.unit_delete, name='epa-unit-delete'),
    
    # ============================================
    # ALL UNITS PAGES
    # ============================================
    path('units/phones/', product_views.all_phone_units, name='epa-all-phone-units'),
    path('units/electronics/', product_views.all_electronic_units, name='epa-all-electronic-units'),
    path('accessories/', product_views.accessory_list, name='epa-accessories'),
    
    # ============================================
    # SALE MANAGEMENT - Use pk (int) for receipts
    # ============================================
    path('sale/<int:sale_id>/reverse/', product_views.unit_reverse_sale, name='epa-sale-reverse'),
    path('sale/<int:sale_id>/complete/', sale_views.sale_complete, name='epa-sale-complete'),
    
    # ============================================
    # POINT OF SALE (POS)
    # ============================================
    path('pos/', pos_views.pos_dashboard, name='epa-pos'),
    path('pos/search/', pos_views.pos_search_products, name='epa-pos-search'),
    path('pos/search-imei/', pos_views.pos_search_imei, name='epa-pos-search-imei'),
    path('pos/branches/', sale_views.get_branches, name='epa-pos-branches'),
    
    # ============================================
    # SALE MANAGEMENT
    # ============================================
    path('sales/', sale_views.sale_list, name='epa-sales'),
    path('sales/add/', sale_views.sale_create, name='epa-sale-create'),
    path('sales/<int:pk>/', sale_views.sale_detail, name='epa-sale-detail'),
    path('sales/<int:pk>/edit/', sale_views.sale_edit, name='epa-sale-edit'), 
    path('sale/process/', sale_views.process_sale, name='epa-sale-process'),
    
    # Receipt views - support both pk and company_sale_id
    path('sale/receipt/<int:pk>/', sale_views.sale_receipt, name='epa-sale-receipt'),
    path('sale/receipt/<str:company_sale_id>/', sale_views.sale_receipt_by_id, name='epa-sale-receipt-by-id'),
    
    # Reverse sale - support both pk and company_sale_id
    path('sale/<int:sale_id>/reverse/', product_views.unit_reverse_sale, name='epa-sale-reverse'),
    path('sale/<str:company_sale_id>/reverse/', product_views.unit_reverse_sale, name='epa-sale-reverse-by-id'),
    
    # Complete sale - support both pk and company_sale_id
    path('sale/<int:sale_id>/complete/', sale_views.sale_complete, name='epa-sale-complete'),
    path('sale/<str:company_sale_id>/complete/', sale_views.sale_complete, name='epa-sale-complete-by-id'),
    path('sale/history/', sale_views.sale_history, name='epa-sale-history'),
    path('sale/<int:pk>/delete/', sale_views.sale_delete, name='epa-sale-delete'),

    # ============================================
    # SINGLE ITEM SALE
    # ============================================
    path('sales/single/', sale_views.sale_create_single, name='epa-sale-create-single'),
    path('sale/search-units/', sale_views.sale_search_units, name='epa-sale-search-units'),
    path('sale/get-unit/', sale_views.sale_get_unit_by_identifier, name='epa-sale-get-unit'),
    path('sale/process-single/', sale_views.sale_process_single, name='epa-sale-process-single'),
    path('sales/pending/', sale_views.sale_pending_list, name='epa-sales-pending'),
    
    # ============================================
    # CATEGORIES - Full CRUD
    # ============================================
    path('categories/', category_views.category_list, name='epa-categories'),
    path('categories/add/', category_views.category_create, name='epa-category-create'),
    path('categories/<int:pk>/edit/', category_views.category_edit, name='epa-category-edit'),
    path('categories/<int:pk>/delete/', category_views.category_delete, name='epa-category-delete'),
    path('categories/<int:pk>/products/', category_views.category_products, name='epa-category-products'),
    path('categories/<int:pk>/toggle-status/', category_views.category_toggle_status, name='epa-category-toggle-status'),
    
    # ============================================
    # FINANCE - Full CRUD (EPA Shop Finance)
    # ============================================
    path('finance/', finance_views.finance_dashboard, name='finance-dashboard'),
    path('finance/cogs-transactions/', finance_views.cogs_transactions, name='finance-cogs-transactions'),
    path('finance/cogs-accounts/', finance_views.cogs_accounts, name='finance-cogs-accounts'),
    path('finance/cogs-accounts/create/', finance_views.cogs_account_create, name='finance-cogs-account-create'),
    path('finance/purchases/', finance_views.purchase_records, name='finance-purchase-records'),
    path('finance/purchases/create/', finance_views.purchase_create, name='finance-purchase-create'),
    path('finance/purchases/<int:pk>/', finance_views.purchase_detail, name='finance-purchase-detail'),
    path('finance/cogs-report/', finance_views.cogs_report, name='finance-cogs-report'),
    path('finance/api/data/', finance_views.finance_api_data, name='finance-api-data'),
    path('finance/api/balance/', finance_views.api_cogs_balance, name='finance-api-balance'),
    path('finance/export/', finance_views.export_cogs_report, name='finance-export-cogs'),
    path('finance/debug/', finance_views.debug_cogs_balance, name='finance-debug'),

    # ============================================
    # FINANCE - COGS Detail Views
    # ============================================
    path('finance/cogs-daily/<str:date_str>/', finance_views.cogs_daily_detail, name='finance-cogs-daily-detail'),
    path('finance/cogs-weekly/<int:year>/<int:week>/', finance_views.cogs_weekly_detail, name='finance-cogs-weekly-detail'),
    path('finance/cogs-monthly/<int:year>/<int:month>/', finance_views.cogs_monthly_detail, name='finance-cogs-monthly-detail'),
]