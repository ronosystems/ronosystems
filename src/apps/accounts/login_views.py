from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

User = get_user_model()


def login_page(request):
    """Web login page with automatic dashboard routing"""
    
    if request.user.is_authenticated:
        return redirect_dashboard(request, request.user) 
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')
        
        if not email or not password:
            messages.error(request, 'Please enter both email and password.')
            return render(request, 'accounts/login.html')
        
        user = authenticate(request, username=email, password=password)
        
        if user is None:
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
        
        if user is not None:
            if user.is_active:
                login(request, user)
                
                if not remember_me:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(1209600)
                
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                return redirect_dashboard(request, user) 
            else:
                messages.error(request, 'Your account is disabled. Please contact support.')
        else:
            messages.error(request, 'Invalid email or password. Please try again.')
    
    return render(request, 'accounts/login.html')


def redirect_dashboard(request, user): 
    """Redirect user to appropriate dashboard based on role, company, and business type"""
    
    # SUPER ADMIN
    if user.role == 'super_admin':
        return HttpResponseRedirect(reverse('super-admin-dashboard'))
    
    # COMPANY USERS
    company = user.company
    
    if not company:
        messages.warning(request, 'You are not assigned to any company. Please contact your administrator.')
        return HttpResponseRedirect('/admin/')
    
    business_type = company.business_type
    
    # Check business type & route to WEB dashboards
    if business_type:
        business_name = business_type.name.lower()
        
        # EPA Shop - Web Dashboard
        if 'epa' in business_name or 'electronics' in business_name:
            return HttpResponseRedirect('/epa_shop/dashboard/')
        
        # Supermarket
        elif 'supermarket' in business_name or 'grocery' in business_name:
            return HttpResponseRedirect('/supermarket/dashboard/')
        
        # Healthcare
        elif 'healthcare' in business_name or 'medical' in business_name:
            return HttpResponseRedirect('/healthcare/dashboard/')
        
        # Education
        elif 'education' in business_name or 'school' in business_name:
            return HttpResponseRedirect('/education/dashboard/')
        
        # Restaurant
        elif 'restaurant' in business_name or 'food' in business_name:
            return HttpResponseRedirect('/restaurant/dashboard/')
        
        # Retail
        elif 'retail' in business_name:
            return HttpResponseRedirect('/retail/dashboard/')
    
    # Default: General Dashboard
    return HttpResponseRedirect('/dashboard/general/')


@login_required
def logout_view(request):
    """Logout user and redirect to web login page"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    # Force redirect to web login page (not API)
    return HttpResponseRedirect('/auth/login/')


    
def register_page(request):
    """Web registration page"""
    
    if request.method == 'POST':
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        phone = request.POST.get('phone', '').strip()
        
        if not all([email, username, password, confirm_password]):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'accounts/register.html')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'accounts/register.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'accounts/register.html')
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role='guest'
            )
            messages.success(request, 'Account created successfully! Please Wait for verifications this may take up to 48 hours.')
            return redirect('/auth/login/')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            return render(request, 'accounts/register.html')
    
    return render(request, 'accounts/register.html')


def forgot_password_page(request):
    """Forgot password page - request password reset link"""
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'accounts/forgot_password.html')
        
        try:
            user = User.objects.get(email=email)
            
            # Generate password reset token
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            # Build reset link
            reset_link = request.build_absolute_uri(
                reverse('reset-password', kwargs={'uidb64': uid, 'token': token})
            )
            
            messages.success(request, f'Password reset link sent to {email}. Please check your email.')
            return redirect('login')
            
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return render(request, 'accounts/forgot_password.html')
    
    return render(request, 'accounts/forgot_password.html')


def reset_password_page(request, uidb64, token):
    """Reset password page - set new password"""
    
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is None or not default_token_generator.check_token(user, token):
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('login')
    
    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        if not password or not confirm_password:
            messages.error(request, 'Please enter both password fields.')
            return render(request, 'accounts/reset_password.html', {'valid_link': True})
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/reset_password.html', {'valid_link': True})
        
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'accounts/reset_password.html', {'valid_link': True})
        
        # Set new password
        user.set_password(password)
        user.save()
        
        messages.success(request, 'Password reset successful! Please login with your new password.')
        return redirect('login')
    
    return render(request, 'accounts/reset_password.html', {'valid_link': True})