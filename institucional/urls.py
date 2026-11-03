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
    path("acceso/recuperar/", views.RecuperarClaveView.as_view(), name="recuperar"),
    path("acceso/recuperar/enviado/", views.RecuperarClaveEnviadoView.as_view(), name="recuperar_enviado"),
    path("acceso/recuperar/<uidb64>/<token>/", views.RecuperarClaveConfirmarView.as_view(), name="recuperar_confirmar"),
    path("acceso/recuperar/listo/", views.RecuperarClaveListoView.as_view(), name="recuperar_listo"),
    path("panel/", views.mi_panel, name="mi_panel"),
    path("administracion/", views.panel, name="panel"),
    path("administracion/cuentas/", views.cuentas, name="cuentas"),
    path("administracion/usuarios/", views.usuarios, name="usuarios"),
    path("administracion/usuarios/nuevo/", views.usuario_crear, name="usuario_crear"),
    path("administracion/usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("administracion/usuarios/<int:pk>/eliminar/", views.usuario_eliminar, name="usuario_eliminar"),
    path("administracion/grupos/", views.grupos, name="grupos"),
    path("administracion/grupos/nuevo/", views.grupo_crear, name="grupo_crear"),
    path("administracion/grupos/<int:pk>/editar/", views.grupo_editar, name="grupo_editar"),
    path("administracion/grupos/<int:pk>/eliminar/", views.grupo_eliminar, name="grupo_eliminar"),
]
