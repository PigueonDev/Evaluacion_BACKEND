"""Punto de entrada de rutas: enlaza las URLs de cada aplicación. Sin Django Admin."""

from django.urls import include, path, re_path

from .archivos import archivo_protegido

urlpatterns = [
    re_path(r"^media/(?P<ruta>.+)$", archivo_protegido, name="archivo_protegido"),
    path("", include("institucional.urls")),
    path("servicios/", include("servicios.urls")),
    path("organizaciones/", include("organizaciones.urls")),
]

handler403 = "institucional.views.acceso_denegado"
