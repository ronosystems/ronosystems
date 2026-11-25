from django.urls import path
from . import business_type_views

urlpatterns = [
    path('', business_type_views.business_type_list, name='business-type-list'),
    path('add/', business_type_views.business_type_create, name='business-type-create'),
    path('<int:pk>/edit/', business_type_views.business_type_edit, name='business-type-edit'),
    path('available/', business_type_views.AvailableBusinessTypesView.as_view(), name='available-business-types'),
    path('validate/', business_type_views.ValidateBusinessTypeView.as_view(), name='validate-business-type'),
    path('initialize/', business_type_views.InitializeBusinessTypesView.as_view(), name='initialize-business-types'),
]