# core/settings.py
import os
import glob
import shutil
import logging
import subprocess
import dj_database_url

from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

ON_RENDER = 'RENDER' in os.environ


def env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ('1', 'true', 'yes', 'on')


# ============================================
# SECURITY
# ============================================
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if ON_RENDER:
        raise RuntimeError("SECRET_KEY environment variable must be set in production.")
    SECRET_KEY = 'django-insecure-ronosystems-dev-only-key'

DEBUG = env_bool('DEBUG', default=False)

# ============================================
# ALLOWED HOSTS
# ============================================
# Platform + wildcard subdomains. Custom domains are gated by TenantMiddleware.
ALLOWED_HOSTS = []

_allowed = os.getenv('ALLOWED_HOSTS', '')
if _allowed:
    ALLOWED_HOSTS.extend(h.strip() for h in _allowed.split(',') if h.strip())
else:
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1'])

ALLOWED_HOSTS.extend([
    'ronosystems.com',
    '.ronosystems.com',                 # kalyet.ronosystems.com, umoja.ronosystems.com
    'ronosystems.onrender.com',
    '.ronosystems.onrender.com',        # kalyet.ronosystems.onrender.com (staging)
    'ronosystems.co.ke',
    '.ronosystems.co.ke',
    '.localhost',                       # fieldmax.localhost, kalwal.localhost
])

if ON_RENDER:
    ALLOWED_HOSTS.append('ronosystems.onrender.com')

# Custom domains (kalyet.co.ke). TenantMiddleware rejects unknown hosts with 404.
if '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('*')

# ============================================
# CSRF TRUSTED ORIGINS
# ============================================
CSRF_TRUSTED_ORIGINS = []
_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if _csrf:
    CSRF_TRUSTED_ORIGINS.extend(o.strip() for o in _csrf.split(',') if o.strip())
else:
    CSRF_TRUSTED_ORIGINS.extend([
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://*.localhost:8000',
    ])

# FIX: extra dev safety net so subdomain POSTs (fieldmax.localhost:8000) are accepted
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend([
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://*.localhost:8000',
    ])

if ON_RENDER:
    CSRF_TRUSTED_ORIGINS.extend([
        'https://ronosystems.onrender.com',
        'https://*.ronosystems.onrender.com',
        'https://ronosystems.com',
        'https://*.ronosystems.com',
    ])

CSRF_TRUSTED_ORIGINS = [
    o for o in CSRF_TRUSTED_ORIGINS if o.startswith(('http://', 'https://'))
]

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
    'django.contrib.sites',

    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'whitenoise.runserver_nostatic',
    'cloudinary_storage',
    'cloudinary',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.apple',
    'allauth.socialaccount.providers.facebook',

    'core',

    # ===== GLOBAL / TENANT CORE =====
    'apps.accounts',       # User + Membership + Role
    'apps.companies',      # Company / Tenant + Domain + Branch + Expense
    'apps.plans',          # Plan + Subscription

    # ===== SHARED FEATURES =====
    'apps.treasury',
    'apps.reports',
    'apps.settings',
    'apps.losses',
    'apps.analytics',
    'apps.workshop',
    'apps.mpesa',
    'apps.cart_orders',
    'apps.ai_chatbot',
    'apps.customers',

    # ===== BUSINESS TYPE APPS =====
    'apps.epa_shop',
    'apps.supermarket',
    'apps.kuku_biz',
    'apps.chama',
]

SITE_ID = 1

