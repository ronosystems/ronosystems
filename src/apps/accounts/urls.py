# apps/accounts/urls.py

from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.urls import path, reverse_lazy
from django.contrib.auth.forms import PasswordResetForm
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

from . import views
from . import staff_views, users_views

app_name = 'accounts'


# ============================================================
# CUSTOM PASSWORD RESET FORM
# ============================================================
class CustomPasswordResetForm(PasswordResetForm):
    """Adds company branding (name + logo) to the reset email."""

    def save(
        self,
        domain_override=None,
        subject_template_name='registration/password_reset_subject.txt',
        email_template_name='registration/password_reset_email.html',
        use_https=False,
        token_generator=None,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        if not token_generator:
            token_generator = default_token_generator

        for user in self.get_users(self.cleaned_data["email"]):
            company_name = (
                user.company.name
                if getattr(user, 'company', None)
                else "RonoSystems"
            )
            user_display = user.first_name or user.username

            company_logo = None
            if getattr(user, 'company', None) and user.company.logo:
                company_logo = user.company.logo.url

            context = {
                'email': user.email,
                'domain': (domain_override
                           or (request.get_host() if request else 'localhost')),
                'site_name': company_name,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'user': user,
                'token': token_generator.make_token(user),
                'protocol': 'https' if use_https else 'http',
                'user_display': user_display,
                'current_site': {'name': company_name},
                'logo_url': company_logo,
            }
            if extra_email_context:
                context.update(extra_email_context)

            self.send_mail(
                subject_template_name,
                email_template_name,
                context,
                from_email,
                user.email,
                html_email_template_name=html_email_template_name,
            )


# ============================================================
# API ROUTES  — all under /api/ to avoid collisions with HTML views
# ============================================================
api_urlpatterns = [
    # Multi-tenant auth
    path('register/',       views.RegisterView.as_view(),       name='api-register'),
    path('login/',          views.LoginView.as_view(),          name='api-login'),
    path('logout/',         views.LogoutView.as_view(),         name='api-logout'),
    path('profile/',        views.UserProfileView.as_view(),    name='api-profile'),
    path('role-info/',      views.UserRoleInfoView.as_view(),   name='api-role-info'),

    # Multi-tenant profiles
    path('memberships/',    views.MyMembershipsView.as_view(),  name='api-my-memberships'),
    path('switch-company/', views.SwitchCompanyView.as_view(),  name='api-switch-company'),

    # Admin (API)
    path('users/',                       views.UserListView.as_view(),          name='api-user-list'),
    path('company/users/',               views.CompanyUserListView.as_view(),   name='api-company-users'),
    path('users/<int:user_id>/role/',    views.UserRoleUpdateView.as_view(),    name='api-user-role'),
    path('users/<int:user_id>/company/', views.UserCompanyUpdateView.as_view(), name='api-user-company'),
    path('users/<int:user_id>/branch/',  views.UserBranchUpdateView.as_view(),  name='api-user-branch'),
    path('users/<int:user_id>/',         views.UserDeleteView.as_view(),        name='api-user-delete'),
    path('users/<int:user_id>/status/',  views.UserStatusToggleView.as_view(),  name='api-user-status'),

    # Password (API — sends JSON response, custom URL)
    path('password/change/', views.UserChangePasswordView.as_view(), name='api-password-change'),
    path('password/forgot/', views.UserPasswordResetView.as_view(),  name='api-password-forgot'),
]


# ============================================================
# HTML / TEMPLATE ROUTES
# ============================================================
urlpatterns = [
    # ---------- Post-login / company selector ----------
    path('post-login/',     views.post_login_redirect, name='post-login'),
    path('select-company/', views.select_company,      name='select-company'),

    # ---------- API (namespaced) ----------
    path('api/', __import__('django.urls', fromlist=['include']).include(api_urlpatterns)),

    # ---------- Password Reset (Django template flow) ----------
    path(
        'password/reset/',
        PasswordResetView.as_view(
            template_name='accounts/password_reset_form.html',
            email_template_name='emails/password_reset_email.html',
            subject_template_name='emails/password_reset_subject.txt',
            form_class=CustomPasswordResetForm,
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password/reset/done/',
        PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password/reset/complete/',
        PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # ---------- Company Admin — Staff (HTML) ----------
    path('staff/',                              staff_views.staff_list,          name='staff-list'),
    path('staff/create/',                       staff_views.staff_create,        name='staff-create'),
    path('staff/<int:membership_id>/edit/',     staff_views.staff_edit,          name='staff-edit'),
    path('staff/<int:membership_id>/detail/',   staff_views.staff_detail,        name='staff-detail'),
    path('staff/<int:membership_id>/delete/',   staff_views.staff_delete,        name='staff-delete'),
    path('staff/<int:membership_id>/toggle/',   staff_views.staff_toggle_status, name='staff-toggle'),
    path('staff/<int:membership_id>/resend-invite/', staff_views.staff_resend_invite, name='staff-resend-invite'),

    # ---------- Super Admin — Global users (HTML) ----------
    path('manage/users/',                           users_views.user_list,             name='user-list'),
    path('manage/users/create/',                    users_views.user_create,           name='user-create'),
    path('manage/users/<int:user_id>/',             users_views.user_detail,           name='user-detail'),
    path('manage/users/<int:user_id>/edit/',        users_views.user_edit,             name='user-edit'),
    path('manage/users/<int:user_id>/assign-admin/', users_views.assign_company_admin, name='assign-company-admin'),
    path('manage/users/<int:user_id>/toggle/',      users_views.user_toggle_status,    name='user-toggle'),
    path('manage/users/<int:user_id>/delete/',      users_views.user_delete,           name='user-delete'),
]