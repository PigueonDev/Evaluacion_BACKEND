"""Lectura segura de los filtros que llegan por GET en listados y búsquedas."""

LARGO_MAXIMO_BUSQUEDA = 100


def parametro_permitido(request, nombre, permitidos):
    """Devuelve el valor del parámetro GET solo si está en la lista blanca."""
    valor = request.GET.get(nombre, "").strip()
    return valor if valor in permitidos else ""


def texto_busqueda(request, nombre="q"):
    return request.GET.get(nombre, "").strip()[:LARGO_MAXIMO_BUSQUEDA]
