from django.urls import path
from . import views

app_name = 'ai_chatbot'

urlpatterns = [
    path('', views.chatbot_page, name='page'),
    path('send/', views.send_message, name='send'),
]