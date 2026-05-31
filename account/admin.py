"""admin 配置：注册并定制 `account` 应用在 Django 管理后台的展示。

- 提供 `CustomUserAdmin` 用于在用户后台展示扩展字段。
- 为 `UserProfile`、`UserFollow`、`PushRecord` 提供简洁的后台列表配置。
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from account.models import PushRecord, User, UserFollow, UserProfile


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("扩展信息", {"fields": ("role", "real_name")}),
    )
    list_display = ("username", "email", "real_name", "role", "is_staff")


admin.site.register(User, CustomUserAdmin)
admin.site.register(UserProfile)


@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    search_fields = ("follower__username", "following__username", "follower__email", "following__email")
    ordering = ("-created_at", "-id")


@admin.register(PushRecord)
class PushRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "period_key", "status", "sent_at", "updated_at")
    list_filter = ("type", "status")
    search_fields = ("user__username", "user__email", "period_key")
    ordering = ("-updated_at", "-id")
