from django.urls import path

import account.views as views


urlpatterns = [
    path('login', views.login),
    path('register', views.register),
    path('register/verification-code', views.send_email_verification_code),
    path("follow/mentors", views.followed_mentors),
    path("follow/mentors/<int:mentor_id>", views.follow_mentor),
    path("follow/subjects", views.followed_subjects),
    path("follow/subjects/<str:subject>", views.follow_subject),
    path("follow/users", views.followed_users),
    path("follow/followers", views.follower_users),
    path("follow/users/<int:user_id>", views.follow_user),
    path("search/users", views.search_users),
    path("users/<int:user_id>/profile", views.public_user_profile),
    path("profile/me", views.my_profile),
    path("profile/avatar", views.upload_avatar),
    path("profile/mentor-verification-request", views.mentor_verification_request),
    path("management/users", views.admin_users),
    path("management/users/<int:user_id>", views.admin_user_detail),
    path("management/verification-requests/<int:request_id>", views.admin_verification_request_detail),
]
