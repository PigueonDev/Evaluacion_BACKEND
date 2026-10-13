from django.conf import settings

from laserena.permisos import rol_usuario


def administracion(request):
    return {
        "phpmyadmin_url": settings.PHPMYADMIN_URL,
        "rol_sgr": rol_usuario(getattr(request, "user", None)),
    }
