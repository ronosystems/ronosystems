from django.urls import path
from . import views

app_name = 'kuku_biz'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Flocks
    path('flocks/', views.flock_list, name='flock_list'),
    path('flocks/new/', views.flock_create, name='flock_create'),
    path('flocks/<int:pk>/', views.flock_detail, name='flock_detail'),

    # Egg Production
    path('eggs/', views.egg_list, name='egg_list'),
    path('eggs/new/', views.egg_create, name='egg_create'),

    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/new/', views.sale_create, name='sale_create'),
    path('sales/<int:pk>/mark-paid/', views.sale_mark_paid, name='sale_mark_paid'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('prices/', views.price_list, name='price_list'),
    path('prices/<int:pk>/delete/', views.price_delete, name='price_delete'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/new/', views.customer_create, name='customer_create'),  

    # Feed
    path('feed/', views.feed_list, name='feed_list'),
    path('feed/new/', views.feed_create, name='feed_create'), 

    # Mortality
    path('mortality/', views.mortality_list, name='mortality_list'),
    path('mortality/new/', views.mortality_create, name='mortality_create'),

    # Health
    path('health/', views.health_list, name='health_list'),
    path('health/new/', views.health_create, name='health_create'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/new/', views.expense_create, name='expense_create'),

    # Inventory
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/create/', views.inventory_create, name='inventory_create'),
    path('inventory/<int:pk>/edit/', views.inventory_edit, name='inventory_edit'),
    path('inventory/<int:pk>/delete/', views.inventory_delete, name='inventory_delete'),
    path('inventory/<int:pk>/adjust/', views.inventory_adjust, name='inventory_adjust'),
    path('inventory/transfer/', views.inventory_transfer, name='inventory_transfer'),

    # Reports
    path('reports/', views.reports, name='reports'),
]