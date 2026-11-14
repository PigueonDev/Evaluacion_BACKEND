"""Cumplimiento por colaborador, como las hojas por cargo, SEMAFORO y RESUMEN de la matriz SGR.

Cumplimiento total = Σ (ponderador × cumplimiento del ítem)
                     + felicitaciones (hasta el máximo del período) − reclamos,
acotado entre 0 % y el tope del colaborador (150 %).
"""

from django.db.models import Max
from django.utils import timezone

from .models import Actividad, Meta


def metas_vigentes(funcionario, periodo):
	"""Metas personales del período más las del cargo para los ítems sin meta personal."""
	personales = list(Meta.objects.filter(periodo=periodo, funcionario=funcionario).select_related("item", "periodo"))
	cubiertos = {meta.item_id for meta in personales}
	del_cargo = Meta.objects.filter(periodo=periodo, cargo=funcionario.cargo_id, funcionario__isnull=True).exclude(item_id__in=cubiertos).select_related("item", "periodo")
	metas = personales + [_meta_personal(meta, funcionario) for meta in del_cargo]
	return sorted(metas, key=lambda meta: (-float(meta.ponderador), meta.item.nombre))


def _meta_personal(meta_cargo, funcionario):
	"""Copia en memoria de la meta del cargo, medida solo sobre el funcionario."""
	return Meta(
		pk=meta_cargo.pk, periodo=meta_cargo.periodo, item=meta_cargo.item, funcionario=funcionario,
		objetivo=meta_cargo.objetivo, ponderador=meta_cargo.ponderador, version=meta_cargo.version,
	)


def _contar_reconocimientos(funcionario, periodo):
	from oficina.models import Reconocimiento

	vigentes = Reconocimiento.objects.filter(funcionario=funcionario, periodo=periodo, estado="vigente")
	return vigentes.filter(tipo="felicitacion").count(), vigentes.filter(tipo="reclamo").count()


def alerta_rrhh(funcionario, periodo):
	"""Reclamos en este período y en el anterior: la matriz pide informar a RRHH."""
	from oficina.models import Reconocimiento

	anterior = periodo.anterior()
	if anterior is None:
		return False
	reclamos = Reconocimiento.objects.filter(funcionario=funcionario, tipo="reclamo", estado="vigente")
	return reclamos.filter(periodo=periodo).exists() and reclamos.filter(periodo=anterior).exists()


def resumen_funcionario(funcionario, periodo, hoy=None):
	hoy = hoy or timezone.localdate()
	filas = []
	for meta in metas_vigentes(funcionario, periodo):
		cumplimiento = meta.cumplimiento
		filas.append({
			"meta": meta,
			"avance": meta.avance_aprobado,
			"cumplimiento": cumplimiento,
			"ponderado": float(meta.ponderador) * cumplimiento / 100,
			"semaforo": meta.semaforo(hoy),
		})
	gestion = sum(fila["ponderado"] for fila in filas)
	felicitaciones, reclamos = _contar_reconocimientos(funcionario, periodo)
	bono = min(felicitaciones, periodo.maximo_felicitaciones) * float(periodo.bono_felicitacion)
	descuento = reclamos * float(periodo.descuento_reclamo)
	total = max(0.0, min(gestion + bono - descuento, float(periodo.tope_cumplimiento)))
	ingresos = Actividad.objects.filter(funcionario=funcionario, periodo=periodo).exclude(estado="anulada")
	ultimo = ingresos.aggregate(ultimo=Max("fecha"))["ultimo"]
	transcurridos = periodo.dias_transcurridos(hoy)
	cantidad = ingresos.count()
	return {
		"funcionario": funcionario,
		"filas": filas,
		"suma_ponderadores": sum(float(fila["meta"].ponderador) for fila in filas),
		"gestion": gestion,
		"felicitaciones": felicitaciones,
		"reclamos": reclamos,
		"bono": bono,
		"descuento": descuento,
		"total": total,
		"esperado": periodo.avance_esperado(hoy),
		"semaforo": periodo.semaforo(total, hoy) if filas else "sin_metas",
		"cumple_minimo": total >= float(periodo.umbral_colectivo),
		"ultimo_ingreso": ultimo,
		"dias_sin_ingreso": (hoy - ultimo).days if ultimo else None,
		"ingresos": cantidad,
		"ingresos_diarios": cantidad / transcurridos if transcurridos else 0,
		"alerta_rrhh": alerta_rrhh(funcionario, periodo),
	}


def resumen_equipo(funcionarios, periodo, hoy=None):
	"""Filas del RESUMEN ordenadas por cumplimiento, con ranking y promedio del equipo."""
	filas = [resumen_funcionario(funcionario, periodo, hoy) for funcionario in funcionarios]
	filas.sort(key=lambda fila: (-fila["total"], fila["funcionario"].nombre_completo))
	for posicion, fila in enumerate(filas, start=1):
		fila["ranking"] = posicion
	con_metas = [fila for fila in filas if fila["filas"]]
	promedio = sum(fila["total"] for fila in con_metas) / len(con_metas) if con_metas else 0
	return {
		"filas": filas,
		"promedio": promedio,
		"semaforo_promedio": periodo.semaforo(promedio, hoy) if con_metas else "sin_metas",
		"cumple_colectivo": promedio >= float(periodo.umbral_colectivo),
		"ingresos": sum(fila["ingresos"] for fila in filas),
	}
