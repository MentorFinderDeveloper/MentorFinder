from django.urls import path, include
import board.views as views

urlpatterns = [
    path('startup', views.startup),
    path('boards', views.boards),
    # TODO Start: [Student] add routing paths for `boards/<index>` and `user/<username>`

    # TODO End: [Student] add routing paths for `boards/<index>` and `user/<username>`

]
