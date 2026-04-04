from django.urls import path

import dataset.views as views


urlpatterns = [
    path("dataset/papers", views.create_paper),
    path("dataset/mentors", views.create_mentor),
]
