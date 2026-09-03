from django.urls import path
from . import login_views
from . import super_dashboard

urlpatterns = [
    # Web Login/Logout/Register
    path('login/', login_views.login_page, name='login'),
    path('logout/', login_views.logout_view, name='logout'),
    path('register/', login_views.register_page, name='register'),
    path('forgot-password/', login_views.forgot_password_page, name='forgot-password'),
    path('reset-password/<uidb64>/<token>/', login_views.reset_password_page, name='reset-password'),
    
    # Super Admin Dashboard
    path('super-dashboard/', super_dashboard.super_admin_dashboard, name='super-admin-dashboard'),
]
