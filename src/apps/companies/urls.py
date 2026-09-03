from django.urls import path
from . import views


urlpatterns = [

    
    # Super Admin Dashboard
    path('dashboard/stats/', views.DashboardStatsView.as_view(), name='dashboard-stats'),
    
    # Super Admin Company Management
    path('companies/', views.CompanyListView.as_view(), name='company-list'),
    path('companies/<int:pk>/', views.CompanyDetailView.as_view(), name='company-detail'),
    
    # Super Admin Business Type Management
    path('business-types/', views.BusinessTypeListView.as_view(), name='business-type-list'),
    path('business-types/<int:pk>/', views.BusinessTypeDetailView.as_view(), name='business-type-detail'),
]
