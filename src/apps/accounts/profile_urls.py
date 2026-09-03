from django.urls import path
from . import profile_views

urlpatterns = [
    path('', profile_views.profile_view, name='profile'),
    path('update/', profile_views.profile_update, name='profile-update'),
    path('picture/upload/', profile_views.profile_picture_upload, name='profile-picture-upload'),
    path('picture/remove/', profile_views.profile_picture_remove, name='profile-picture-remove'),
    path('password/change/', profile_views.password_change, name='password-change'),
    path('password/reset/', profile_views.password_reset_request, name='password-reset'),
]
