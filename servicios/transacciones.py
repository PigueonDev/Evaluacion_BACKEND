"""Transacción «Registrar actividad»: actividad + tareas preparatorias + auditoría en una sola unidad."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from institucional.models import Funcionario

from .models import Actividad, Auditoria, TareaPreparatoria
from .reglas import validar_cupo_diario, validar_fecha_ingreso, validar_semana_editable


def _auditar(usuario, accion, actividad, anterior=None):
	Auditoria.objects.create(
		usuario=usuario,
		accion=accion,
		entidad="Actividad",
		identificador=str(actividad.codigo_evidencia),
		valor_anterior=anterior,
		valor_nuevo={"estado": actividad.estado, "fecha": actividad.fecha.isoformat(), "tareas": actividad.tareas.count()},
	)


@transaction.atomic
def registrar_actividad(actividad, tareas, funcionario, usuario, hoy=None):
	"""Guarda la actividad y sus tareas. Si una regla falla no queda nada a medias.

	`actividad` es una instancia sin guardar; `tareas` es una lista de TareaPreparatoria sin guardar.
	"""
	# Bloquea la fila del funcionario para que dos ingresos simultáneos no superen el cupo diario.
	funcionario = Funcionario.objects.select_for_update().get(pk=funcionario.pk)
	validar_fecha_ingreso(actividad.fecha, hoy)
	validar_cupo_diario(funcionario, actividad.fecha)
	if not tareas:
		raise ValidationError("Agrega al menos una tarea preparatoria.")
	actividad.funcionario = funcionario
	actividad.estado = "pendiente"
	actividad.full_clean()
	actividad.save()
	for tarea in tareas:
		tarea.actividad = actividad
		tarea.realizada = False
		tarea.full_clean()
		tarea.save()
	_auditar(usuario, "registrar_actividad", actividad)
	return actividad


@transaction.atomic
def actualizar_actividad(actividad, usuario, hoy=None):
	anterior = Actividad.objects.select_for_update().get(pk=actividad.pk)
	validar_semana_editable(anterior, hoy)
	if anterior.estado != "pendiente":
		raise ValidationError("Solo se modifica una actividad pendiente de aprobación.")
	validar_fecha_ingreso(actividad.fecha, hoy)
	validar_cupo_diario(actividad.funcionario, actividad.fecha, excluir_pk=actividad.pk)
	actividad.full_clean()
	actividad.save()
	_auditar(usuario, "editar_actividad", actividad, {"fecha": anterior.fecha.isoformat()})
	return actividad


@transaction.atomic
def marcar_tarea(tarea, realizada, usuario, hoy=None):
	actividad = Actividad.objects.select_for_update().get(pk=tarea.actividad_id)
	validar_semana_editable(actividad, hoy)
	if actividad.estado != "pendiente":
		raise ValidationError("La actividad ya fue revisada; sus tareas no cambian.")
	tarea.realizada = realizada
	tarea.realizada_en = timezone.now() if realizada else None
	tarea.save(update_fields=["realizada", "realizada_en"])
	return tarea


@transaction.atomic
def revisar_actividad(actividad, decision, usuario, observacion="", hoy=None):
	"""El Supervisor aprueba o rechaza. Solo se aprueba con todas las tareas realizadas."""
	actividad = Actividad.objects.select_for_update().get(pk=actividad.pk)
	validar_semana_editable(actividad, hoy)
	if actividad.estado != "pendiente":
		raise ValidationError("La actividad ya fue revisada.")
	if decision == "aprobar":
		if not actividad.tareas_completas:
			raise ValidationError("No se puede aprobar: hay tareas preparatorias sin realizar.")
		actividad.estado = "validada"
	elif decision == "rechazar":
		if not observacion.strip():
			raise ValidationError("Indica el motivo del rechazo.")
		actividad.estado = "rechazada"
	else:
		raise ValidationError("Decisión no válida.")
	actividad.revisada_por = usuario
	actividad.revisada_en = timezone.now()
	actividad.observacion_revision = observacion.strip()
	actividad.save(update_fields=["estado", "revisada_por", "revisada_en", "observacion_revision"])
	_auditar(usuario, f"{decision}_actividad", actividad, {"estado": "pendiente"})
	return actividad


def tareas_desde_formset(formset):
	tareas = []
	for form in formset.forms:
		if not form.has_changed() or form.cleaned_data.get("DELETE"):
			continue
		tareas.append(TareaPreparatoria(tipo=form.cleaned_data["tipo"], descripcion=form.cleaned_data.get("descripcion", "")))
	return tareas
