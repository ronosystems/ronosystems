from django.urls import path
from . import dashboard_router

urlpatterns = [
    path('', dashboard_router.dashboard_router, name='dashboard-router'),
]
