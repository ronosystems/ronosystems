from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from apps.companies import web_views as company_views
from apps.accounts.admin_site import restricted_admin_site
from apps.accounts import views_guest
from core.views import qz_sign, contact, manifest_view, service_worker, asset_links
from core.ai_views import ai_assistant
from . import views

# ============================================
# ADMIN SITE CUSTOMIZATION
# ============================================
restricted_admin_site.site_header = "RONOSYSTEMS ADMINISTRATION"
restricted_admin_site.site_title = "Administration Portal"
restricted_admin_site.index_title = "Welcome to RonoSystems Administration"


urlpatterns = [
    # Home
    path('', views.home, name='home'),
    path('api/', views.api_root, name='api-root'),

    # Restricted admin
    path('admin/', restricted_admin_site.urls),

    # No-access
    path('no-access/', views_guest.no_access, name='no-access'),

    # ============================================
    # WEB AUTH — allauth
    # ============================================
    path('auth/', include('allauth.urls')),
    path('auth/', include('apps.accounts.web_urls', namespace='web_accounts')),

    # ============================================
    # WEB INTERFACE
    # ============================================
    path('dashboard/', include('apps.company.dashboard_urls')),
    path('company/', include('apps.company.urls_web')),
    path('epa_shop/', include('apps.epa_shop.urls_web')),
    path('kuku_biz/', include('apps.kuku_biz.urls')),
    path('chama/', include('apps.chama.urls')),
    path('business-types/', include('apps.business_types.urls')),
    path('subscription-expired/', company_views.subscription_expired, name='subscription-expired'),
    path('payments/kcb/callback/', company_views.company_payments_callback, name='kcb-callback'),
    path('companies/', include('apps.companies.web_urls')),
    path('employees/', include('apps.employees.web_urls')),
    path('losses/', include('apps.losses.urls', namespace='losses')),
    path('treasury/', include('apps.treasury.urls')),
    path('plans/', include('apps.plans.urls')),
    path('reports/', include('apps.reports.urls')),
    path('settings/', include('apps.settings.urls')),
    path('profile/', include('apps.accounts.profile_urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('workshop/', include('apps.workshop.urls', namespace='workshop')),
    path('mpesa/', include('apps.mpesa.urls')),

    # ============================================
    # API ENDPOINTS
    # ============================================
    path('api/auth/', include('apps.accounts.urls', namespace='api_accounts')),
    path('api/companies/', include('apps.companies.urls')),
    path('api/epa/', include('apps.epa_shop.urls')),
    path('api/supermarket/', include('apps.supermarket.urls')),

    # ============================================
    # CORE PAGES & PWA
    # ============================================
    path('contact/', contact, name='contact'),
    path('ai/assistant/', ai_assistant, name='ai-assistant'),
    path('manifest.json', manifest_view, name='manifest'),
    path('sw.js', service_worker, name='service-worker'),
    path('.well-known/assetlinks.json', asset_links, name='asset_links'),

    # ============================================
    # TEMPLATE PAGES — MOVED TO templates/website/
    # ============================================
    path('about/', TemplateView.as_view(template_name='website/about.html'), name='about'),
    path('help/', TemplateView.as_view(template_name='website/help.html'), name='help'),
    path('support/', TemplateView.as_view(template_name='website/support.html'), name='support'),
    path('feedback/', TemplateView.as_view(template_name='website/feedback.html'), name='feedback'),
    path('features/', TemplateView.as_view(template_name='website/features.html'), name='features'),
    path('faq/', TemplateView.as_view(template_name='website/faq.html'), name='faq'),
    path('documentation/', TemplateView.as_view(template_name='website/documentation.html'), name='documentation'),
    path('ai-assistant/', TemplateView.as_view(template_name='website/ai_assistant.html'), name='ai-assistant-page'),
    path('invoicing/', TemplateView.as_view(template_name='website/invoicing.html'), name='invoicing'),
    path('pricing/', TemplateView.as_view(template_name='website/pricing.html'), name='pricing'),
    path('terms/', TemplateView.as_view(template_name='website/terms.html'), name='terms'),
    path('privacy/', TemplateView.as_view(template_name='website/privacy.html'), name='privacy'),
]


# ============================================
# STATIC & MEDIA (DEBUG ONLY)
# ============================================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)