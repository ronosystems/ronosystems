from django.urls import path
from . import views

app_name = 'mpesa'

urlpatterns = [
    path('stk-push/',   views.mpesa_stk_push,   name='stk_push'),
    path('stk-status/', views.mpesa_stk_status, name='stk_status'),
    path('confirm/',    views.mpesa_confirm,    name='confirm'),
    path('callback/',   views.mpesa_callback,   name='callback'),
]