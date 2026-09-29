from django.urls import path

from . import views

app_name = "servicios"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("actividades/", views.actividades, name="actividades"),
    path("agenda/", views.agenda, name="agenda"),
    path("", views.catalogo, name="catalogo"),
    path("<slug:slug>/", views.detalle, name="detalle"),
]
