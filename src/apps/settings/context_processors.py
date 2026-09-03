from .settings_data import get_settings, DEFAULT_SETTINGS

def system_settings(request):
    """Add system settings to all templates"""
    
    # Get settings from file
    settings_dict = get_settings()
    
    # Get logo - ensure it doesn't have /media/ prefix
    site_logo = settings_dict.get('SITE_LOGO', '')
    if site_logo:
        # Remove any /media/ prefix
        site_logo = site_logo.replace('/media/', '').replace('media/', '')
    
    # If user is logged in and has company logo, use that instead
    if request.user.is_authenticated:
        try:
            if hasattr(request.user, 'company') and request.user.company:
                company_logo = getattr(request.user.company, 'logo', None)
                if company_logo:
                    if hasattr(company_logo, 'url'):
                        # Get just the filename/path without /media/
                        logo_url = company_logo.url
                        site_logo = logo_url.replace('/media/', '').replace('media/', '')
                    else:
                        site_logo = str(company_logo).replace('/media/', '').replace('media/', '')
        except:
            pass
    
    context = {
        'system_name': settings_dict.get('SITE_NAME', 'RonoSystems'),
        'site_tagline': settings_dict.get('SITE_TAGLINE', 'Enterprise Management Platform'),
        'site_logo': site_logo,
        'primary_color': settings_dict.get('PRIMARY_COLOR', '#036a77'),
        'secondary_color': settings_dict.get('SECONDARY_COLOR', '#00b4d8'),
        'system_settings': settings_dict,
    }
    return context