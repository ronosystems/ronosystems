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
    path('flocks/<int:pk>/edit/', views.flock_edit, name='flock_edit'),
    path('flocks/<int:pk>/delete/', views.flock_delete, name='flock_delete'),
   
    # Bird sales
    path('bird-sales/', views.bird_sale_list, name='bird_sale_list'),
    path('bird-sales/create/', views.bird_sale_create, name='bird_sale_create'),
    path('bird-sales/<int:pk>/edit/', views.bird_sale_edit, name='bird_sale_edit'),
    path('bird-sales/<int:pk>/delete/', views.bird_sale_delete, name='bird_sale_delete'),
    path('bird-sales/<int:pk>/receipt/', views.bird_sale_receipt, name='bird_sale_receipt'),
    path('bird-sales/<int:pk>/mark-paid/', views.bird_sale_mark_paid, name='bird_sale_mark_paid'),

    # Egg production
    path('eggs/', views.egg_list, name='egg_list'),
    path('eggs/create/', views.egg_create, name='egg_create'),
    path('eggs/<int:pk>/edit/', views.egg_edit, name='egg_edit'),
    path('eggs/<int:pk>/delete/', views.egg_delete, name='egg_delete'),

    # Sales
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/new/', views.sale_create, name='sale_create'),
    path('sales/<int:pk>/mark-paid/', views.sale_mark_paid, name='sale_mark_paid'),
    path('sales/<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('sales/<int:pk>/receipt/', views.sale_receipt, name='sale_receipt'),
    path('prices/', views.price_list, name='price_list'),
    path('prices/<int:pk>/delete/', views.price_delete, name='price_delete'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/new/', views.customer_create, name='customer_create'),  

    # Feed
    path('feed-types/', views.feed_type_list, name='feed_type_list'),
    path('feed-types/new/', views.feed_type_create, name='feed_type_create'),
    path('feed-types/<int:pk>/edit/', views.feed_type_edit, name='feed_type_edit'),
    path('feed-types/<int:pk>/delete/', views.feed_type_delete, name='feed_type_delete'),
    path('feed/', views.feed_list, name='feed_list'),
    path('feed/new/', views.feed_create, name='feed_create'),
    path('feed/consume/', views.feed_consume, name='feed_consume'),
    path('feed/<int:pk>/edit/', views.feed_edit, name='feed_edit'),
    path('feed/<int:pk>/delete/', views.feed_delete, name='feed_delete'),
    path('feed/<int:pk>/mark-paid/', views.feed_mark_paid, name='feed_mark_paid'),
    path('feed/consumption/', views.feed_consumption_list, name='feed_consumption_list'),
    path('feed/consumption/<int:pk>/delete/', views.feed_consumption_delete, name='feed_consumption_delete'),

    # Mortality
    path('mortality/', views.mortality_list, name='mortality_list'),
    path('mortality/new/', views.mortality_create, name='mortality_create'),
    path('mortality/<int:pk>/delete/', views.mortality_delete, name='mortality_delete'),

    # Health
    path('health/', views.health_list, name='health_list'),
    path('health/new/', views.health_create, name='health_create'),
    path('health/<int:pk>/delete/', views.health_delete, name='health_delete'),

    # Vaccine types (catalog)
    path('health/vaccines/', views.vaccine_type_list, name='vaccine_type_list'),
    path('health/vaccines/new/', views.vaccine_type_create, name='vaccine_type_create'),
    path('health/vaccines/<int:pk>/edit/', views.vaccine_type_edit, name='vaccine_type_edit'),
    path('health/vaccines/<int:pk>/delete/', views.vaccine_type_delete, name='vaccine_type_delete'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/new/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('expenses/<int:pk>/mark-paid/', views.expense_mark_paid, name='expense_mark_paid'),

    # Inventory — separated by category
    path('inventory/', views.inventory_hub, name='inventory_hub'),
    path('inventory/eggs/', views.egg_inventory, name='egg_inventory'),
    path('inventory/feed/', views.feed_inventory, name='feed_inventory'),
    path('inventory/vaccines/', views.vaccine_inventory, name='vaccine_inventory'),
    path('inventory/other/', views.other_inventory, name='other_inventory'),

    # Shared create/edit/delete (unchanged)
    path('inventory/create/', views.inventory_create, name='inventory_create'),
    path('inventory/<int:pk>/edit/', views.inventory_edit, name='inventory_edit'),
    path('inventory/<int:pk>/delete/', views.inventory_delete, name='inventory_delete'),
    path('inventory/<int:pk>/adjust/', views.inventory_adjust, name='inventory_adjust'),
    path('inventory/transfer/', views.inventory_transfer, name='inventory_transfer'),

    # Reports
    path('reports/', views.reports, name='reports'),
]