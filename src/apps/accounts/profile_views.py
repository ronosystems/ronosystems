from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib.auth import get_user_model
import os
from PIL import Image
from io import BytesIO

User = get_user_model()

@login_required
def profile_view(request):
    """View and edit user profile"""
    user = request.user
    
    context = {
        'user': user,
        'page_title': 'Profile',
        'page_subtitle': 'Manage your profile',
    }
    return render(request, 'accounts/profile.html', context)

@login_required
def profile_update(request):
    """Update user profile details"""
    user = request.user
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        department = request.POST.get('department', '').strip()
        position = request.POST.get('position', '').strip()
        employee_id = request.POST.get('employee_id', '').strip()
        
        # Validate email
        if email and email != user.email:
            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email already in use by another user.')
                return redirect('/profile/')
            user.email = email
        
        # Update user fields
        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone
        user.address = address
        user.department = department
        user.position = position
        user.employee_id = employee_id
        user.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('/profile/')
    
    return redirect('/profile/')

@login_required
def profile_picture_upload(request):
    """Upload profile picture"""
    user = request.user
    
    if request.method == 'POST' and request.FILES.get('profile_picture'):
        profile_pic = request.FILES['profile_picture']
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if profile_pic.content_type not in allowed_types:
            messages.error(request, 'Please upload a valid image file (JPEG, PNG, GIF, WEBP).')
            return redirect('/profile/')
        
        # Validate file size (max 5MB)
        if profile_pic.size > 5 * 1024 * 1024:
            messages.error(request, 'Image size must be less than 5MB.')
            return redirect('/profile/')
        
        # Delete old profile picture if exists
        if user.profile_picture:
            try:
                default_storage.delete(user.profile_picture.path)
            except:
                pass
        
        # Save new profile picture
        filename = f"profile_{user.id}_{profile_pic.name}"
        path = default_storage.save(f'profiles/{filename}', ContentFile(profile_pic.read()))
        user.profile_picture = path
        user.save()
        
        messages.success(request, 'Profile picture updated successfully!')
        return redirect('/profile/')
    
    messages.error(request, 'Please select a file to upload.')
    return redirect('/profile/')

@login_required
def profile_picture_remove(request):
    """Remove profile picture"""
    user = request.user
    
    if request.method == 'POST':
        if user.profile_picture:
            try:
                default_storage.delete(user.profile_picture.path)
            except:
                pass
            user.profile_picture = None
            user.save()
            messages.success(request, 'Profile picture removed successfully!')
        else:
            messages.warning(request, 'No profile picture to remove.')
        
        return redirect('/profile/')
    
    return redirect('/profile/')

@login_required
def password_change(request):
    """Change user password"""
    
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Validate current password
        if not request.user.check_password(current_password):
            messages.error(request, 'Current password is incorrect.')
            return redirect('/profile/')
        
        # Validate new password
        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('/profile/')
        
        # Validate password confirmation
        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
            return redirect('/profile/')
        
        # Change password
        request.user.set_password(new_password)
        request.user.save()
        
        # Keep user logged in
        update_session_auth_hash(request, request.user)
        
        messages.success(request, 'Password changed successfully!')
        return redirect('/profile/')
    
    return redirect('/profile/')

@login_required
def password_reset_request(request):
    """Request password reset (for users who forgot password)"""
    messages.info(request, 'Password reset functionality coming soon. Please contact support.')
    return redirect('/auth/login/')
