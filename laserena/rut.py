"""RUT chileno: normalización y dígito verificador (módulo 11)."""

import re

from django.core.exceptions import ValidationError

FORMATO_RUT = re.compile(r"^(\d{1,8})-?([\dK])$")


def digito_verificador(cuerpo):
	suma, factor = 0, 2
	for digito in reversed(str(cuerpo)):
		suma += int(digito) * factor
		factor = 2 if factor == 7 else factor + 1
	resto = 11 - suma % 11
	return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar_rut(valor):
	"""Devuelve el RUT como 12345678-5 o lanza ValidationError si no es válido."""
	texto = re.sub(r"[.\s]", "", str(valor or "")).upper()
	coincidencia = FORMATO_RUT.match(texto)
	if not coincidencia:
		raise ValidationError("Ingresa el RUT con dígito verificador, por ejemplo 12.345.678-5.")
	cuerpo, dv = coincidencia.groups()
	cuerpo = cuerpo.lstrip("0") or "0"
	if int(cuerpo) < 1_000_000:
		raise ValidationError("El RUT es demasiado corto.")
	if digito_verificador(cuerpo) != dv:
		raise ValidationError("El dígito verificador del RUT no es válido.")
	return f"{cuerpo}-{dv}"


def formatear_rut(rut):
	cuerpo, dv = rut.split("-")
	return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
