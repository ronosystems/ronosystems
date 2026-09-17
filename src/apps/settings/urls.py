from django.urls import path
from . import views

app_name = 'settings'

urlpatterns = [
    path('', views.settings_dashboard, name='dashboard'),
    path('update/', views.settings_update, name='update'),
    path('reset-category/', views.settings_reset_category, name='reset_category'),
]