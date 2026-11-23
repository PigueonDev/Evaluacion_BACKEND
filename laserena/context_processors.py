from django.conf import settings

from laserena.permisos import contexto_perfil


def administracion(request):
    return {"phpmyadmin_url": settings.PHPMYADMIN_URL, **contexto_perfil(request)}
