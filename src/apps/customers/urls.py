from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    path('register/', views.customer_register, name='register'),
    path('success/<uuid:public_id>/', views.registration_success, name='registration-success'),

    # 👇 New Customer Auth Routes
    path('dashboard/', views.customer_dashboard, name='dashboard'),
    path('settings/', views.customer_settings, name='settings'), 
    path('profile/', views.customer_profile, name='profile'),
    path('logout/', views.customer_logout, name='logout'),
    path('loan/create/', views.customer_loan_create, name='loan_create'),
    path('orders/<str:order_number>/', views.customer_order_detail, name='order_detail'),

    # Coming Soon Placeholder Routes
    path('support/', views.coming_soon, {'page_name': 'support'}, name='support'),
    path('faqs/', views.coming_soon, {'page_name': 'faqs'}, name='faqs'),
    path('terms/', views.coming_soon, {'page_name': 'terms'}, name='terms'),
]