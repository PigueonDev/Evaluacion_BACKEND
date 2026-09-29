from django.urls import path

from . import views

app_name = "institucional"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("autoridades/", views.autoridades, name="autoridades"),
]
