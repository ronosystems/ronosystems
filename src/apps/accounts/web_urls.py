# apps/accounts/web_urls.py
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect
from django.urls import path
from . import views_guest
from . import super_dashboard
from . import join_company as jc


app_name = 'web_accounts'  

def logout_view(request):
    """GET /auth/logout/ - inatumiwa na base.html + kuku_base.html"""
    auth_logout(request)
    request.session.pop('support_mode', None)
    request.session.pop('viewing_company_id', None)
    return redirect('/')

urlpatterns = [
    path('logout/', logout_view, name='logout'),
    path('no-access/', views_guest.no_access, name='no-access'),
    path('super-dashboard/', super_dashboard.super_admin_dashboard, name='super-admin-dashboard'),
    path('join-company/', jc.join_company, name='join-company'),
]