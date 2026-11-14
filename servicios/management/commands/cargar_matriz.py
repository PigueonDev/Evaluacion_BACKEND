from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from institucional.models import Cargo, UnidadMunicipal
from servicios.matriz import CARGOS, ITEMS, METAS_POR_CARGO, UNIDADES, trimestre_de
from servicios.models import ItemMedicion, Meta, Periodo


class Command(BaseCommand):
	help = "Carga los cargos, ítems, unidades municipales y metas trimestrales de la matriz SGR. Se puede repetir sin duplicar."

	def add_arguments(self, parser):
		parser.add_argument("--fecha", help="Fecha (AAAA-MM-DD) dentro del trimestre a cargar. Por defecto, hoy.")
		parser.add_argument("--actualizar-metas", action="store_true", help="Sobrescribe objetivo y ponderador de las metas de cargo ya creadas.")

	@transaction.atomic
	def handle(self, *args, **options):
		try:
			fecha = date.fromisoformat(options["fecha"]) if options.get("fecha") else timezone.localdate()
		except ValueError as error:
			raise CommandError("La fecha debe tener el formato AAAA-MM-DD.") from error
		resultado = cargar_matriz(fecha, actualizar_metas=options["actualizar_metas"])
		self.stdout.write(self.style.SUCCESS(
			f"Matriz SGR cargada en «{resultado['periodo']}»: {resultado['cargos']} cargos, {resultado['items']} ítems, "
			f"{resultado['unidades']} unidades, {resultado['metas_nuevas']} metas nuevas y {resultado['metas_actualizadas']} actualizadas."
		))


def cargar_matriz(fecha=None, actualizar_metas=False):
	fecha = fecha or timezone.localdate()
	for nombre, sigla, tipo, descripcion in UNIDADES:
		UnidadMunicipal.objects.update_or_create(nombre=nombre, defaults={"sigla": sigla, "tipo": tipo, "descripcion": descripcion})
	items = {}
	for codigo, nombre, tipo in ITEMS:
		items[codigo], _ = ItemMedicion.objects.update_or_create(
			codigo=codigo, defaults={"nombre": nombre, "tipo_medicion": tipo, "unidad": "porcentaje" if tipo == "tasa_tubo" else "cantidad", "activo": True},
		)
	cargos = {}
	for nombre, sigla, perfil, descripcion in CARGOS:
		cargos[nombre], _ = Cargo.objects.update_or_create(nombre=nombre, defaults={"sigla": sigla, "perfil": perfil, "descripcion": descripcion, "activo": True})
	nombre_periodo, inicio, termino = trimestre_de(fecha)
	periodo, _ = Periodo.objects.get_or_create(nombre=nombre_periodo, defaults={"fecha_inicio": inicio, "fecha_termino": termino, "estado": "abierto"})
	nuevas = actualizadas = 0
	for nombre_cargo, metas in METAS_POR_CARGO.items():
		cargo = cargos[nombre_cargo]
		cargo.funciones.add(items["OTG"], *(items[codigo] for codigo, _, _ in metas))
		for codigo, ponderador, objetivo in metas:
			meta, creada = Meta.objects.get_or_create(
				periodo=periodo, item=items[codigo], cargo=cargo, funcionario=None,
				defaults={"objetivo": objetivo, "ponderador": ponderador},
			)
			if creada:
				nuevas += 1
			elif actualizar_metas and (meta.objetivo != objetivo or meta.ponderador != ponderador):
				meta.objetivo, meta.ponderador = objetivo, ponderador
				meta.version += 1
				meta.save(update_fields=["objetivo", "ponderador", "version"])
				actualizadas += 1
	return {
		"periodo": periodo, "cargos": len(cargos), "items": len(items), "unidades": len(UNIDADES),
		"metas_nuevas": nuevas, "metas_actualizadas": actualizadas,
	}
