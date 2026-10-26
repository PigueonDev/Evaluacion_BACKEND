from django.conf import settings

from laserena.permisos import es_administracion, rol_usuario


def administracion(request):
    usuario = getattr(request, "user", None)
    return {
        "phpmyadmin_url": settings.PHPMYADMIN_URL,
        "rol_sgr": rol_usuario(usuario),
        "es_administracion": es_administracion(usuario),
    }
