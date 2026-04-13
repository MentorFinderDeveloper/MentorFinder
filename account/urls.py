from django.urls import path

import account.views as views


urlpatterns = [
    path('login', views.login),
    path('register', views.register),
    path("follow/mentors", views.followed_mentors),
    path("follow/mentors/<int:mentor_id>", views.follow_mentor),
]
