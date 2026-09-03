from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/', views.SupermarketDashboardView.as_view(), name='supermarket-dashboard'),
    
    # Categories
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list'),
    path('categories/<int:pk>/', views.CategoryDetailView.as_view(), name='category-detail'),
    
    # Suppliers
    path('suppliers/', views.SupplierListCreateView.as_view(), name='supplier-list'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier-detail'),
    
    # Products
    path('products/', views.ProductListCreateView.as_view(), name='product-list'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    
    # Inventory
    path('inventory/', views.InventoryListView.as_view(), name='inventory-list'),
    path('inventory/low-stock/', views.LowStockView.as_view(), name='low-stock'),
    
    # Purchase Orders
    path('purchase-orders/', views.PurchaseOrderListCreateView.as_view(), name='purchase-order-list'),
    path('purchase-orders/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
    
    # Sales
    path('sales/', views.SaleListCreateView.as_view(), name='sale-list'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale-detail'),
    
    # Customers
    path('customers/', views.CustomerListCreateView.as_view(), name='customer-list'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    
    # Discounts
    path('discounts/', views.DiscountListCreateView.as_view(), name='discount-list'),
    path('discounts/<int:pk>/', views.DiscountDetailView.as_view(), name='discount-detail'),
]
