"""Punto de entrada de rutas: enlaza las URLs de cada aplicación. Sin Django Admin."""

from django.urls import include, path, re_path

from .archivos import archivo_protegido

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    re_path(r"^media/(?P<ruta>.+)$", archivo_protegido, name="archivo_protegido"),
    path("", include("institucional.urls")),
    path("servicios/", include("servicios.urls")),
    path("organizaciones/", include("organizaciones.urls")),
    path("oficina/", include("oficina.urls")),
    path("api/", include("api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger/", SpectacularSwaggerView.as_view(), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(), name="redoc"),
]

handler403 = "institucional.views.acceso_denegado"
