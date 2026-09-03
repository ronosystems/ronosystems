from django.urls import path
from . import views
from . import business_type_views

urlpatterns = [

    # Business Type Registry
    path('business-types/available/', 
         business_type_views.AvailableBusinessTypesView.as_view(), 
         name='available-business-types'),
    path('business-types/validate/', 
         business_type_views.ValidateBusinessTypeView.as_view(), 
         name='validate-business-type'),
    path('business-types/initialize/', 
         business_type_views.InitializeBusinessTypesView.as_view(), 
         name='initialize-business-types'),

    path('', views.business_type_list, name='business-type-list'),
    path('create/', views.business_type_create, name='business-type-create'),
    path('<int:pk>/edit/', views.business_type_edit, name='business-type-edit'),
    path('<int:pk>/delete/', views.business_type_delete, name='business-type-delete'),
]
