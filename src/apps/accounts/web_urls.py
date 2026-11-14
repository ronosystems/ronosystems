# apps/accounts/web_urls.py
from django.urls import path
from . import views_guest
from . import super_dashboard
from . import join_company as jc


app_name = 'web_accounts'  

urlpatterns = [
    path('no-access/', views_guest.no_access, name='no-access'),
    path('super-dashboard/', super_dashboard.super_admin_dashboard, name='super-admin-dashboard'),
    path('join-company/', jc.join_company, name='join-company'),
]