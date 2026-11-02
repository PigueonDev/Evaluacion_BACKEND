from datetime import date, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organizaciones.models import OrganizacionComunitaria, normalizar_territorio

PALABRAS_JJVV = ("JUNTA DE VECINO", "JUNTA VECINAL", "JJVV", "J.V.", "JJ.VV")


def _fecha(valor):
	if isinstance(valor, datetime):
		return valor.date()
	if isinstance(valor, date):
		return valor
	return None


def _entero(valor):
	if isinstance(valor, bool) or valor is None:
		return None
	if isinstance(valor, (int, float)):
		return int(valor) if valor >= 0 else None
	texto = str(valor).strip()
	return int(texto) if texto.isdigit() else None


def _texto(valor, largo):
	return " ".join(str(valor or "").split())[:largo]


def tipo_por_nombre(nombre):
	nombre = nombre.upper()
	return "junta_vecinos" if any(palabra in nombre for palabra in PALABRAS_JJVV) else "funcional"


class Command(BaseCommand):
	help = "Importa la base JJVV (Excel) como organizaciones comunitarias en estado «sin verificar»."

	def add_arguments(self, parser):
		parser.add_argument("archivo", help="Ruta del archivo base-datos-jjvv-sin-verificar.xlsx")

	def handle(self, archivo, **options):
		try:
			import openpyxl
		except ImportError as error:
			raise CommandError("Instala openpyxl: pip install -r requirements.txt") from error
		ruta = Path(archivo)
		if not ruta.is_file():
			raise CommandError(f"No existe el archivo {ruta}")
		libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
		hoja = libro.worksheets[0]
		creadas = actualizadas = omitidas = 0
		sin_domicilio = sin_territorio = socios_invalidos = 0
		nombres = {}
		with transaction.atomic():
			for numero, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
				fila = list(fila) + [None] * (8 - len(fila))
				nombre = _texto(fila[0], 200)
				if not nombre:
					omitidas += 1
					continue
				nombres[nombre.upper()] = nombres.get(nombre.upper(), 0) + 1
				domicilio = _texto(fila[1], 250)
				territorio = normalizar_territorio(fila[2])
				socios = _entero(fila[3])
				sin_domicilio += not domicilio
				sin_territorio += territorio == "SIN TERRITORIO"
				socios_invalidos += fila[3] is not None and socios is None
				datos = {
					"nombre": nombre,
					"tipo": tipo_por_nombre(nombre),
					"domicilio": domicilio,
					"territorio": territorio,
					"socios_activos": socios,
					"fecha_constitucion": _fecha(fila[4]),
					"numero_registro_pj": _entero(fila[5]),
					"fecha_inscripcion": _fecha(fila[6]),
					"registro_directiva": _entero(fila[7]),
				}
				_, creada = OrganizacionComunitaria.objects.update_or_create(
					archivo_origen=ruta.name[:120], fila_origen=numero, defaults=datos
				)
				if creada:
					creadas += 1
				else:
					actualizadas += 1
		duplicados = sum(1 for total in nombres.values() if total > 1)
		self.stdout.write(self.style.SUCCESS(
			f"Importación lista: {creadas} creadas, {actualizadas} actualizadas, {omitidas} filas vacías omitidas."
		))
		self.stdout.write(
			f"Calidad de datos: {sin_domicilio} sin domicilio, {sin_territorio} sin territorio, "
			f"{socios_invalidos} con socios no numéricos, {duplicados} nombres duplicados."
		)
