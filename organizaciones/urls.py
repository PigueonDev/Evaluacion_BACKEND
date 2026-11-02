from django.urls import path

from . import views

app_name = "organizaciones"

urlpatterns = [
	path("", views.listado, name="listado"),
	path("nueva/", views.crear, name="crear"),
	path("<int:pk>/", views.detalle, name="detalle"),
	path("<int:pk>/editar/", views.editar, name="editar"),
	path("<int:pk>/eliminar/", views.eliminar, name="eliminar"),
	path("<int:pk>/verificar/", views.verificar, name="verificar"),
]
