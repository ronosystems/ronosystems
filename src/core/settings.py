import os
import dj_database_url
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# SECURITY - Production Ready
# ============================================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-ronosystems-key-12345')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# ALLOWED_HOSTS - Fixed
ALLOWED_HOSTS = []
allowed = os.getenv('ALLOWED_HOSTS', '')
if allowed:
    ALLOWED_HOSTS = [host.strip() for host in allowed.split(',') if host.strip()]
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

if 'RENDER' in os.environ:
    ALLOWED_HOSTS.append('ronosystems.onrender.com')
    ALLOWED_HOSTS.append('*.onrender.com')

# CSRF Trusted Origins - Fixed
CSRF_TRUSTED_ORIGINS = []
csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_origins.split(',') if origin.strip()]
else:
    CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']

if 'RENDER' in os.environ:
    CSRF_TRUSTED_ORIGINS.append('https://ronosystems.onrender.com')
    CSRF_TRUSTED_ORIGINS.append('https://*.onrender.com')

# Filter out any origins that don't start with http:// or https://
CSRF_TRUSTED_ORIGINS = [origin for origin in CSRF_TRUSTED_ORIGINS if origin.startswith('http')]

# ============================================
# INSTALLED APPS
# ============================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'whitenoise.runserver_nostatic',
    'cloudinary_storage',
    'cloudinary',
    
    # Custom Apps
    'apps.accounts',
    'apps.employees',
    'apps.business_types',
    'apps.companies',
    'apps.company', 
    'apps.treasury',
    'apps.plans',
    'apps.reports',
    'apps.settings', 
    
    # Business Type Apps
    'apps.epa_shop',
    'apps.supermarket',
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.companies.middleware.SubscriptionExpiryMiddleware',
]

ROOT_URLCONF = 'core.urls'

# ============================================
# TEMPLATES
# ============================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.settings.context_processors.system_settings',
                'apps.epa_shop.context_processors.user_context',
                'apps.company.context_processors.company_context',
                'apps.companies.context_processors.support_mode_context',  
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ============================================
# DATABASE - SQLite for Local, PostgreSQL for Production
# ============================================

# Check if we should use SQLite (local development)
USE_SQLITE = os.getenv('USE_SQLITE', 'False') == 'True'

# Check if we're on Render (production)
ON_RENDER = 'RENDER' in os.environ

if ON_RENDER:
    # Production on Render - Use PostgreSQL
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL:
        DATABASES = {
            'default': dj_database_url.config(
                default=DATABASE_URL,
                conn_max_age=600,
                conn_health_checks=True,
                ssl_require=True,
            )
        }
    else:
        # Fallback if DATABASE_URL not set
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': os.getenv('DATABASE_NAME', 'rono_db'),
                'USER': os.getenv('DATABASE_USER', 'rono_user'),
                'PASSWORD': os.getenv('DATABASE_PASSWORD', 'rono_secure_password'),
                'HOST': os.getenv('DATABASE_HOST', 'localhost'),
                'PORT': os.getenv('DATABASE_PORT', '5432'),
            }
        }
        
elif USE_SQLITE:
    # Local development with SQLite
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    print("✅ Using SQLite database for local development")
    
else:
    # Local development with PostgreSQL (default)
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL:
        DATABASES = {
            'default': dj_database_url.config(
                default=DATABASE_URL,
                conn_max_age=600,
                conn_health_checks=True,
            )
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': os.getenv('DATABASE_NAME', 'rono_db'),
                'USER': os.getenv('DATABASE_USER', 'rono_user'),
                'PASSWORD': os.getenv('DATABASE_PASSWORD', 'rono_secure_password'),
                'HOST': os.getenv('DATABASE_HOST', 'localhost'),
                'PORT': os.getenv('DATABASE_PORT', '5432'),
            }
        }

# ============================================
# AUTHENTICATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# ============================================
# CLOUDINARY STORAGE CONFIGURATION
# ============================================
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', 'dg9it0ut8'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY', ''),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', ''),
}

# ============================================
# STATIC & MEDIA FILES - CLOUDINARY
# ============================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Use Cloudinary for media files in production
if ON_RENDER:
    # Use Cloudinary for media storage
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
    print("✅ Using Cloudinary for media files on Render")
else:
    # Local development - use local media
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'
    print("✅ Using local media storage")

# Ensure static directory exists
os.makedirs(STATIC_ROOT, exist_ok=True)

# Use WhiteNoise for static files in production
if ON_RENDER:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ============================================
# DEFAULT SETTINGS
# ============================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# ============================================
# CORS
# ============================================
CORS_ALLOW_ALL_ORIGINS = DEBUG
if not DEBUG:
    CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')
    CORS_ALLOW_CREDENTIALS = True

# ============================================
# JWT Settings
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ============================================
# LOGIN/LOGOUT URLs
# ============================================
LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/auth/login/'

# ============================================
# SECURITY SETTINGS (Production)
# ============================================
if not DEBUG and ON_RENDER:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ============================================
# LOGGING
# ============================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}