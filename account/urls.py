"""URL 路由：将 HTTP 路径映射到 `account.views` 中的视图函数。

路由均使用函数视图，具体的请求方法检查在视图内部完成。
"""

from django.urls import path
from django.views.decorators.csrf import csrf_exempt

import account.views as views


def api_path(route, view, kwargs=None, name=None):
    return path(route, csrf_exempt(view), kwargs=kwargs, name=name)


urlpatterns = [
    api_path('login', views.login),
    api_path('register', views.register),
    api_path('register/verification-code', views.send_email_verification_code),
    api_path("password-reset/verification-code", views.send_password_reset_verification_code),
    api_path("password-reset", views.reset_password_with_email_code),
    api_path("follow/mentors", views.followed_mentors),
    api_path("follow/mentors/<int:mentor_id>", views.follow_mentor),
    api_path("follow/counts", views.follow_counts),
    api_path("follow/subjects", views.followed_subjects),
    api_path("follow/subjects/available", views.available_subjects),
    api_path("follow/subjects/followed", views.followed_subject_summaries),
    api_path("follow/subjects/<str:subject>/papers", views.followed_subject_papers),
    api_path("follow/subjects/<str:subject>", views.follow_subject),
    api_path("follow/users", views.followed_users),
    api_path("follow/followers", views.follower_users),
    api_path("follow/users/<int:user_id>", views.follow_user),
    api_path("search/users", views.search_users),
    api_path("users/<int:user_id>/profile", views.public_user_profile),
    api_path("profile/me", views.my_profile),
    api_path("profile/username", views.update_username),
    api_path("profile/avatar", views.upload_avatar),
    api_path("profile/mentor-verification-request", views.mentor_verification_request),
    api_path("management/users", views.admin_users),
    api_path("management/users/<int:user_id>", views.admin_user_detail),
    api_path("management/verification-requests/<int:request_id>", views.admin_verification_request_detail),
]
