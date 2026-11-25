# apps/accounts/urls.py
from django.urls import path
from . import staff_views, users_views

app_name = 'accounts'

urlpatterns = [
    # ===== COMPANY ADMIN - STAFF =====
    path('staff/', staff_views.staff_list, name='staff-list'),
    path('staff/create/', staff_views.staff_create, name='staff-create'),
    path('staff/<int:user_id>/', staff_views.staff_detail, name='staff-detail'),
    path('staff/<int:user_id>/edit/', staff_views.staff_edit, name='staff-edit'),
    path('staff/<int:user_id>/toggle/', staff_views.staff_toggle_status, name='staff-toggle'),
    path('staff/<int:user_id>/delete/', staff_views.staff_delete, name='staff-delete'),

    # ===== SUPER ADMIN - GLOBAL USERS =====
    path('users/', users_views.user_list, name='user-list'),
    path('users/create/', users_views.user_create, name='user-create'),
    path('users/<int:user_id>/', users_views.user_detail, name='user-detail'),
    path('users/<int:user_id>/edit/', users_views.user_edit, name='user-edit'),
    path('users/<int:user_id>/assign-admin/', users_views.assign_company_admin, name='assign-company-admin'),
    path('users/<int:user_id>/toggle/', users_views.user_toggle_status, name='user-toggle'),
    path('users/<int:user_id>/delete/', users_views.user_delete, name='user-delete'),
]