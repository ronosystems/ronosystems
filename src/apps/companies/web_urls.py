from django.urls import path
from . import web_views

app_name = 'companies'

urlpatterns = [
    # ============================================
    # Company Management (Super Admin)
    # ============================================
    path('', web_views.company_list, name='company-list'),
    path('create/', web_views.company_create, name='company-create'),
    path('<int:pk>/', web_views.company_detail, name='company-detail'),
    path('<int:pk>/edit/', web_views.company_edit, name='company-edit'),
    path('<int:pk>/delete/', web_views.company_delete, name='company-delete'),
]