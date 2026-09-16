import os
import dj_database_url
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Define BASE_DIR FIRST so we know where .env lives
BASE_DIR = Path(__file__).resolve().parent.parent

# Explicitly load .env from BASE_DIR  →  /home/rs/ronosystems/src/.env
load_dotenv(BASE_DIR / '.env')

# ============================================
# SECURITY - Production Ready
# ============================================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-ronosystems-key-12345')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# ALLOWED_HOSTS
ALLOWED_HOSTS = []
allowed = os.getenv('ALLOWED_HOSTS', '')
if allowed:
    ALLOWED_HOSTS = [host.strip() for host in allowed.split(',') if host.strip()]
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

if 'RENDER' in os.environ:
    ALLOWED_HOSTS.append('ronosystems.onrender.com')
    ALLOWED_HOSTS.append('.onrender.com')

# Allow all hosts because custom domains are dynamic.
# Security is enforced by CustomDomainMiddleware (DB lookup) + Cloudflare.
ALLOWED_HOSTS.append('*')

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = []
csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_origins.split(',') if origin.strip()]
else:
    CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']

if 'RENDER' in os.environ:
    CSRF_TRUSTED_ORIGINS.append('https://ronosystems.onrender.com')
    # NOTE: Django does NOT support wildcards in CSRF_TRUSTED_ORIGINS.
    # Custom domains are added dynamically by CustomDomainMiddleware.

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

    # Sites framework (required by django-allauth)
    'django.contrib.sites',

    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'whitenoise.runserver_nostatic',
    'cloudinary_storage',
    'cloudinary',

    # ===== django-allauth =====
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.apple',
    'allauth.socialaccount.providers.facebook',

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

# Required by django.contrib.sites / allauth
SITE_ID = 1

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
    # allauth middleware (must come after AuthenticationMiddleware)
    'allauth.account.middleware.AccountMiddleware',
    'apps.companies.middleware.CustomDomainMiddleware',
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
                'apps.companies.context_processors.pending_join_requests',
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

# ===== allauth authentication backends =====
AUTHENTICATION_BACKENDS = [
    # Default ModelBackend — keeps email/password login working
    'django.contrib.auth.backends.ModelBackend',
    # allauth-specific backend — handles social + email login
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ============================================
# DJANGO-ALLAUTH CONFIGURATION
# ============================================

# Use email as the primary identifier (matches your existing login by email)
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = 'optional'


# Login/logout behavior
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SESSION_REMEMBER = True  # "Remember me" checkbox behaviour

# Signup behaviour — don't auto-redirect to allauth's signup flow,
# we have our own register page at /auth/register/
ACCOUNT_SIGNUP_REDIRECT_URL = '/dashboard/'
LOGIN_REDIRECT_URL = '/dashboard/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/auth/login/'

# Adapter — see signals/adapters note below
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.RonoSocialAccountAdapter'
ACCOUNT_ADAPTER = 'apps.accounts.adapters.RonoAccountAdapter'

# Auto-connect social accounts to existing users with the same email
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_QUERY_EMAIL = True

# Which fields to pull from social providers
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'APP': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
            'key': '',
        },
    },
    'facebook': {
        'METHOD': 'oauth2',
        'SDK_URL': '//connect.facebook.net/{locale}/sdk.js',
        'SCOPE': ['email', 'public_profile'],
        'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'INIT_PARAMS': {'cookie': True},
        'FIELDS': [
            'id',
            'first_name',
            'last_name',
            'middle_name',
            'name',
            'name_format',
            'picture',
            'short_name',
            'email',
        ],
        'EXCHANGE_TOKEN': True,
        'VERIFIED_EMAIL': False,
        'VERSION': 'v18.0',
        'APP': {
            'client_id': os.getenv('FACEBOOK_CLIENT_ID', ''),
            'secret': os.getenv('FACEBOOK_CLIENT_SECRET', ''),
            'key': '',
        },
    },
    'apple': {
        'APP': {
            'client_id': os.getenv('APPLE_CLIENT_ID', ''),
            'secret': os.getenv('APPLE_CLIENT_SECRET', ''),
            'key': os.getenv('APPLE_KEY_ID', ''),
            'certificate_key': os.getenv('APPLE_PRIVATE_KEY', ''),
        },
        'SCOPE': ['name', 'email'],
    },
}

# Where social signups land after account creation
SOCIALACCOUNT_LOGIN_ON_GET = True  # lets social buttons work as simple links
SOCIALACCOUNT_STORE_TOKENS = False

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
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
    print("✅ Using Cloudinary for media files on Render")
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'
    print("✅ Using local media storage")

os.makedirs(STATIC_ROOT, exist_ok=True)

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
# EMAIL CONFIGURATION
# ============================================
ON_RENDER = 'RENDER' in os.environ

if ON_RENDER:
    # Production (Render) — use SMTP
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@ronosystems.com')
else:
    # Local development — print emails to console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'noreply@ronosystems.com'

SYSTEM_NAME = os.getenv('SYSTEM_NAME', 'RonoSystems')

# ============================================
# KOPOKOPO PAYMENT GATEWAY
# ============================================

KOPOKOPO_CLIENT_ID = os.getenv('KOPOKOPO_CLIENT_ID', '')
KOPOKOPO_CLIENT_SECRET = os.getenv('KOPOKOPO_CLIENT_SECRET', '')
KOPOKOPO_API_KEY = os.getenv('KOPOKOPO_API_KEY', '')

KOPOKOPO_ENVIRONMENT = os.getenv('KOPOKOPO_ENVIRONMENT', 'sandbox')

if KOPOKOPO_ENVIRONMENT == 'production':
    KOPOKOPO_BASE_URL = 'https://api.kopokopo.com'
else:
    KOPOKOPO_BASE_URL = 'https://sandbox.kopokopo.com'

if ON_RENDER:
    KOPOKOPO_CALLBACK_URL = os.getenv(
        'KOPOKOPO_CALLBACK_URL',
        'https://ronosystems.onrender.com/payments/kopokopo/callback/'
    )
else:
    KOPOKOPO_CALLBACK_URL = os.getenv(
        'KOPOKOPO_CALLBACK_URL',
        'https://ronosystems.onrender.com/payments/kopokopo/callback/'
    )

KOPOKOPO_REDIRECT_URL = os.getenv(
    'KOPOKOPO_REDIRECT_URL',
    'https://ronosystems.onrender.com/'
)

# ============================================
# KCB BUNI PAYMENT GATEWAY
# ============================================

KCB_CONSUMER_KEY = os.getenv('KCB_CONSUMER_KEY', '')
KCB_CONSUMER_SECRET = os.getenv('KCB_CONSUMER_SECRET', '')
KCB_ENVIRONMENT = os.getenv('KCB_ENVIRONMENT', 'sandbox')

if KCB_ENVIRONMENT == 'production':
    KCB_BASE_URL = 'https://api.buni.kcbgroup.com'
else:
    KCB_BASE_URL = 'https://uat.buni.kcbgroup.com'

KCB_TOKEN_URL = f'{KCB_BASE_URL}/token?grant_type=client_credentials'
KCB_STK_ENDPOINT = '/mm/api/request/1.0.0/stkpush'
KCB_CALLBACK_URL = os.getenv(
    'KCB_CALLBACK_URL',
    'https://ronosystems.onrender.com/payments/kcb/callback/'
)

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