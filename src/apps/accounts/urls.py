# apps/accounts/urls.py
from django.contrib.auth.views import PasswordResetConfirmView
from django.urls import path, reverse_lazy

from . import views
from . import staff_views, users_views

app_name = 'accounts'


urlpatterns = [
    path('post-login/', views.post_login_redirect, name='post-login-redirect'),
    path('select-company/', views.select_company, name='select-company'),

    # ===== PASSWORD RESET (used by staff invite emails) =====
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('account_login'),
        ),
        name='password_reset_confirm',
    ),

    # ===== COMPANY ADMIN - STAFF =====
    path('staff/', staff_views.staff_list, name='staff-list'),
    path('staff/create/', staff_views.staff_create, name='staff-create'),
    path('staff/<int:membership_id>/edit/', staff_views.staff_edit, name='staff-edit'),
    path('staff/<int:membership_id>/detail/', staff_views.staff_detail, name='staff-detail'),
    path('staff/<int:membership_id>/delete/', staff_views.staff_delete, name='staff-delete'),
    path('staff/<int:membership_id>/toggle/', staff_views.staff_toggle_status, name='staff-toggle'),
    path('staff/<int:membership_id>/resend-invite/',staff_views.staff_resend_invite, name='staff-resend-invite'),

    # ===== SUPER ADMIN - GLOBAL USERS =====
    path('users/', users_views.user_list, name='user-list'),
    path('users/create/', users_views.user_create, name='user-create'),
    path('users/<int:user_id>/', users_views.user_detail, name='user-detail'),
    path('users/<int:user_id>/edit/', users_views.user_edit, name='user-edit'),
    path('users/<int:user_id>/assign-admin/', users_views.assign_company_admin, name='assign-company-admin'),
    path('users/<int:user_id>/toggle/', users_views.user_toggle_status, name='user-toggle'),
    path('users/<int:user_id>/delete/', users_views.user_delete, name='user-delete'),
]