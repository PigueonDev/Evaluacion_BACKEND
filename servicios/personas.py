"""Vecinos ya registrados: se recuerdan al guardar y se ofrecen al escribir."""

from django.core.exceptions import ValidationError
from django.db.models import Q

from institucional.models import Vecino
from laserena.rut import normalizar_rut


def recordar_persona(delegacion, nombre, rut="", telefono=""):
	"""Crea o actualiza el vecino de la delegación para poder autocompletarlo después."""
	nombre = (nombre or "").strip()
	if delegacion is None or not nombre:
		return None
	rut_limpio = ""
	if rut:
		try:
			rut_limpio = normalizar_rut(rut)
		except ValidationError:
			rut_limpio = ""
	telefono = (telefono or "").strip()
	if rut_limpio:
		vecino = Vecino.objects.filter(delegacion=delegacion, rut=rut_limpio).first()
	else:
		vecino = Vecino.objects.filter(delegacion=delegacion, nombre__iexact=nombre).first()
	if vecino is None:
		return Vecino.objects.create(delegacion=delegacion, nombre=nombre, rut=rut_limpio, telefono=telefono)
	cambios = []
	if telefono and vecino.telefono != telefono:
		vecino.telefono = telefono
		cambios.append("telefono")
	if rut_limpio and vecino.nombre != nombre:
		vecino.nombre = nombre
		cambios.append("nombre")
	if cambios:
		vecino.save(update_fields=cambios)
	return vecino


def buscar_personas(user, texto, ambito):
	"""Coincidencias por nombre, RUT o teléfono dentro de la delegación del usuario."""
	texto = (texto or "").strip()
	if len(texto) < 2:
		return []
	compacto = "".join(caracter for caracter in texto.upper() if caracter.isalnum())
	vecinos = ambito(Vecino.objects.filter(activo=True), user, "delegacion").filter(
		Q(nombre__icontains=texto) | Q(rut__icontains=texto) | Q(rut__icontains=compacto) | Q(telefono__icontains=texto)
	).order_by("nombre")[:8]
	return [{"nombre": vecino.nombre, "rut": vecino.rut, "telefono": vecino.telefono} for vecino in vecinos]
