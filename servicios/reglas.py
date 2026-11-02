"""Reglas de ingreso de actividades acordadas con el cliente (matriz SGR, octubre 2026)."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

MAXIMO_ACTIVIDADES_POR_DIA = 7
DIAS_HABILES = 5


def inicio_semana(fecha):
	return fecha - timedelta(days=fecha.weekday())


def fin_semana_laboral(fecha):
	return inicio_semana(fecha) + timedelta(days=DIAS_HABILES - 1)


def semana_abierta(fecha, hoy=None):
	"""La semana de `fecha` admite cambios solo de lunes a viernes de esa misma semana."""
	hoy = hoy or timezone.localdate()
	return hoy.weekday() < DIAS_HABILES and inicio_semana(fecha) == inicio_semana(hoy)


def validar_fecha_ingreso(fecha, hoy=None):
	hoy = hoy or timezone.localdate()
	if fecha is None:
		raise ValidationError({"fecha": "Indica la fecha de la actividad."})
	if fecha > hoy:
		raise ValidationError({"fecha": "No se registran actividades con fecha futura."})
	if fecha.weekday() >= DIAS_HABILES:
		raise ValidationError({"fecha": "Solo se registran actividades de lunes a viernes."})
	if not semana_abierta(fecha, hoy):
		raise ValidationError({"fecha": (
			f"La semana laboral del {inicio_semana(fecha):%d/%m} al {fin_semana_laboral(fecha):%d/%m} ya cerró. "
			"Las actividades se ingresan dentro de su semana y no se traspasan a la siguiente."
		)})


def validar_cupo_diario(funcionario, fecha, excluir_pk=None):
	from .models import Actividad

	registradas = Actividad.objects.filter(funcionario=funcionario, fecha=fecha).exclude(estado="anulada")
	if excluir_pk:
		registradas = registradas.exclude(pk=excluir_pk)
	if registradas.count() >= MAXIMO_ACTIVIDADES_POR_DIA:
		raise ValidationError({"fecha": f"Ya registraste {MAXIMO_ACTIVIDADES_POR_DIA} actividades el {fecha:%d/%m/%Y}. Es el máximo diario."})


def validar_semana_editable(actividad, hoy=None):
	if not semana_abierta(actividad.fecha, hoy):
		raise ValidationError("La semana laboral de esta actividad ya cerró: queda bloqueada.")
