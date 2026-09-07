from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

admin.site.site_header = "RS ADMINISTRATION"
admin.site.site_title = "Administration Portal"
admin.site.index_title = "Welcome to RonoSystems Administration"

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    path('api/', views.api_root, name='api-root'),
    path('admin/', admin.site.urls),
    
    # ============================================
    # WEB INTERFACE
    # ============================================
    path('auth/', include('apps.accounts.web_urls')),
    path('dashboard/', include('apps.company.dashboard_urls')),
    path('company/', include('apps.company.urls_web')), 
    path('epa_shop/', include('apps.epa_shop.urls_web')),
    path('business-types/', include('apps.business_types.urls')),
    path('companies/', include('apps.companies.web_urls')),
    path('employees/', include('apps.employees.web_urls')),
    
    # Treasury - follows same pattern as other apps
    path('treasury/', include('apps.treasury.urls')),
    
    path('plans/', include('apps.plans.urls')),
    path('reports/', include('apps.reports.urls')),
    path('settings/', include('apps.settings.urls')),
    path('profile/', include('apps.accounts.profile_urls')),
    
    # ============================================
    # API ENDPOINTS
    # ============================================
    path('api/auth/', include('apps.accounts.urls')),
    path('api/', include('apps.companies.urls')),
    path('api/epa/', include('apps.epa_shop.urls')),
    path('api/supermarket/', include('apps.supermarket.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)