from django.urls import path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerSplitView

from . import views

app_name = "api"

urlpatterns = [
    # Autenticación JWT
    path("token/", views.ObtenerTokenView.as_view(), name="token_obtener"),
    path("token/refresh/", views.RenovarTokenView.as_view(), name="token_renovar"),
    path("token/verify/", views.VerificarTokenView.as_view(), name="token_verificar"),
    path("token/blacklist/", views.RevocarTokenView.as_view(), name="token_revocar"),
    path("yo/", views.perfil_actual, name="perfil_actual"),
    # Mantenedor 1: usuarios
    path("usuarios/", views.usuarios_lista, name="usuarios_lista"),
    path("usuarios/<int:pk>/", views.usuario_detalle, name="usuario_detalle"),
    # Mantenedor 2: cartas de Oficina de Partes
    path("cartas/", views.cartas_lista, name="cartas_lista"),
    re_path(r"^cartas/exportar/(?P<formato>excel|pdf)/$", views.cartas_exportar, name="cartas_exportar"),
    path("cartas/<int:pk>/", views.carta_detalle, name="carta_detalle"),
    # Transacción: registrar actividad
    path("actividades/", views.actividades_lista, name="actividades_lista"),
    re_path(r"^actividades/exportar/(?P<formato>excel|pdf)/$", views.actividades_exportar, name="actividades_exportar"),
    path("actividades/<int:pk>/", views.actividad_detalle, name="actividad_detalle"),
    path("actividades/<int:pk>/revision/", views.actividad_revision, name="actividad_revision"),
    path("actividades/<int:pk>/tareas/<int:tarea_pk>/", views.tarea_marcar, name="tarea_marcar"),
    # Documentación OpenAPI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("swagger/", SpectacularSwaggerSplitView.as_view(url_name="api:schema"), name="swagger"),
    path("redoc/", SpectacularRedocView.as_view(url_name="api:schema"), name="redoc"),
    re_path(r"^(?P<ruta>.*)$", views.ruta_no_encontrada, name="no_encontrada"),
]
