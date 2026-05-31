from django.urls import path
from django.views.decorators.csrf import csrf_exempt

import dataset.views as views


def api_path(route, view, kwargs=None, name=None):
    return path(route, csrf_exempt(view), kwargs=kwargs, name=name)


urlpatterns = [
    api_path("dataset/papers", views.create_paper),
    api_path("dataset/papers/<int:paper_id>", views.paper_detail),
    api_path("dataset/mentors", views.create_mentor),
    api_path("dataset/mentors/custom", views.create_custom_mentor),
    api_path("dataset/mentors/mine", views.my_custom_mentors),
    api_path("dataset/mentors/<int:mentor_id>", views.mentor_detail),
    api_path("dataset/mentors/<int:mentor_id>/recent-direction-analysis", views.mentor_recent_direction_analysis),
    api_path("dataset/weekly-push/latest", views.weekly_push_latest),
    api_path("dataset/weekly-push/history", views.weekly_push_history),
    api_path("dataset/weekly-push/personalized", views.weekly_push_personalized),
    api_path("dataset/weekly-push/personalized/history", views.weekly_push_personalized_history),
    api_path("dataset/scheduled-task-runs/latest", views.scheduled_task_runs_latest),
    api_path("timeline", views.paper_timeline_view, name="paper_timeline_no_slash"),
    api_path("timeline/", views.paper_timeline_view, name="paper_timeline"),
]
