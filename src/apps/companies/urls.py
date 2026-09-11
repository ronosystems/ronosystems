from django.urls import path
from . import views
from . import support_views


urlpatterns = [

    
    # Super Admin Dashboard
    path('dashboard/stats/', views.DashboardStatsView.as_view(), name='dashboard-stats'),
    
    # Super Admin Company Management
    path('companies/', views.CompanyListView.as_view(), name='company-list'),
    path('companies/<int:pk>/', views.CompanyDetailView.as_view(), name='company-detail'),
    
    # Super Admin Business Type Management
    path('business-types/', views.BusinessTypeListView.as_view(), name='business-type-list'),
    path('business-types/<int:pk>/', views.BusinessTypeDetailView.as_view(), name='business-type-detail'),

    path('support/select/', support_views.company_selector, name='support-selector'),
    path('support/enter/<int:company_id>/', support_views.enter_support_mode, name='support-enter'),
    path('support/exit/', support_views.exit_support_mode, name='support-exit'),
    path('support/session/<int:session_id>/delete/', support_views.delete_support_session, name='support-session-delete'),
    path('support/sessions/clear/', support_views.clear_all_support_sessions, name='support-sessions-clear'),
]
