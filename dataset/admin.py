from django.contrib import admin
from .models import Mentor, Paper


@admin.register(Mentor)
class MentorAdmin(admin.ModelAdmin):
    list_display = ("id", "Chinese_name", "English_name", "research_direction", "email", "paper_ids")



@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "publish_date", "author_names")