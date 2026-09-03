from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'role', 'company', 'is_active', 'is_verified')
    list_filter = ('role', 'is_active', 'is_verified', 'two_factor_enabled')
    search_fields = ('email', 'username', 'phone')
    fieldsets = UserAdmin.fieldsets + (
        ('RonoSystems Custom Fields', {
            'fields': ('role', 'company', 'phone', 'is_verified', 'two_factor_enabled')
        }),
    )
