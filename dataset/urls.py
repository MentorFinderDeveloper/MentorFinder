from django.urls import path

import dataset.views as views


urlpatterns = [
    path("dataset/papers", views.create_paper),
    path("dataset/papers/<int:paper_id>", views.paper_detail),
    path("dataset/mentors", views.create_mentor),
    path("dataset/mentors/custom", views.create_custom_mentor),
    path("dataset/mentors/mine", views.my_custom_mentors),
    path("dataset/mentors/<int:mentor_id>", views.mentor_detail),
    path("dataset/mentors/<int:mentor_id>/recent-direction-analysis", views.mentor_recent_direction_analysis),
    path("dataset/weekly-push/latest", views.weekly_push_latest),
    path("dataset/weekly-push/history", views.weekly_push_history),
    path("dataset/weekly-push/personalized", views.weekly_push_personalized),
    path("timeline", views.paper_timeline_view, name="paper_timeline_no_slash"),
    path("timeline/", views.paper_timeline_view, name="paper_timeline"),
]
