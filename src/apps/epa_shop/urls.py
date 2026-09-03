from django.urls import path
from . import views
from . import product_views

app_name = 'epa_shop'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.EPADashboardView.as_view(), name='api_dashboard'),
    
    # Branches
    path('branches/', views.BranchListCreateView.as_view(), name='branch_list'),
    path('branches/<int:pk>/', views.BranchDetailView.as_view(), name='branch_detail'),
    
    # Suppliers
    path('suppliers/', views.SupplierListCreateView.as_view(), name='supplier_list'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier_detail'),
    
    # Categories
    path('categories/', views.CategoryListCreateView.as_view(), name='category_list'),
    path('categories/<int:pk>/', views.CategoryDetailView.as_view(), name='category_detail'),
    
    # Electronics
    path('electronics/', views.ElectronicListCreateView.as_view(), name='electronic_list'),
    path('electronics/<int:pk>/', views.ElectronicDetailView.as_view(), name='electronic_detail'),
    
    # Phones
    path('phones/', views.PhoneListCreateView.as_view(), name='phone_list'),
    path('phones/<int:pk>/', views.PhoneDetailView.as_view(), name='phone_detail'),
    
    # Accessories
    path('accessories/', views.AccessoryListCreateView.as_view(), name='accessory_list'),
    path('accessories/<int:pk>/', views.AccessoryDetailView.as_view(), name='accessory_detail'),
    
    # Sales
    path('sales/', views.SaleListCreateView.as_view(), name='sale_list'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale_detail'),
    path('sales/<int:pk>/invoice/', views.SaleInvoiceView.as_view(), name='sale_invoice'),
    
    # Customers
    path('customers/', views.CustomerListCreateView.as_view(), name='customer_list'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer_detail'),
    
    # Stock Movements
    path('stock-movements/', views.StockMovementListCreateView.as_view(), name='stock_movement_list'),
    path('stock-movements/<int:pk>/', views.StockMovementDetailView.as_view(), name='stock_movement_detail'),
    
    # Purchase Orders
    path('purchase-orders/', views.PurchaseOrderListCreateView.as_view(), name='purchase_order_list'),
    path('purchase-orders/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/receive/', views.PurchaseOrderReceiveView.as_view(), name='purchase_order_receive'),
    
    # Warranties
    path('warranties/', views.WarrantyListCreateView.as_view(), name='warranty_list'),
    path('warranties/<int:pk>/', views.WarrantyDetailView.as_view(), name='warranty_detail'),
    
    # Repairs
    path('repairs/', views.RepairListCreateView.as_view(), name='repair_list'),
    path('repairs/<int:pk>/', views.RepairDetailView.as_view(), name='repair_detail'),
    path('repairs/<int:pk>/complete/', views.RepairCompleteView.as_view(), name='repair_complete'),
]