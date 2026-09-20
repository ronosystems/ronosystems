from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.companies import web_views as company_views
from apps.accounts.admin_site import restricted_admin_site
from apps.accounts import views_guest
from . import views


# ============================================
# ADMIN SITE CUSTOMIZATION
# ============================================
admin.site.site_header = "RONOSYSTEMS ADMINISTRATION"
admin.site.site_title = "Administration Portal"
admin.site.index_title = "Welcome to RonoSystems Administration"


# ============================================
# URL PATTERNS
# ============================================
urlpatterns = [
    # Home
    path('', views.home, name='home'),
    path('api/', views.api_root, name='api-root'),

    # ⚠️ RESTRICTED ADMIN — only super admins
    path('admin/', restricted_admin_site.urls),

    # ✅ No-access page for guests without company
    path('no-access/', views_guest.no_access, name='no-access'),

    # ============================================
    # WEB INTERFACE
    # ============================================
    path('auth/', include('apps.accounts.web_urls')),
    path('dashboard/', include('apps.company.dashboard_urls')),
    path('company/', include('apps.company.urls_web')),
    path('epa_shop/', include('apps.epa_shop.urls_web')),
    path('kuku_biz/', include('apps.kuku_biz.urls')),
    path('business-types/', include('apps.business_types.urls')),
    path('subscription-expired/', company_views.subscription_expired, name='subscription-expired'),
    path('payments/kcb/callback/', company_views.company_payments_callback, name='kcb-callback'),
    path('companies/', include('apps.companies.web_urls')),
    path('employees/', include('apps.employees.web_urls')),

    path('treasury/', include('apps.treasury.urls')),

    path('plans/', include('apps.plans.urls')),
    path('reports/', include('apps.reports.urls')),
    path('settings/', include('apps.settings.urls')),
    path('profile/', include('apps.accounts.profile_urls')),
    path('accounts/', include('allauth.urls')),

    # ============================================
    # API ENDPOINTS
    # ============================================
    path('api/auth/', include('apps.accounts.urls')),
    path('api/', include('apps.companies.urls')),
    path('api/epa/', include('apps.epa_shop.urls')),
    path('api/supermarket/', include('apps.supermarket.urls')),
]


# ============================================
# STATIC & MEDIA (DEBUG ONLY)
# ============================================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)