# ============================================
# MIDDLEWARE — ORDER MATTERS
# ============================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',

    # 1. Auth FIRST so request.user exists before tenant check
    'django.contrib.auth.middleware.AuthenticationMiddleware',

    # 2. Tenant (sets request.company / request.tenant from Host)
    'apps.companies.middleware.TenantMiddleware',

    # 3. Active membership (JWT claims -> session -> tenant -> primary)
    'apps.companies.middleware.ActiveMembershipMiddleware',

    # 4. Subscription check (uses request.tenant)
    'apps.companies.middleware.SubscriptionExpiryMiddleware',

    # 5. Login gate + message framework
    'apps.accounts.middleware.LoginRequiredMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',

    # 6. Housekeeping
    'apps.accounts.middleware.InactivityLogoutMiddleware',
    'apps.analytics.middleware.VisitTrackingMiddleware',
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

                # Settings / AI / Cart
                'apps.settings.context_processors.pending_payments_count',
                'apps.settings.context_processors.pending_ai_chats_count',
                'apps.settings.context_processors.system_settings',
                'apps.ai_chatbot.context_processors.chatbot_available',
                'apps.cart_orders.context_processors.cart_count',

                # EPA Shop
                'apps.epa_shop.context_processors.user_context',
                'apps.epa_shop.context_processors.pending_orders_count',
                'apps.epa_shop.context_processors.sidebar_low_stock_count',

                # ===== COMPANIES — SOURCE OF TRUTH FOR TENANT =====
                'apps.companies.context_processors.system_website_url',
                'apps.companies.context_processors.active_base_template',
                'apps.companies.context_processors.support_mode_context',
                'apps.companies.context_processors.pending_join_requests',
                'apps.companies.context_processors.company_branding_context',
                'apps.companies.context_processors.unread_messages_count',
                'apps.companies.context_processors.receipt_settings_context',
                'apps.companies.context_processors.pending_feedback_count',
                'apps.companies.context_processors.total_notifications_count',
                'apps.companies.context_processors.pending_applications_count',
                'apps.companies.context_processors.company_features_context',

                'apps.plans.context_processors.plan_features',
                'apps.losses.context_processors.pending_losses_count',
                'apps.analytics.context_processors.visit_count_today',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ============================================
# VISIT TRACKING
# ============================================
VISIT_TRACKING_ENABLED = env_bool('VISIT_TRACKING_ENABLED', default=True)
VISIT_TRACKING_HASH_IP = env_bool('VISIT_TRACKING_HASH_IP', default=False)
VISIT_TRACKING_IP_SALT = os.getenv('VISIT_TRACKING_IP_SALT', 'change-me-in-prod')

if ON_RENDER:
    GEOIP_PATH = Path('/opt/render/project/geoip')
    if not GEOIP_PATH.exists():
        GEOIP_PATH = Path('/tmp/geoip')
else:
    GEOIP_PATH = BASE_DIR / 'geoip'

# ============================================
# DATABASE
# ============================================
USE_SQLITE = env_bool('USE_SQLITE', default=False)

if ON_RENDER:
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
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    print("✅ Using SQLite database for local development")
else:
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

AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.MembershipBackend',       # company-profile login
    'apps.accounts.backends.CustomerDomainBackend',   # shop customer PIN login
    'apps.accounts.backends.EmailOrPhoneBackend',     # mother domain fallback
    'apps.accounts.backends.TenantAuthBackend',       # legacy tenant login
    'django.contrib.auth.backends.ModelBackend',      # Django admin
]

# ============================================
# SESSION / AUTO-LOGOUT (30 MIN)
# ============================================
SESSION_COOKIE_AGE = 60 * 30
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
INACTIVITY_TIMEOUT_SECONDS = 60 * 30

# ============================================
# DJANGO-ALLAUTH
# ============================================
ACCOUNT_LOGIN_METHODS = {'username'}
ACCOUNT_SIGNUP_FIELDS = ['username*', 'email', 'password1*', 'password2*']
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
ACCOUNT_EMAIL_VERIFICATION = 'optional'
LOGIN_REDIRECT_URL = '/dashboard/'
ACCOUNT_LOGIN_REDIRECT_URL = '/dashboard/'
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_SIGNUP_REDIRECT_URL = '/dashboard/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/auth/login/'

SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.RonoSocialAccountAdapter'
ACCOUNT_ADAPTER = 'apps.accounts.adapters.RonoAccountAdapter'
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_QUERY_EMAIL = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'VERIFIED_EMAIL': True,
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
        'FIELDS': ['id', 'first_name', 'last_name', 'middle_name', 'name',
                   'name_format', 'picture', 'short_name', 'email'],
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
            'settings': {'certificate_key': os.getenv('APPLE_PRIVATE_KEY', '')},
        },
        'SCOPE': ['name', 'email'],
    },
}

ACCOUNT_FORMS = {'login': 'apps.accounts.forms.CustomLoginForm'}
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_STORE_TOKENS = False

# ============================================
# WHATSAPP TWILIO
# ============================================
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# ============================================
# CLOUDINARY
# ============================================
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME', 'dg9it0ut8'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY', ''),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET', ''),
    'UNSIGNED_PRESET': os.getenv('CLOUDINARY_UNSIGNED_PRESET', 'epa_unsigned'),
}

# ============================================
# STATIC & MEDIA
# ============================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

USE_CLOUDINARY_MEDIA = env_bool('USE_CLOUDINARY_MEDIA', default=ON_RENDER)

# FIX: default backend must be Cloudinary when USE_CLOUDINARY_MEDIA=True,
# otherwise uploads land on ephemeral disk but URLs point at Cloudinary.
if USE_CLOUDINARY_MEDIA:
    STORAGES = {
        "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
        "staticfiles": {
            "BACKEND": (
                "whitenoise.storage.CompressedManifestStaticFilesStorage"
                if ON_RENDER
                else "django.contrib.staticfiles.storage.StaticFilesStorage"
            )
        },
    }
    MEDIA_URL = f"https://res.cloudinary.com/{CLOUDINARY_STORAGE['CLOUD_NAME']}/image/upload/"
    print("✅ Using Cloudinary for media files")
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'
    print("✅ Using local media storage")

os.makedirs(STATIC_ROOT, exist_ok=True)

DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# ============================================
# CORS
# ============================================
CORS_ALLOW_ALL_ORIGINS = DEBUG
if not DEBUG:
    _cors = os.getenv('CORS_ALLOWED_ORIGINS', '')
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(',') if o.strip()]
    CORS_ALLOW_CREDENTIALS = True

# ============================================
# JWT
# ============================================
# FIX: use the membership-aware authenticator so request.membership is set
# from JWT claims. Fall back to vanilla JWTAuthentication for admin routes.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.accounts.authentication.MembershipJWTAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# FIX: shorten access token lifetime so switching companies takes effect
# within a normal session (was 1 day, which kept the old company active).
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ============================================
# LOGIN / LOGOUT URLs
# ============================================
# FIX: route unauthenticated users to the multi-tenant login endpoint
# instead of allauth's username-only login, so company_username works.
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ============================================
# SECURITY (Production)
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
# EMAIL
# ============================================
USE_REAL_EMAIL = env_bool('USE_REAL_EMAIL', default=False)
if ON_RENDER or USE_REAL_EMAIL:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 465))
    if EMAIL_PORT == 465:
        EMAIL_USE_SSL = True
        EMAIL_USE_TLS = False
    else:
        EMAIL_USE_SSL = False
        EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.getenv(
        'DEFAULT_FROM_EMAIL',
        EMAIL_HOST_USER or 'support.ronosystems@gmail.com',
    )
    SERVER_EMAIL = os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
    SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', DEFAULT_FROM_EMAIL)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'support.ronosystems@gmail.com'
    SERVER_EMAIL = DEFAULT_FROM_EMAIL
    SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', DEFAULT_FROM_EMAIL)

# ============================================
# SYSTEM ENGINES
# ============================================
SYSTEM_NAME = os.getenv('SYSTEM_NAME', 'RonoSystems')
SYSTEM_WEBSITE_URL = os.getenv('SYSTEM_WEBSITE_URL', '')
SYSTEM_DOMAIN = os.getenv(
    'SYSTEM_DOMAIN',
    'ronosystems.onrender.com' if ON_RENDER else 'localhost:8000',
)

