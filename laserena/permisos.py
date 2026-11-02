"""Perfiles del SGR basados en los Grupos de Django.

Administrador (coordinación), Supervisor (delegado) y Administrativo (funcionario).
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

LARGO_MAXIMO_BUSQUEDA = 100
GRUPO_ADMINISTRADOR = "Administrador"
GRUPO_SUPERVISOR = "Supervisor"
GRUPO_ADMINISTRATIVO = "Administrativo"
GRUPOS_SGR = (GRUPO_ADMINISTRADOR, GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO)
GRUPOS_OPERATIVOS = (GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO)


def grupo_usuario(user):
    """Grupo SGR del usuario. Si tuviera varios, manda el de mayor nivel."""
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    if user.is_superuser:
        return GRUPO_ADMINISTRADOR
    if not hasattr(user, "_grupo_sgr"):
        nombres = set(user.groups.values_list("name", flat=True))
        user._grupo_sgr = next((grupo for grupo in GRUPOS_SGR if grupo in nombres), None)
    return user._grupo_sgr


def es_personal(user):
    return grupo_usuario(user) is not None


def es_administracion(user):
    return grupo_usuario(user) == GRUPO_ADMINISTRADOR


def permite_grupo(user, grupos):
    grupo = grupo_usuario(user)
    if grupo is None:
        return False
    return grupo == GRUPO_ADMINISTRADOR or grupo in grupos


def solo_grupos(*grupos):
    """Exige sesión y uno de los grupos indicados. El Administrador siempre pasa."""

    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not es_personal(request.user):
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
            if not permite_grupo(request.user, grupos):
                return render(request, "institucional/denegado.html", status=403)
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


def con_permiso(codigo):
    """Exige sesión y un permiso de Django concedido por el grupo."""

    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not es_personal(request.user):
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
            if not request.user.has_perm(codigo):
                return render(request, "institucional/denegado.html", status=403)
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


solo_personal = solo_grupos(*GRUPOS_OPERATIVOS)
solo_funcionario = solo_grupos(GRUPO_ADMINISTRATIVO)
solo_delegado = solo_grupos(GRUPO_SUPERVISOR)
solo_consulta = solo_grupos(GRUPO_SUPERVISOR)
solo_funcionario_o_delegado = solo_grupos(GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR)
solo_administracion = solo_grupos()


class RolMiddleware:
    """Impide que un perfil operativo entre a la administración del sistema."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        grupo = grupo_usuario(getattr(request, "user", None))
        if grupo in GRUPOS_OPERATIVOS and request.path.startswith("/administracion"):
            return render(request, "institucional/denegado.html", status=403)
        return self.get_response(request)


def parametro_permitido(request, nombre, permitidos):
    """Devuelve el valor del parámetro GET solo si está en la lista blanca."""
    valor = request.GET.get(nombre, "").strip()
    return valor if valor in permitidos else ""


def texto_busqueda(request, nombre="q"):
    return request.GET.get(nombre, "").strip()[:LARGO_MAXIMO_BUSQUEDA]


def perfil_funcionario(user):
    """Perfil SGR del usuario, si tiene funcionario asociado."""
    if not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "perfil_sgr", None)


def acotar_ambito(queryset, user, campo):
    """Limita la consulta a la delegación del funcionario. El Administrador ve todo el municipio."""
    perfil = perfil_de_ambito(user)
    if perfil is None:
        return queryset
    return queryset.filter(**{campo: perfil.delegacion_id})


def perfil_de_ambito(user):
    """Perfil que restringe la delegación. El Administrador no acota el municipio."""
    perfil = perfil_funcionario(user)
    if perfil is None or es_administracion(user):
        return None
    return perfil
