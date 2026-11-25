from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from apps.companies import web_views as company_views
from apps.accounts.admin_site import restricted_admin_site
from apps.accounts import views_guest
from core.views import contact, manifest_view, service_worker, asset_links, admin_contact_messages
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
    def view(request, *args, **kwargs):
        template_name = company_tpl if getattr(request, 'company', None) else system_tpl
        return TemplateView.as_view(template_name=template_name)(request, *args, **kwargs)
    return view

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    path('api/', views.api_root, name='api-root'),

    # Restricted admin
    path('admin/', restricted_admin_site.urls),

    # DASHBOARD
    path('dashboard/', views.dashboard_router, name='dashboard-router'),
    path('superadmin/dashboard/', views.super_admin_dashboard, name='super-admin-dashboard'),

    # ============================================
    # WEB AUTH — allauth (MARA MOJA TU)
    # ============================================
    path('accounts/', include('allauth.urls')),
    path('auth/', include('apps.accounts.web_urls', namespace='web_accounts')),
    path('auth/apply-company/', views_guest.apply_company, name='apply_company'),

    # ============================================
    # STAFF + USERS CRUD - MARA MOJA TU, KATIKA ROOT
    # Hii inatoa:
    #   /staff/  -> Company Admin Staff CRUD (staff_views.py)
    #   /users/  -> Super Admin Users CRUD (users_views.py)
    # Usii-include tena chini ya company/ au users/ au api/auth/
    # ============================================
    path('', include('apps.accounts.urls')),

    # ============================================
    # WEB INTERFACE
    # ============================================
    path('epa_shop/', include('apps.epa_shop.urls_web', namespace='epa_shop')),
    path('cart/', include('apps.cart_orders.urls', namespace='cart-orders')),
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('kuku_biz/', include('apps.kuku_biz.urls')),
    path('chama/', include('apps.chama.urls')),
    path('business-types/', include('apps.companies.business_types_urls')),
    path('subscription-expired/', company_views.subscription_expired, name='subscription-expired'),
    path('payments/kcb/callback/', company_views.company_payments_callback, name='kcb-callback'),
    path('companies/', include('apps.companies.web_urls')),
    path('losses/', include('apps.losses.urls', namespace='losses')),
    path('treasury/', include('apps.treasury.urls')),
    path('plans/', include('apps.plans.urls')),
    path('reports/', include('apps.reports.urls')),
    path('settings/', include('apps.settings.urls')),
    path('profile/', include('apps.accounts.profile_urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('workshop/', include('apps.workshop.urls', namespace='workshop')),
    path('mpesa/', include('apps.mpesa.urls')),
    path('ai/chatbot/', include('apps.ai_chatbot.urls')),
    path('contact-messages/', admin_contact_messages, name='admin_contact_messages'),
    path('contact-messages/delete/', views.delete_contact_messages, name='delete_contact_messages'),
    path('notifications/', views.notification_center, name='notification_center'),

    # ============================================
    # API ENDPOINTS
    # ============================================
    # IMEONDOLEWA: path('api/auth/', include('apps.accounts.urls', namespace='api_accounts'))
    # Sababu: apps.accounts.urls ni WEB views (render HTML), sio API.
    # Ukiihitaji API ya auth, tengeneza apps/accounts/api_urls.py tofauti.
    path('api/companies/', include('apps.companies.urls')),
    path('api/epa_shop/', include('apps.epa_shop.urls', namespace='epa_shop_api')),
    path('api/supermarket/', include('apps.supermarket.urls')),

    # ============================================
    # CORE PAGES & PWA
    # ============================================
    path('contact/', contact, name='contact'),
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