# ============================================
# AI ASSISTANT
# ============================================
AI_PROVIDER = os.getenv('AI_PROVIDER', 'groq')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
AI_ASSISTANT_ENABLED = bool(GROQ_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY)

# ============================================
# CONTACT FORM
# ============================================
CONTACT_EMAIL = os.getenv('CONTACT_EMAIL', 'support.ronosystems@gmail.com')

# ============================================
# KOPOKOPO / KCB
# ============================================
KOPOKOPO_CLIENT_ID = os.getenv('KOPOKOPO_CLIENT_ID', '')
KOPOKOPO_CLIENT_SECRET = os.getenv('KOPOKOPO_CLIENT_SECRET', '')
KOPOKOPO_API_KEY = os.getenv('KOPOKOPO_API_KEY', '')
KOPOKOPO_ENVIRONMENT = os.getenv('KOPOKOPO_ENVIRONMENT', 'sandbox')
KOPOKOPO_BASE_URL = (
    'https://api.kopokopo.com'
    if KOPOKOPO_ENVIRONMENT == 'production'
    else 'https://sandbox.kopokopo.com'
)
KOPOKOPO_CALLBACK_URL = os.getenv(
    'KOPOKOPO_CALLBACK_URL',
    'https://ronosystems.onrender.com/payments/kopokopo/callback/',
)
KOPOKOPO_REDIRECT_URL = os.getenv(
    'KOPOKOPO_REDIRECT_URL',
    'https://ronosystems.onrender.com/',
)

KCB_CONSUMER_KEY = os.getenv('KCB_CONSUMER_KEY', '')
KCB_CONSUMER_SECRET = os.getenv('KCB_CONSUMER_SECRET', '')
KCB_ENVIRONMENT = os.getenv('KCB_ENVIRONMENT', 'sandbox')
KCB_BASE_URL = (
    'https://api.buni.kcbgroup.com'
    if KCB_ENVIRONMENT == 'production'
    else 'https://uat.buni.kcbgroup.com'
)
KCB_TOKEN_URL = f'{KCB_BASE_URL}/token?grant_type=client_credentials'
KCB_STK_ENDPOINT = '/mm/api/request/1.0.0/stkpush'
KCB_CALLBACK_URL = os.getenv(
    'KCB_CALLBACK_URL',
    'https://ronosystems.onrender.com/payments/kcb/callback/',
)

# ============================================
# LOGGING
# ============================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}
    },
}

# ============================================
# GEOIP AUTO-DOWNLOAD
# ============================================
if ON_RENDER:
    _log = logging.getLogger(__name__)
    _mmdb = GEOIP_PATH / 'GeoLite2-City.mmdb'
    if not _mmdb.exists():
        _log.warning('GeoLite2-City.mmdb missing — attempting download…')
        try:
            GEOIP_PATH.mkdir(parents=True, exist_ok=True)
            _account = os.getenv('MAXMIND_ACCOUNT_ID', '')
            _key = os.getenv('MAXMIND_LICENSE_KEY', '')
            if _account and _key:
                subprocess.run(
                    [
                        'curl', '-fL', '-u', f'{_account}:{_key}',
                        'https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz',
                        '-o', '/tmp/geolite2-city.tar.gz',
                    ],
                    check=True, timeout=120,
                )
                subprocess.run(
                    ['tar', '-xzf', '/tmp/geolite2-city.tar.gz', '-C', '/tmp'],
                    check=True, timeout=60,
                )
                _extracted = glob.glob('/tmp/GeoLite2-City_*/GeoLite2-City.mmdb')
                if _extracted:
                    shutil.move(_extracted[0], str(_mmdb))
                    _log.info('GeoLite2-City.mmdb installed at %s', _mmdb)
        except Exception as _e:
            _log.warning('GeoIP auto-download failed: %s', _e)