"""Transacción «Registrar ausencia»: ausencia + ajuste de metas + auditoría en una sola unidad.

La meta del período se reduce en proporción a los días del período (los mismos que usa el
semáforo) en que el funcionario no estará disponible. Como el semáforo compara cumplimiento contra avance esperado, al bajar el
objetivo el semáforo queda coherente con la ausencia. Si algo falla, no se guarda nada.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from institucional.models import Funcionario
from servicios.models import Auditoria, Meta

from .models import AjusteMeta, Ausencia

CENTESIMA = Decimal("0.01")


def _dias_ausente(funcionario, periodo, excluir_pk=None):
	ausencias = Ausencia.objects.filter(funcionario=funcionario, periodo=periodo, estado="vigente")
	if excluir_pk:
		ausencias = ausencias.exclude(pk=excluir_pk)
	return sum(ausencia.dias for ausencia in ausencias)


def _metas_del_funcionario(funcionario, periodo):
	"""Metas personales del período; si solo hay metas del cargo, crea la meta personal equivalente."""
	personales = list(Meta.objects.select_for_update().filter(periodo=periodo, funcionario=funcionario))
	items_personales = {meta.item_id for meta in personales}
	creadas = []
	for meta_cargo in Meta.objects.filter(periodo=periodo, cargo=funcionario.cargo, funcionario__isnull=True).exclude(item_id__in=items_personales):
		creadas.append(Meta.objects.create(periodo=periodo, item=meta_cargo.item, funcionario=funcionario, objetivo=meta_cargo.objetivo, ponderador=meta_cargo.ponderador))
	return [(meta, False) for meta in personales] + [(meta, True) for meta in creadas]


def _validar(ausencia):
	periodo = ausencia.periodo
	if periodo.estado != "abierto":
		raise ValidationError("El período está cerrado; no admite ausencias.")
	if ausencia.fecha_termino < ausencia.fecha_inicio:
		raise ValidationError({"fecha_termino": "La fecha de término no puede ser anterior al inicio."})
	if ausencia.fecha_inicio < periodo.fecha_inicio or ausencia.fecha_termino > periodo.fecha_termino:
		raise ValidationError(f"La ausencia debe quedar dentro del período ({periodo.fecha_inicio:%d-%m-%Y} a {periodo.fecha_termino:%d-%m-%Y}).")
	traslape = Ausencia.objects.filter(
		funcionario=ausencia.funcionario, estado="vigente",
	).filter(Q(fecha_inicio__lte=ausencia.fecha_termino) & Q(fecha_termino__gte=ausencia.fecha_inicio))
	if traslape.exists():
		raise ValidationError("Ya existe una ausencia vigente que se cruza con esas fechas.")


def _aplicar_factor(ausencia, metas, disponibles_antes, disponibles_despues, hoy):
	ajustes = []
	for meta, creada in metas:
		semaforo_anterior = meta.semaforo(hoy)
		anterior = meta.objetivo
		nuevo = (Decimal(anterior) * disponibles_despues / disponibles_antes).quantize(CENTESIMA, rounding=ROUND_HALF_UP)
		if nuevo <= 0:
			raise ValidationError(f"La meta «{meta.item}» quedaría en cero.")
		meta.objetivo = nuevo
		meta.version += 1
		meta.full_clean()
		meta.save(update_fields=["objetivo", "version"])
		ajustes.append(AjusteMeta(
			ausencia=ausencia, meta=meta, meta_creada=creada,
			objetivo_anterior=anterior, objetivo_nuevo=nuevo,
			semaforo_anterior=semaforo_anterior, semaforo_nuevo=meta.semaforo(hoy),
		))
	return ajustes


@transaction.atomic
def registrar_ausencia(ausencia, usuario, hoy=None):
	"""Guarda la ausencia y ajusta las metas del funcionario en el período.

	`ausencia` es una instancia sin guardar con funcionario, periodo, fechas y motivo.
	"""
	hoy = hoy or timezone.localdate()
	# Bloquea al funcionario: dos ausencias simultáneas no pueden calcular el ajuste sobre la misma base.
	funcionario = Funcionario.objects.select_for_update().get(pk=ausencia.funcionario_id)
	ausencia.funcionario = funcionario
	_validar(ausencia)
	periodo = ausencia.periodo
	metas = _metas_del_funcionario(funcionario, periodo)
	if not metas:
		raise ValidationError("El funcionario no tiene metas en este período; no hay nada que ajustar.")
	disponibles_antes = periodo.dias_totales - _dias_ausente(funcionario, periodo)
	disponibles_despues = disponibles_antes - ausencia.dias
	if disponibles_despues <= 0:
		raise ValidationError("La ausencia cubre todos los días disponibles del período.")
	ausencia.registrada_por = usuario
	ausencia.estado = "vigente"
	ausencia.full_clean()
	ausencia.save()
	ajustes = _aplicar_factor(ausencia, metas, disponibles_antes, disponibles_despues, hoy)
	AjusteMeta.objects.bulk_create(ajustes)
	Auditoria.objects.create(
		usuario=usuario, accion="registrar_ausencia", entidad="Ausencia", identificador=str(ausencia.pk),
		valor_anterior={str(a.meta_id): str(a.objetivo_anterior) for a in ajustes},
		valor_nuevo={"dias": ausencia.dias, "metas": {str(a.meta_id): str(a.objetivo_nuevo) for a in ajustes}},
	)
	return ausencia


@transaction.atomic
def anular_ausencia(ausencia, usuario, hoy=None):
	"""Deja la ausencia sin efecto y devuelve las metas a la proporción sin esos días."""
	hoy = hoy or timezone.localdate()
	ausencia = Ausencia.objects.select_for_update().select_related("periodo", "funcionario").get(pk=ausencia.pk)
	if ausencia.estado != "vigente":
		raise ValidationError("La ausencia ya estaba anulada.")
	if ausencia.periodo.estado != "abierto":
		raise ValidationError("El período está cerrado; la ausencia no se puede anular.")
	periodo = ausencia.periodo
	disponibles_con = periodo.dias_totales - _dias_ausente(ausencia.funcionario, periodo)
	disponibles_sin = disponibles_con + ausencia.dias
	metas = [(meta, False) for meta in Meta.objects.select_for_update().filter(pk__in=ausencia.ajustes.values("meta_id"))]
	ajustes = _aplicar_factor(ausencia, metas, disponibles_con, disponibles_sin, hoy)
	ausencia.estado = "anulada"
	ausencia.anulada_por = usuario
	ausencia.anulada_en = timezone.now()
	ausencia.save(update_fields=["estado", "anulada_por", "anulada_en"])
	Auditoria.objects.create(
		usuario=usuario, accion="anular_ausencia", entidad="Ausencia", identificador=str(ausencia.pk),
		valor_nuevo={str(a.meta_id): str(a.objetivo_nuevo) for a in ajustes},
	)
	return ausencia
