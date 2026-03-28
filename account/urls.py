from django.urls import path

import account.views as views


urlpatterns = [
    path('login', views.login),
    path('register', views.register),
]
