"""Cuentas del SGR: el rol Administrador administra los parámetros."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from servicios.models import ItemMedicion, Meta, Periodo, Servicio

from .models import Autoridad, Cargo, Delegacion, Funcionario, Municipio

MODELOS_PARAMETRO = (
    Delegacion,
    Cargo,
    Funcionario,
    Autoridad,
    Municipio,
    Servicio,
    ItemMedicion,
    Periodo,
    Meta,
)


def conceder_permisos_parametros(usuario):
    """Permite ver y mantener delegaciones, cargos, catálogos, ítems, períodos, metas y ponderaciones."""
    tipos = ContentType.objects.get_for_models(*MODELOS_PARAMETRO)
    permisos = Permission.objects.filter(content_type__in=list(tipos.values()))
    usuario.user_permissions.add(*permisos)
    return usuario
