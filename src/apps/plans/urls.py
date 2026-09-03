from django.urls import path
from . import views

app_name = 'plans'

urlpatterns = [
    # Plan Management
    path('', views.plan_list, name='plan-list'),
    path('create/', views.plan_create, name='plan-create'),
    path('<int:pk>/', views.plan_detail, name='plan-detail'),
    path('<int:pk>/edit/', views.plan_edit, name='plan-edit'),
    path('<int:pk>/delete/', views.plan_delete, name='plan-delete'),
    path('<int:pk>/toggle-status/', views.plan_toggle_status, name='plan-toggle-status'),
    
    # Subscription Management
    path('subscriptions/', views.subscription_list, name='subscription-list'),
    path('subscriptions/create/', views.subscription_create, name='subscription-create'),
    path('subscriptions/<int:pk>/', views.subscription_detail, name='subscription-detail'),
    path('subscriptions/<int:pk>/edit/', views.subscription_edit, name='subscription-edit'),
    path('subscriptions/<int:pk>/cancel/', views.subscription_cancel, name='subscription-cancel'),
    
    # API Endpoints
    path('api/plans/', views.get_plans_api, name='plans-api'),
    path('api/plans/<int:pk>/', views.get_plan_detail_api, name='plan-detail-api'),
    path('api/company/<int:company_id>/subscription/', views.get_company_subscription_api, name='company-subscription-api'),
]