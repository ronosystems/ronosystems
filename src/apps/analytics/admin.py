from django.contrib import admin
from .models import Visit, IPGeoCache


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'page', 'ip_address', 'country', 'city',
                    'device_type', 'browser', 'os', 'user_name')
    list_filter = ('device_type', 'country', 'browser', 'os')
    search_fields = ('ip_address', 'city', 'country', 'page', 'user_name', 'user_email')
    date_hierarchy = 'created_at'


@admin.register(IPGeoCache)
class IPGeoCacheAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'city', 'country', 'resolved_at')
    search_fields = ('ip_address', 'city', 'country')
