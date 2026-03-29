from django.urls import path

import search.views as views


urlpatterns = [
    path("search/health", views.health),
]

