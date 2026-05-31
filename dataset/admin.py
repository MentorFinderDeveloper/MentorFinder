from django.contrib import admin
from .models import Mentor, Paper, ScheduledTaskRun

@admin.register(Mentor)
class MentorAdmin(admin.ModelAdmin):
    list_display = ("id", "Chinese_name", "English_name", "research_direction", "email", "owner", "paper_ids")



@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "publish_date", "author_names")


@admin.register(ScheduledTaskRun)
class ScheduledTaskRunAdmin(admin.ModelAdmin):
    list_display = ("id", "task_name", "status", "progress_message", "progress_current", "progress_total", "started_at", "finished_at", "last_heartbeat_at")
    list_filter = ("task_name", "status")
    search_fields = ("task_name", "error_message", "progress_message", "progress_log")
    readonly_fields = (
        "task_name",
        "status",
        "started_at",
        "finished_at",
        "error_message",
        "progress_message",
        "progress_current",
        "progress_total",
        "progress_log",
        "last_heartbeat_at",
    )
