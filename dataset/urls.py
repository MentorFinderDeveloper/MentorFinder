from django.urls import path

import dataset.views as views


urlpatterns = [
    path("dataset/papers", views.create_paper),
    path("dataset/papers/<int:paper_id>", views.paper_detail),
    path("dataset/mentors", views.create_mentor),
    path("dataset/mentors/<int:mentor_id>", views.mentor_detail),
    path('timeline/',views.paper_timeline_view, name = 'paper_timeline'),
]
