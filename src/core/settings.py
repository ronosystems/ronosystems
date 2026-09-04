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

# Allow hosts from environment or default for Render
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
# Add Render domain if not in env
if 'RENDER' in os.environ:
    ALLOWED_HOSTS.append('ronosystems.onrender.com')
    ALLOWED_HOSTS.append('*.onrender.com')

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')
if 'RENDER' in os.environ:
    CSRF_TRUSTED_ORIGINS.append('https://ronosystems.onrender.com')
    CSRF_TRUSTED_ORIGINS.append('https://*.onrender.com')

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
    'whitenoise.runserver_nostatic',  # For static files in production
    
    # Custom Apps
    'apps.accounts',
    'apps.employees',
    'apps.business_types',
    'apps.companies',
    'apps.company', 
    'apps.plans',
    'apps.reports',
    'apps.settings', 
    
    # Business Type Apps
    'apps.epa_shop',
    'apps.supermarket',
]

# ============================================
# MIDDLEWARE (Whitenoise for static files)
# ============================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add this for static files
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ============================================
# DATABASE - Neon PostgreSQL (Production)
# ============================================
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Production - Neon PostgreSQL
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
else:
    # Development - Local PostgreSQL
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
# STATIC & MEDIA FILES
# ============================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Whitenoise storage for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ============================================
# DEFAULT SETTINGS
# ============================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# ============================================
# CORS
# ============================================
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only in development
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
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ============================================
# LOGGING (Optional)
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