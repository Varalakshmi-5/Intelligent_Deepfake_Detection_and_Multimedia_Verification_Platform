from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, OTP


class UserAdmin(DjangoUserAdmin):
    model = User
    list_display = ("email", "name", "role", "is_verified", "is_active", "date_joined")
    list_filter = ("role", "is_verified", "is_active")
    search_fields = ("email", "name")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name",)}),
        ("Permissions", {"fields": ("role", "is_verified", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "name", "password1", "password2", "role")}),
    )


admin.site.register(User, UserAdmin)
admin.site.register(OTP)
