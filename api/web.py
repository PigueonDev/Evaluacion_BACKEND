"""Exportaciones desde la aplicación web (sesión de Django), con los mismos filtros y columnas que la API."""

from laserena.permisos import con_permiso, es_administracion, solo_funcionario

from .exportar import exportar
from .views import actividades_para_exportar, cartas_para_exportar


@con_permiso("oficina.view_carta")
def exportar_cartas(request, formato):
    return exportar("cartas", formato, cartas_para_exportar(request), request.user, es_administracion(request.user))


@solo_funcionario
def exportar_actividades(request, formato):
    return exportar("actividades", formato, actividades_para_exportar(request), request.user, es_administracion(request.user))
