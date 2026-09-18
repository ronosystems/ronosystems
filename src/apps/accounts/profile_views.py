from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.conf import settings
from django.contrib.auth import get_user_model
import time
import cloudinary
import cloudinary.uploader

User = get_user_model()


# ============================================================
# Cloudinary helper
# ============================================================
def _cloudinary_configure():
    cfg = getattr(settings, 'CLOUDINARY_STORAGE', {})
    cloudinary.config(
        cloud_name=cfg.get('CLOUD_NAME', ''),
        api_key=cfg.get('API_KEY', ''),
        api_secret=cfg.get('API_SECRET', ''),
        secure=True,
    )


# ============================================================
# Profile view / update
# ============================================================
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

        if email and email != user.email:
            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email already in use by another user.')
                return redirect('/profile/')
            user.email = email

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


# ============================================================
# Profile picture — Cloudinary direct, unique public_id per upload
# ============================================================
@login_required
def profile_picture_upload(request):
    """Upload profile picture to Cloudinary with a unique public_id per upload."""
    user = request.user

    if request.method != 'POST' or not request.FILES.get('profile_picture'):
        messages.error(request, 'Please select a file to upload.')
        return redirect('/profile/')

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

    # Remember the current key so we can delete it AFTER a successful upload
    old_key = ''
    if user.profile_picture:
        old_key = getattr(user.profile_picture, 'name', '') or str(user.profile_picture)
        old_key = old_key.strip().lstrip('/')

    # Upload to Cloudinary — unique public_id every time
    try:
        _cloudinary_configure()
        public_id = f"profiles/user_{user.id}_{int(time.time())}"
        result = cloudinary.uploader.upload(
            profile_pic,
            public_id=public_id,
            overwrite=False,           # unique ID means nothing to overwrite
            resource_type='image',
        )
        new_key = result.get('public_id') or public_id
    except Exception as e:
        messages.error(request, f'Upload failed: {e}')
        return redirect('/profile/')

    # Save the new key on the user
    user.profile_picture = new_key
    user.save()

    # Delete the previous asset (best-effort, silent on failure)
    if old_key and old_key != new_key:
        try:
            _cloudinary_configure()
            cloudinary.uploader.destroy(old_key)
        except Exception:
            pass

    messages.success(request, 'Profile picture updated successfully!')
    return redirect('/profile/')


@login_required
def profile_picture_remove(request):
    """Remove profile picture from Cloudinary and clear the field."""
    user = request.user

    if request.method != 'POST':
        return redirect('/profile/')

    if not user.profile_picture:
        messages.warning(request, 'No profile picture to remove.')
        return redirect('/profile/')

    old_key = getattr(user.profile_picture, 'name', '') or str(user.profile_picture)
    old_key = old_key.strip().lstrip('/')

    try:
        _cloudinary_configure()
        cloudinary.uploader.destroy(old_key)
    except Exception:
        pass

    user.profile_picture = None
    user.save()

    messages.success(request, 'Profile picture removed successfully!')
    return redirect('/profile/')


# ============================================================
# Password
# ============================================================
@login_required
def password_change(request):
    """Change user password"""
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if not request.user.check_password(current_password):
            messages.error(request, 'Current password is incorrect.')
            return redirect('/profile/')

        if len(new_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('/profile/')

        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
            return redirect('/profile/')

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)

        messages.success(request, 'Password changed successfully!')
        return redirect('/profile/')

    return redirect('/profile/')


@login_required
def password_reset_request(request):
    """Request password reset (for users who forgot password)"""
    messages.info(request, 'Password reset functionality coming soon. Please contact support.')
    return redirect('/auth/login/')