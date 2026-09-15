from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# Canonical web auth URLs (avoid colliding with API routes like /api/auth/login/)
WEB_LOGIN_URL = '/auth/login/'


# ============================================================
# LOGIN
# ============================================================
def login_page(request):
    """Web login page with automatic dashboard routing."""

    if request.user.is_authenticated:
        return redirect_dashboard(request, request.user)

    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        remember_me = request.POST.get('remember_me')

        if not email or not password:
            messages.error(request, 'Please enter both email and password.')
            return render(request, 'accounts/login.html')

        # Primary: authenticate with email as username
        user = authenticate(request, username=email, password=password)

        # Fallback: look up by email, then authenticate with the real username
        if user is None:
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user is not None:
            if not user.is_active:
                messages.error(request, 'Your account is disabled. Please contact support.')
                return render(request, 'accounts/login.html')

            login(request, user)

            # Session expiry: 0 = expire on browser close, 1209600 = 2 weeks
            request.session.set_expiry(1209600 if remember_me else 0)

            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect_dashboard(request, user)
        else:
            messages.error(request, 'Invalid email or password. Please try again.')

    return render(request, 'accounts/login.html')


# ============================================================
# DASHBOARD ROUTING
# ============================================================
def redirect_dashboard(request, user):
    """Redirect user to the appropriate dashboard based on role, company, and business type."""

    role = getattr(user, 'role', None)

    # Super admin
    if role == 'super_admin':
        return HttpResponseRedirect(reverse('super-admin-dashboard'))

    # Company users
    company = getattr(user, 'company', None)
    if not company:
        return HttpResponseRedirect('/no-access/')

    business_type = getattr(company, 'business_type', None)

    if business_type and getattr(business_type, 'name', None):
        business_name = business_type.name.lower()

        if 'epa' in business_name or 'electronics' in business_name:
            return HttpResponseRedirect('/epa_shop/dashboard/')
        if 'supermarket' in business_name or 'grocery' in business_name:
            return HttpResponseRedirect('/supermarket/dashboard/')
        if 'healthcare' in business_name or 'medical' in business_name:
            return HttpResponseRedirect('/healthcare/dashboard/')
        if 'education' in business_name or 'school' in business_name:
            return HttpResponseRedirect('/education/dashboard/')
        if 'restaurant' in business_name or 'food' in business_name:
            return HttpResponseRedirect('/restaurant/dashboard/')
        if 'retail' in business_name:
            return HttpResponseRedirect('/retail/dashboard/')

    # Fallback
    return HttpResponseRedirect('/dashboard/general/')


# ============================================================
# LOGOUT
# ============================================================
@login_required
def logout_view(request):
    """Logout user and redirect to the web login page."""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return HttpResponseRedirect(WEB_LOGIN_URL)


