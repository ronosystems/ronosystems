from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings as django_settings
from django.http import JsonResponse
import json
import os

from .settings_data import get_settings, save_settings, DEFAULT_SETTINGS, CATEGORIES, SETTINGS_META

@login_required
@staff_member_required
def settings_dashboard(request):
    """System settings dashboard"""
    
    # Get current settings
    current_settings = get_settings()
    
    # Prepare categories with their settings
    categories_data = {}
    for cat_key, cat_data in CATEGORIES.items():
        categories_data[cat_key] = {
            'label': cat_data['label'],
            'icon': cat_data['icon'],
            'color': cat_data['color'],
            'settings': []
        }
        
        for setting_key in cat_data['settings']:
            meta = SETTINGS_META.get(setting_key, {})
            value = current_settings.get(setting_key, '')
            
            # Convert boolean for display
            if meta.get('type') == 'boolean':
                value = 'true' if value else 'false'
            
            # For images, store just the relative path (without /media/)
            if meta.get('type') == 'image' and value:
                # Remove any /media/ prefix if present
                value = value.replace('/media/', '').replace('media/', '')
            
            categories_data[cat_key]['settings'].append({
                'key': setting_key,
                'value': value,
                'label': meta.get('label', setting_key.replace('_', ' ').title()),
                'type': meta.get('type', 'text'),
                'description': meta.get('description', ''),
                'help_text': meta.get('help_text', ''),
                'required': meta.get('required', False),
                'options': meta.get('options', []),
            })
    
    context = {
        'categories': categories_data,
        'settings': current_settings,
        'page_title': 'System Settings',
        'page_subtitle': 'Configure your system preferences',
        'active_tab': 'settings',
    }
    return render(request, 'admin/settings_dashboard.html', context)

@login_required
@staff_member_required
def settings_update(request):
    """Update system settings"""
    
    print("=" * 50)
    print("SETTINGS UPDATE REQUEST")
    print("Method:", request.method)
    print("POST Keys:", list(request.POST.keys()))
    print("FILES Keys:", list(request.FILES.keys()))
    print("=" * 50)
    
    if request.method != 'POST':
        return redirect('/settings/')
    
    current_settings = get_settings()
    updated_count = 0
    
    # Process form fields
    for key, value in request.POST.items():
        if key == 'csrfmiddlewaretoken' or key.startswith('remove_'):
            continue
        
        # Check if this is a setting key
        if key in current_settings:
            # Get the setting type
            meta = SETTINGS_META.get(key, {})
            setting_type = meta.get('type', 'text')
            
            # Handle different types
            if setting_type == 'boolean':
                current_settings[key] = value == 'on'
            elif setting_type == 'integer':
                try:
                    current_settings[key] = int(value) if value else 0
                except:
                    current_settings[key] = 0
            elif setting_type == 'float':
                try:
                    current_settings[key] = float(value) if value else 0.0
                except:
                    current_settings[key] = 0.0
            else:
                current_settings[key] = value.strip() if value else ''
            
            updated_count += 1
            print(f"Updated {key} = {current_settings[key]}")
    
    # Handle file uploads
    for key, file_obj in request.FILES.items():
        if key in current_settings:
            # Delete old file if exists
            old_value = current_settings.get(key, '')
            if old_value:
                # Remove any /media/ prefix for storage path
                old_path = old_value.replace('/media/', '').replace('media/', '')
                if default_storage.exists(old_path):
                    default_storage.delete(old_path)
                    print(f"Deleted old file: {old_path}")
            
            # Create upload directory
            upload_dir = os.path.join(django_settings.MEDIA_ROOT, 'settings')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            
            # Save file - store path WITHOUT /media/ prefix
            file_name = file_obj.name.replace(' ', '_')
            file_path = default_storage.save(f'settings/{file_name}', ContentFile(file_obj.read()))
            
            # Store just the relative path (without /media/)
            current_settings[key] = file_path
            updated_count += 1
            label = SETTINGS_META.get(key, {}).get('label', key)
            messages.success(request, f'✅ {label} uploaded successfully!')
            print(f"Uploaded {key} = {file_path}")
    
    # Handle image removals
    for key, value in request.POST.items():
        if key.startswith('remove_'):
            setting_key = key.replace('remove_', '')
            if setting_key in current_settings:
                # Delete old file
                old_value = current_settings.get(setting_key, '')
                if old_value:
                    old_path = old_value.replace('/media/', '').replace('media/', '')
                    if default_storage.exists(old_path):
                        default_storage.delete(old_path)
                        print(f"Deleted removed file: {old_path}")
                
                current_settings[setting_key] = ''
                updated_count += 1
                label = SETTINGS_META.get(setting_key, {}).get('label', setting_key)
                messages.success(request, f'✅ {label} removed successfully')
    
    # Save settings
    if updated_count > 0:
        save_settings(current_settings)
        messages.success(request, f'✅ {updated_count} settings updated successfully!')
    else:
        messages.info(request, 'No changes were made')
    
    return redirect('/settings/?saved=1')

