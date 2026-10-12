# apps/workshop/urls.py

from django.urls import path
from . import views

app_name = 'workshop'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # My Work (technician's own queue)
    path('my-work/', views.my_work, name='my-work'),

    # Jobs
    path('jobs/', views.job_list, name='job-list'),
    path('jobs/new/', views.job_create, name='job-create'),
    path('jobs/<int:pk>/', views.job_detail, name='job-detail'),
    path('jobs/<int:pk>/edit/', views.job_edit, name='job-edit'),
    path('jobs/<int:pk>/status/', views.job_status_update, name='job-status-update'),
    path('jobs/<int:pk>/receipt/', views.job_receipt, name='job-receipt'),

    # Materials
    path('jobs/<int:job_pk>/materials/add/', views.material_add, name='material-add'),
    path('materials/<int:pk>/edit/', views.material_edit, name='material-edit'),
    path('materials/<int:pk>/delete/', views.material_delete, name='material-delete'),

    # Payments
    path('jobs/<int:job_pk>/payments/add/', views.payment_add, name='payment-add'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment-delete'),

    # Notes
    path('jobs/<int:job_pk>/notes/add/', views.note_add, name='note-add'),

    # Payouts (the admin table)
    path('payouts/', views.payout_list, name='payout-list'),
    path('payouts/<int:pk>/', views.payout_detail, name='payout-detail'),
    path('payouts/<int:pk>/edit/', views.payout_edit, name='payout-edit'),
    path('payouts/<int:pk>/pay/', views.payout_mark_paid, name='payout-mark-paid'),

    # Technician rates
    path('rates/', views.rate_list, name='rate-list'),
    path('rates/new/', views.rate_create, name='rate-create'),
    path('rates/<int:pk>/edit/', views.rate_edit, name='rate-edit'),
    path('rates/<int:pk>/delete/', views.rate_delete, name='rate-delete'),

    # Customers
    path('customers/', views.customer_list, name='customer-list'),
    path('customers/new/', views.customer_create, name='customer-create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer-edit'),
]