"""Grupos del SGR y sus permisos. Se sincronizan después de cada migrate."""

from django.contrib.auth.models import Group, Permission
from django.db.models import Q

from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR

APPS_ADMINISTRADOR = ("institucional", "servicios", "oficina", "organizaciones")
MODELOS_AUTH_ADMINISTRADOR = ("user", "group")

PERMISOS_SUPERVISOR = (
    "organizaciones.view_organizacioncomunitaria",
    "organizaciones.add_organizacioncomunitaria",
    "organizaciones.change_organizacioncomunitaria",
    "organizaciones.verificar_organizacion",
    "servicios.view_actividad",
    "servicios.aprobar_actividad",
    "servicios.view_tareapreparatoria",
    "servicios.view_compromiso",
    "servicios.view_meta",
    "institucional.view_funcionario",
    "oficina.view_carta",
    "oficina.add_carta",
    "oficina.change_carta",
    "oficina.delete_carta",
    "oficina.view_beneficionino",
    "oficina.add_beneficionino",
    "oficina.change_beneficionino",
    "oficina.delete_beneficionino",
    "oficina.view_ausencia",
    "oficina.add_ausencia",
    "oficina.anular_ausencia",
    "oficina.view_ajustemeta",
)

PERMISOS_ADMINISTRATIVO = (
    "organizaciones.view_organizacioncomunitaria",
    "servicios.view_actividad",
    "servicios.add_actividad",
    "servicios.change_actividad",
    "servicios.view_tareapreparatoria",
    "servicios.add_tareapreparatoria",
    "servicios.change_tareapreparatoria",
    "servicios.view_caso",
    "servicios.add_caso",
    "servicios.change_caso",
    "servicios.add_gestion",
    "servicios.change_gestion",
    "servicios.view_compromiso",
    "servicios.add_compromiso",
    "servicios.change_compromiso",
    "oficina.view_carta",
    "oficina.change_carta",
    "oficina.view_beneficionino",
    "oficina.add_beneficionino",
    "oficina.change_beneficionino",
    "oficina.view_ausencia",
)


def _permisos(codigos):
    filtro = Q(pk__in=[])
    for codigo in codigos:
        app_label, codename = codigo.split(".")
        filtro |= Q(content_type__app_label=app_label, codename=codename)
    return Permission.objects.filter(filtro)


def permisos_administrador():
    return Permission.objects.filter(
        Q(content_type__app_label__in=APPS_ADMINISTRADOR)
        | Q(content_type__app_label="auth", content_type__model__in=MODELOS_AUTH_ADMINISTRADOR)
    )


def asegurar_grupos():
    """Crea los tres grupos del SGR y les asigna su conjunto de permisos."""
    definicion = {
        GRUPO_ADMINISTRADOR: permisos_administrador(),
        GRUPO_SUPERVISOR: _permisos(PERMISOS_SUPERVISOR),
        GRUPO_ADMINISTRATIVO: _permisos(PERMISOS_ADMINISTRATIVO),
    }
    grupos = {}
    for nombre, permisos in definicion.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.set(permisos)
        grupos[nombre] = grupo
    return grupos


def asignar_grupo(usuario, nombre_grupo):
    """Deja al usuario en un único grupo SGR, conservando otros grupos ajenos al SGR."""
    from laserena.permisos import GRUPOS_SGR

    grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
    usuario.groups.remove(*Group.objects.filter(name__in=GRUPOS_SGR).exclude(pk=grupo.pk))
    usuario.groups.add(grupo)
    if hasattr(usuario, "_grupo_sgr"):
        del usuario._grupo_sgr
    return usuario


def sincronizar_grupos(sender, **kwargs):
    # organizaciones es la última app instalada: para entonces ya existen todos los permisos.
    if sender.name == "organizaciones":
        asegurar_grupos()
