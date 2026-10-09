"""Punto de entrada de rutas: enlaza las URLs de cada aplicación."""

from django.contrib import admin
from django.urls import include, path, re_path

from institucional.views import AccesoView

from .archivos import archivo_protegido

urlpatterns = [
    # El login del admin usa la misma vista que "Acceso funcionarios" para aplicar el bloqueo por intentos.
    path("admin/login/", AccesoView.as_view()),
    path("admin/", admin.site.urls),
    re_path(r"^media/(?P<ruta>.+)$", archivo_protegido, name="archivo_protegido"),
    path("", include("institucional.urls")),
    path("servicios/", include("servicios.urls")),
]
