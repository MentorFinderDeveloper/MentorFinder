from django.urls import path
from django.views.decorators.csrf import csrf_exempt

import search.views as views


def api_path(route, view, kwargs=None, name=None):
    return path(route, csrf_exempt(view), kwargs=kwargs, name=name)


urlpatterns = [
    api_path("search/health", views.health),
    api_path("search/mentors", views.mentors),
    api_path("search/papers", views.papers),
]
