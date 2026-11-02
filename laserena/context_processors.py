from django.conf import settings

from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, grupo_usuario


def administracion(request):
    grupo = grupo_usuario(getattr(request, "user", None))
    return {
        "phpmyadmin_url": settings.PHPMYADMIN_URL,
        "grupo_sgr": grupo,
        "es_personal": grupo is not None,
        "es_administracion": grupo == GRUPO_ADMINISTRADOR,
        "es_supervisor": grupo == GRUPO_SUPERVISOR,
        "es_administrativo": grupo == GRUPO_ADMINISTRATIVO,
    }
