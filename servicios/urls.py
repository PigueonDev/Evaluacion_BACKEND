from django.urls import path

from . import views

app_name = "servicios"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("actividades/", views.actividades, name="actividades"),
    path("actividades/nueva/", views.actividad_nueva, name="actividad_nueva"),
    path("actividades/codigo/", views.actividad_por_codigo, name="actividad_codigo"),
    path("actividades/<int:pk>/", views.actividad_detalle, name="actividad_detalle"),
    path("actividades/<int:pk>/editar/", views.actividad_editar, name="actividad_editar"),
    path("actividades/<int:pk>/anular/", views.actividad_anular, name="actividad_anular"),
    path("casos/", views.casos, name="casos"),
    path("casos/nuevo/", views.caso_nuevo, name="caso_nuevo"),
    path("casos/<int:pk>/", views.caso_detalle, name="caso_detalle"),
    path("casos/<int:pk>/editar/", views.caso_editar, name="caso_editar"),
    path("casos/<int:pk>/desactivar/", views.caso_desactivar, name="caso_desactivar"),
    path("casos/<int:pk>/gestiones/nueva/", views.gestion_nueva, name="gestion_nueva"),
    path("casos/<int:caso_pk>/gestiones/<int:pk>/editar/", views.gestion_editar, name="gestion_editar"),
    path("casos/<int:caso_pk>/gestiones/<int:pk>/desactivar/", views.gestion_desactivar, name="gestion_desactivar"),
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/nueva/", views.compromiso_nuevo, name="compromiso_nuevo"),
    path("agenda/resumen/", views.resumen_agenda, name="resumen_agenda"),
    path("agenda/<int:pk>/", views.compromiso_detalle, name="compromiso_detalle"),
    path("agenda/<int:pk>/editar/", views.compromiso_editar, name="compromiso_editar"),
    path("agenda/<int:pk>/desactivar/", views.compromiso_desactivar, name="compromiso_desactivar"),
    path("consulta/", views.consulta, name="consulta"),
    path("consulta/actividades/<int:pk>/", views.consulta_actividad, name="consulta_actividad"),
    path("", views.catalogo, name="catalogo"),
    path("<slug:slug>/", views.detalle, name="detalle"),
]
