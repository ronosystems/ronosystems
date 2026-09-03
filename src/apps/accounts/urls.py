# apps/users/urls.py

from django.urls import path, include
from . import views
from . import role_views


urlpatterns = [
    # ============================================
    # AUTHENTICATION
    # ============================================
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # ============================================
    # USER PROFILE
    # ============================================
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
    path('change-password/', views.UserChangePasswordView.as_view(), name='change-password'),
    path('reset-password/', views.UserPasswordResetView.as_view(), name='reset-password'),
    
    # ============================================
    # USER MANAGEMENT (Super Admin only)
    # ============================================
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/<int:user_id>/role/', views.UserRoleUpdateView.as_view(), name='user-role-update'),
    path('users/<int:user_id>/company/', views.UserCompanyUpdateView.as_view(), name='user-company-update'),
    path('users/<int:user_id>/delete/', views.UserDeleteView.as_view(), name='user-delete'),
    path('users/<int:user_id>/toggle-status/', views.UserStatusToggleView.as_view(), name='user-toggle-status'),
    path('users/<int:user_id>/branch/', views.UserBranchUpdateView.as_view(), name='user-branch-update'),
    
    # ============================================
    # ROLE MANAGEMENT (Company Admin & Super Admin)
    # ============================================
    path('role-info/', role_views.UserRoleInfoView.as_view(), name='role-info'),
    path('users/company/', role_views.CompanyUserListView.as_view(), name='company-users'),
    path('users/<int:user_id>/update-role/', role_views.UserRoleUpdateView.as_view(), name='update-role'),
    
    # ============================================
    # COMPANY USERS (Company Admin)
    # ============================================
    path('company/users/', views.CompanyUserListView.as_view(), name='company-users'),
]