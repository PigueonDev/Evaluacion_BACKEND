"""Contraseña temporal: el primer ingreso obliga a definir una clave propia."""

from django.contrib.auth import get_user_model

from .models import EstadoClave

User = get_user_model()


def marcar_clave_temporal(usuario, temporal):
	estado, _ = EstadoClave.objects.update_or_create(usuario=usuario, defaults={"debe_cambiar_clave": temporal})
	return estado


class ClaveTemporalMiddleware:
	"""Mientras la contraseña sea temporal, solo se puede cambiarla o cerrar sesión."""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		from django.shortcuts import redirect

		if clave_temporal_pendiente(getattr(request, "user", None)):
			ruta = request.path
			if not ruta.startswith(("/acceso/cambiar-clave/", "/acceso/salir/", "/static/", "/media/")):
				return redirect("institucional:cambiar_clave")
		return self.get_response(request)


def clave_temporal_pendiente(usuario):
	if usuario is None or not getattr(usuario, "is_authenticated", False):
		return False
	return EstadoClave.objects.filter(usuario_id=usuario.pk, debe_cambiar_clave=True).exists()
