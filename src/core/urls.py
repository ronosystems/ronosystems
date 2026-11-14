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

# ============================================
# HELPER FUNCTION FOR DYNAMIC TEMPLATES
# ============================================
def get_template(system_tpl, company_tpl):
    """
    Returns a view that serves either the system template or company template
    based on whether 'current_company' is present on the request.
    """
    def view(request, *args, **kwargs):
        # Check if current_company is set (by your middleware)
        template_name = company_tpl if getattr(request, 'current_company', None) else system_tpl
        return TemplateView.as_view(template_name=template_name)(request, *args, **kwargs)
    return view


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
    # TEMPLATE PAGES — DYNAMIC ROUTING (COMPANY VS SYSTEM)
    # ============================================
    path('about/', get_template('website/about.html', 'website/company_about.html'), name='about'),
    path('help/', get_template('website/help.html', 'website/company_help.html'), name='help'),
    path('support/', get_template('website/support.html', 'website/company_support.html'), name='support'),
    path('feedback/', get_template('website/feedback.html', 'website/company_feedback.html'), name='feedback'),
    path('features/', get_template('website/features.html', 'website/company_features.html'), name='features'),
    path('faq/', get_template('website/faq.html', 'website/company_faq.html'), name='faq'),
    path('documentation/', get_template('website/documentation.html', 'website/company_documentation.html'), name='documentation'),
    path('ai-assistant/', get_template('website/ai_assistant.html', 'website/company_ai_assistant.html'), name='ai-assistant-page'),
    path('invoicing/', get_template('website/invoicing.html', 'website/company_invoicing.html'), name='invoicing'),
    path('pricing/', get_template('website/pricing.html', 'website/company_pricing.html'), name='pricing'),
    path('terms/', get_template('website/terms.html', 'website/company_terms.html'), name='terms'),
    path('privacy/', get_template('website/privacy.html', 'website/company_privacy.html'), name='privacy'),
]


# ============================================
# STATIC & MEDIA (DEBUG ONLY)
# ============================================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)