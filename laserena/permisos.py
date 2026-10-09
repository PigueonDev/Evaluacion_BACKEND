from django.contrib.auth.decorators import user_passes_test

LARGO_MAXIMO_BUSQUEDA = 100


def es_staff(user):
    return user.is_active and user.is_staff


solo_personal = user_passes_test(es_staff)


def parametro_permitido(request, nombre, permitidos):
    """Devuelve el valor del parámetro GET solo si está en la lista blanca."""
    valor = request.GET.get(nombre, "").strip()
    return valor if valor in permitidos else ""


def texto_busqueda(request, nombre="q"):
    return request.GET.get(nombre, "").strip()[:LARGO_MAXIMO_BUSQUEDA]