@login_required
@staff_member_required
def settings_reset(request):
    """Reset a setting to default"""
    
    if request.method == 'POST':
        setting_key = request.POST.get('key')
        current_settings = get_settings()
        
        if setting_key in DEFAULT_SETTINGS:
            current_settings[setting_key] = DEFAULT_SETTINGS[setting_key]
            save_settings(current_settings)
            label = SETTINGS_META.get(setting_key, {}).get('label', setting_key)
            messages.success(request, f'✅ "{label}" has been reset to default.')
        else:
            messages.error(request, f'❌ Setting "{setting_key}" not found.')
    
    return redirect('/settings/')

@login_required
@staff_member_required
def settings_export(request):
    """Export settings as JSON"""
    current_settings = get_settings()
    return JsonResponse(current_settings, safe=False)

@login_required
@staff_member_required
def settings_import(request):
    """Import settings from JSON"""
    if request.method == 'POST' and request.FILES.get('settings_file'):
        try:
            file = request.FILES['settings_file']
            data = json.loads(file.read().decode('utf-8'))
            
            current_settings = get_settings()
            imported_count = 0
            
            for key, value in data.items():
                if key in current_settings:
                    current_settings[key] = value
                    imported_count += 1
            
            save_settings(current_settings)
            messages.success(request, f'✅ Successfully imported {imported_count} settings')
        except Exception as e:
            messages.error(request, f'❌ Error importing settings: {str(e)}')
    
    return redirect('/settings/')

@login_required
@staff_member_required
def settings_test_email(request):
    """Test email configuration"""
    if request.method == 'POST':
        try:
            from django.core.mail import send_mail
            from django.conf import settings as django_settings
            
            test_email = request.POST.get('test_email')
            if not test_email:
                messages.error(request, 'Please provide a test email address')
                return redirect('/settings/')
            
            current_settings = get_settings()
            
            # Configure email
            django_settings.EMAIL_HOST = current_settings.get('EMAIL_HOST', 'smtp.gmail.com')
            django_settings.EMAIL_PORT = int(current_settings.get('EMAIL_PORT', 587))
            django_settings.EMAIL_HOST_USER = current_settings.get('EMAIL_USERNAME', '')
            django_settings.EMAIL_HOST_PASSWORD = current_settings.get('EMAIL_PASSWORD', '')
            django_settings.EMAIL_USE_TLS = current_settings.get('EMAIL_TLS', True)
            django_settings.DEFAULT_FROM_EMAIL = current_settings.get('EMAIL_FROM', 'noreply@example.com')
            
            # Send test email
            send_mail(
                'Test Email from RonoSystems',
                'This is a test email to verify your email configuration.\n\nIf you received this, your email settings are working correctly!\n\nBest regards,\nRonoSystems Team',
                django_settings.DEFAULT_FROM_EMAIL,
                [test_email],
                fail_silently=False,
            )
            
            messages.success(request, f'✅ Test email sent successfully to {test_email}')
        except Exception as e:
            messages.error(request, f'❌ Failed to send test email: {str(e)}')
    
    return redirect('/settings/')

@login_required
@staff_member_required
def settings_debug(request):
    """Debug view to check settings"""
    current_settings = get_settings()
    return JsonResponse({
        'settings': current_settings,
        'file_exists': os.path.exists(SETTINGS_FILE),
        'file_path': SETTINGS_FILE,
        'settings_keys': list(current_settings.keys()),
    })