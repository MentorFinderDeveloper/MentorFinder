from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from account.models import User


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("扩展信息", {"fields": ("role", "real_name")}),
    )
    list_display = ("username", "email", "real_name", "role", "is_staff")


admin.site.register(User, CustomUserAdmin)
