from .settings_data import get_settings, DEFAULT_SETTINGS
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
import os


def system_settings(request):
    """Add system settings to all templates with proper URL handling"""
    
    # Get settings from file
    settings_dict = get_settings()
    
    # Get image paths
    site_logo = settings_dict.get('SITE_LOGO', '')
    site_favicon = settings_dict.get('SITE_FAVICON', '')
    login_background = settings_dict.get('LOGIN_BACKGROUND', '')
    
    # Helper function to get full URL for an image
    def get_full_url(image_path, check_exists=True):
        """Get the full URL for an image, handling both local and Cloudinary storage"""
        if not image_path:
            return None
        
        # If it's already a full URL (Cloudinary or external)
        if image_path.startswith('http://') or image_path.startswith('https://'):
            return image_path
        
        # If it contains 'cloudinary', it's already a Cloudinary URL
        if 'cloudinary' in image_path:
            return image_path
        
        # Clean the path (remove any /media/ prefix)
        clean_path = image_path
        if clean_path.startswith('/media/'):
            clean_path = clean_path[7:]
        elif clean_path.startswith('media/'):
            clean_path = clean_path[6:]
        
        # Remove leading/trailing slashes
        clean_path = clean_path.strip('/')
        
        # Check if file exists (optional)
        if check_exists:
            try:
                if not default_storage.exists(clean_path):
                    print(f"File not found: {clean_path}")
                    return None
            except Exception as e:
                print(f"Error checking file existence: {e}")
        
        # Try to get URL from storage (works with Cloudinary)
        try:
            url = default_storage.url(clean_path)
            if url:
                return url
        except Exception as e:
            print(f"Error getting URL from storage: {e}")
        
        # Fallback: use MEDIA_URL
        media_url = getattr(django_settings, 'MEDIA_URL', '/media/')
        if media_url:
            # Ensure no double slashes
            if media_url.endswith('/') and clean_path.startswith('/'):
                return f"{media_url}{clean_path[1:]}"
            elif media_url.endswith('/') or clean_path.startswith('/'):
                return f"{media_url}{clean_path}"
            else:
                return f"{media_url}/{clean_path}"
        
        # Final fallback
        return f"/media/{clean_path}"
    
    # Get company logo URL
    company_logo_url = None
    company_logo = None
    
    if request.user.is_authenticated:
        try:
            if hasattr(request.user, 'company') and request.user.company:
                company_logo_obj = getattr(request.user.company, 'logo', None)
                if company_logo_obj:
                    company_logo = company_logo_obj
                    # Get the URL from the ImageField
                    if hasattr(company_logo_obj, 'url'):
                        company_logo_url = company_logo_obj.url
                    else:
                        company_logo_url = str(company_logo_obj)
        except Exception as e:
            print(f"Error getting company logo: {e}")
    
    # Get full URLs for images
    site_logo_url = get_full_url(site_logo)
    site_favicon_url = get_full_url(site_favicon)
    login_background_url = get_full_url(login_background)
    
    # Determine storage type
    storage_type = 'local'
    storage_backend = str(type(default_storage))
    if 'cloudinary' in storage_backend.lower():
        storage_type = 'cloudinary'
    elif 's3' in storage_backend.lower() or 'boto3' in storage_backend.lower():
        storage_type = 's3'
    
    # Build context
    context = {
        # Basic site info
        'system_name': settings_dict.get('SITE_NAME', 'RonoSystems'),
        'site_tagline': settings_dict.get('SITE_TAGLINE', 'Enterprise Management Platform'),
        
        # Logo URLs
        'site_logo': site_logo,
        'site_logo_url': site_logo_url,
        'site_favicon': site_favicon,
        'site_favicon_url': site_favicon_url,
        'login_background': login_background,
        'login_background_url': login_background_url,
        
        # Company logo (for authenticated users)
        'company_logo': company_logo,
        'company_logo_url': company_logo_url,
        
        # Colors
        'primary_color': settings_dict.get('PRIMARY_COLOR', '#036a77'),
        'secondary_color': settings_dict.get('SECONDARY_COLOR', '#00b4d8'),
        
        # Full settings dict
        'system_settings': settings_dict,
        
        # Media and storage info
        'media_url': getattr(django_settings, 'MEDIA_URL', '/media/'),
        'storage_type': storage_type,
        'is_cloudinary': storage_type == 'cloudinary',
        'is_s3': storage_type == 's3',
        'is_local': storage_type == 'local',
    }
    
    # Debug mode - show storage info
    if getattr(django_settings, 'DEBUG', False):
        context['storage_backend'] = storage_backend
        context['media_root'] = getattr(django_settings, 'MEDIA_ROOT', None)
        context['base_dir'] = getattr(django_settings, 'BASE_DIR', None)
    
    return context