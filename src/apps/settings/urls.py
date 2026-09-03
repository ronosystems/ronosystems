from django.urls import path
from . import views

app_name = 'settings'

urlpatterns = [
    path('', views.settings_dashboard, name='settings_dashboard'),
    path('update/', views.settings_update, name='settings_update'),
    path('reset/', views.settings_reset, name='settings_reset'),
    path('export/', views.settings_export, name='settings_export'),
    path('import/', views.settings_import, name='settings_import'),
    path('test-email/', views.settings_test_email, name='settings_test_email'),
]