from django.urls import path

import account.views as views


urlpatterns = [
    path('login', views.login),
    path('register', views.register),
    path("follow/mentors", views.followed_mentors),
    path("follow/mentors/<int:mentor_id>", views.follow_mentor),
    path("follow/users", views.followed_users),
    path("follow/users/<int:user_id>", views.follow_user),
    path("search/users", views.search_users),
    path("profile/me", views.my_profile),
    path("profile/mentor-verification-request", views.mentor_verification_request),
    path("management/users", views.admin_users),
    path("management/users/<int:user_id>", views.admin_user_detail),
    path("management/verification-requests/<int:request_id>", views.admin_verification_request_detail),
]
