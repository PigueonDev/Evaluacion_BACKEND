from django.urls import path

from . import views

app_name = "oficina"

urlpatterns = [
	path("cartas/", views.cartas, name="cartas"),
	path("cartas/nueva/", views.carta_crear, name="carta_crear"),
	path("cartas/<int:pk>/", views.carta_detalle, name="carta_detalle"),
	path("cartas/<int:pk>/editar/", views.carta_editar, name="carta_editar"),
	path("cartas/<int:pk>/eliminar/", views.carta_eliminar, name="carta_eliminar"),
	path("beneficios/", views.beneficios, name="beneficios"),
	path("beneficios/nuevo/", views.beneficio_crear, name="beneficio_crear"),
	path("beneficios/<int:pk>/", views.beneficio_detalle, name="beneficio_detalle"),
	path("beneficios/<int:pk>/editar/", views.beneficio_editar, name="beneficio_editar"),
	path("beneficios/<int:pk>/eliminar/", views.beneficio_eliminar, name="beneficio_eliminar"),
	path("ausencias/", views.ausencias, name="ausencias"),
	path("ausencias/registrar/", views.ausencia_registrar, name="ausencia_registrar"),
	path("ausencias/<int:pk>/", views.ausencia_detalle, name="ausencia_detalle"),
	path("ausencias/<int:pk>/anular/", views.ausencia_anular, name="ausencia_anular"),
]
