from django.urls import path
from . import dashboard_router
from . import general_views

urlpatterns = [
    path('', dashboard_router.dashboard_router, name='dashboard-router'),
    path('general/', general_views.general_dashboard, name='general-dashboard'),
]
