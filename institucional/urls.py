from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "institucional"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("autoridades/", views.autoridades, name="autoridades"),
    path("acceso/", views.AccesoView.as_view(), name="acceso"),
    path("acceso/salir/", auth_views.LogoutView.as_view(), name="salir"),
    path("acceso/verificar/", views.verificar_acceso, name="verificar"),
    path("administracion/", views.panel, name="panel"),
]
