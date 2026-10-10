from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('visits/', views.visit_dashboard, name='visit_dashboard'),
    path('visits/mark-read/', views.mark_visits_read, name='mark_visits_read'),
    path('visits/erase/', views.erase_visits, name='erase_visits'),
]