# ============================================================
# REGISTER
# ============================================================
def register_page(request):
    """
    Web registration page.

    Two flows:

    CASE A — User provides a Company ID
      → validate the code against Company.company_id
      → create a CompanyJoinRequest (status='pending')
      → company admin approves → User is created then
      → if a previous request was REJECTED, allow re-application
        (the existing row is reset back to 'pending')

    CASE B — User leaves Company ID blank
      → create a guest User directly (is_active=False, role='guest')
      → super admin approves via Django admin

    Common validation (email/username uniqueness, password match) runs first.
    """

    if request.method == 'POST':
        first_name       = (request.POST.get('first_name') or '').strip()
        last_name        = (request.POST.get('last_name') or '').strip()
        email            = (request.POST.get('email') or '').strip().lower()
        username         = (request.POST.get('username') or '').strip()
        password         = request.POST.get('password') or ''
        confirm_password = request.POST.get('confirm_password') or ''
        phone            = (request.POST.get('phone') or '').strip()
        company_id_input = (request.POST.get('company_id') or '').strip().upper()

        # ---------- Required fields ----------
        if not all([email, username, password, confirm_password]):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'accounts/register.html', {'form_data': request.POST})

        # ---------- Password checks ----------
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html', {'form_data': request.POST})

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'accounts/register.html', {'form_data': request.POST})

        # =========================================================
        # CASE A — COMPANY ID PROVIDED → join request flow
        # =========================================================
        if company_id_input:
            from apps.companies.models import Company, CompanyJoinRequest

            # ---------- Resolve the company ----------
            company = Company.objects.filter(company_id__iexact=company_id_input).first()

            if not company:
                messages.error(
                    request,
                    f'Company ID "{company_id_input}" was not found. '
                    'Please check and try again, or leave the field blank.'
                )
                return render(request, 'accounts/register.html', {'form_data': request.POST})

            # ---------- Check for an existing request for this (company, email) ----------
            existing = CompanyJoinRequest.objects.filter(
                company=company, email__iexact=email
            ).first()

            # ----- Pending: don't allow a second request -----
            if existing and existing.status == 'pending':
                messages.error(
                    request,
                    'You already have a pending request for this company. '
                    'Please wait for the company admin to review it.'
                )
                return render(request, 'accounts/register.html', {'form_data': request.POST})

            # ----- Approved: the user already has (or will have) an account -----
            if existing and existing.status == 'approved':
                messages.error(
                    request,
                    'This email is already registered with this company. '
                    'Try logging in instead, or use a different email.'
                )
                return render(request, 'accounts/register.html', {'form_data': request.POST})

            # ----- Rejected: allow re-application by resetting the row -----
            if existing and existing.status == 'rejected':
                # Only block if a User account has since been created with this email
                if User.objects.filter(email__iexact=email).exists():
                    messages.error(
                        request,
                        'This email is already in use. Please use a different email.'
                    )
                    return render(request, 'accounts/register.html', {'form_data': request.POST})

                # Only block if the username is now taken
                if User.objects.filter(username__iexact=username).exists():
                    messages.error(request, 'Username already taken.')
                    return render(request, 'accounts/register.html', {'form_data': request.POST})

                try:
                    existing.first_name       = first_name
                    existing.last_name        = last_name
                    existing.username         = username
                    existing.phone            = phone
                    existing.password_hash    = make_password(password)
                    existing.requested_role   = 'company_staff'
                    existing.status           = 'pending'
                    existing.reviewed_by      = None
                    existing.reviewed_at      = None
                    existing.rejection_reason = ''
                    existing.save()

                    messages.success(
                        request,
                        f'Your request to join "{company.name}" has been re-submitted. '
                        'You will be able to log in once the company admin approves it.'
                    )
                    return redirect(WEB_LOGIN_URL)

                except Exception as e:
                    logger.exception("Re-application failed for %s", email)
                    messages.error(request, f'Error submitting request: {e}')
                    return render(request, 'accounts/register.html', {'form_data': request.POST})

            # ----- No existing request: new email/username uniqueness check -----
            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, 'Email already registered.')
                return render(request, 'accounts/register.html', {'form_data': request.POST})

            if User.objects.filter(username__iexact=username).exists():
                messages.error(request, 'Username already taken.')
                return render(request, 'accounts/register.html', {'form_data': request.POST})

            # ----- Create a fresh join request -----
            try:
                CompanyJoinRequest.objects.create(
                    company=company,
                    first_name=first_name,
                    last_name=last_name,
                    username=username,
                    email=email,
                    phone=phone,
                    password_hash=make_password(password),
                    requested_role='company_staff',
                    status='pending',
                )
                messages.success(
                    request,
                    f'Your request to join "{company.name}" has been submitted. '
                    'You will be able to log in once the company admin approves it.'
                )
                return redirect(WEB_LOGIN_URL)

            except Exception as e:
                logger.exception("Join request failed for %s", email)
                messages.error(request, f'Error submitting request: {e}')
                return render(request, 'accounts/register.html', {'form_data': request.POST})

        # =========================================================
        # CASE B — NO Company ID → create guest user (pending super admin)
        # =========================================================

        # Uniqueness (guest path)
        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'accounts/register.html', {'form_data': request.POST})

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'accounts/register.html', {'form_data': request.POST})

        try:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role='guest',
                is_active=False,   # requires super admin approval
            )
            messages.success(
                request,
                'Account created! Please wait for verification — '
                'this may take up to 48 hours.'
            )
            return redirect(WEB_LOGIN_URL)

        except Exception as e:
            logger.exception("Registration failed for %s", email)
            messages.error(request, f'Error creating account: {e}')
            return render(request, 'accounts/register.html', {'form_data': request.POST})

    return render(request, 'accounts/register.html')

# ============================================================
# FORGOT PASSWORD
# ============================================================
def forgot_password_page(request):
    """Request a password reset link via email."""

    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()

        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'accounts/forgot_password.html')

        try:
            user = User.objects.get(email__iexact=email)

            # Build reset link
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = request.build_absolute_uri(
                reverse('reset-password', kwargs={'uidb64': uid, 'token': token})
            )

            # Render HTML email
            system_name = getattr(settings, 'SYSTEM_NAME', 'RonoSystems')
            html_message = render_to_string('accounts/emails/password_reset_email.html', {
                'user': user,
                'reset_link': reset_link,
                'system_name': system_name,
            })

            # Send email (never crash the request if mail fails)
            try:
                send_mail(
                    subject=f"Password Reset Request - {system_name}",
                    message=f"Reset your password: {reset_link}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception:
                logger.exception("Failed to send password reset email to %s", user.email)

        except User.DoesNotExist:
            # Do nothing — fall through to the same message (prevents enumeration)
            pass

        # Always show the same message, whether the user exists or not
        messages.success(request, 'Check Your Email For Reset link')
        return redirect(WEB_LOGIN_URL)

    return render(request, 'accounts/forgot_password.html')


# ============================================================
# RESET PASSWORD
# ============================================================
def reset_password_page(request, uidb64, token):
    """Set a new password using the token from the reset email."""

    # Decode the user ID
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # Validate the token
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, 'accounts/reset_password.html', {'valid_link': False})

    if request.method == 'POST':
        password = request.POST.get('password') or ''
        confirm_password = request.POST.get('confirm_password') or ''

        if not password or not confirm_password:
            messages.error(request, 'Please enter both password fields.')
            return render(request, 'accounts/reset_password.html', {'valid_link': True})

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/reset_password.html', {'valid_link': True})

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'accounts/reset_password.html', {'valid_link': True})

        # Save the new password
        user.set_password(password)
        user.save()

        messages.success(request, 'Password reset successful! Please login with your new password.')
        return redirect(WEB_LOGIN_URL)

    return render(request, 'accounts/reset_password.html', {'valid_link': True})