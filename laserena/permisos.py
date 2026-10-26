from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

LARGO_MAXIMO_BUSQUEDA = 100
ROL_ADMINISTRADOR = "administrador"
ROLES_OPERATIVOS = ("funcionario", "delegado", "consulta")


def es_staff(user):
    return user.is_active and user.is_staff


def solo_personal(view):
    """Personal municipal. Un perfil con rol usa las pantallas de ese rol."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
        if not es_staff(request.user):
            return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
        return view(request, *args, **kwargs)

    return _wrapped


def rol_usuario(user):
    """Rol del perfil SGR. El personal sin perfil queda como administración sin rol nombrado."""
    perfil = perfil_funcionario(user)
    if perfil is None:
        return None
    return perfil.rol


def es_administracion(user):
    """Personal sin rol operativo: sin perfil, o con el rol Administrador."""
    if not getattr(user, "is_authenticated", False) or not es_staff(user):
        return False
    rol = rol_usuario(user)
    return rol is None or rol == ROL_ADMINISTRADOR


def permite_rol(user, roles):
    if not es_staff(user):
        return False
    if es_administracion(user):
        return True
    return rol_usuario(user) in roles


def solo_roles(*roles):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not getattr(request.user, "is_authenticated", False) or not es_staff(request.user):
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
            if not permite_rol(request.user, roles):
                return render(request, "institucional/denegado.html", status=403)
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


solo_funcionario = solo_roles("funcionario")
solo_delegado = solo_roles("delegado")
solo_consulta = solo_roles("consulta")
solo_funcionario_o_delegado = solo_roles("funcionario", "delegado")
solo_administracion = solo_roles()


class RolMiddleware:
    """Impide que un rol operativo entre a la administración del sistema."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rol = rol_usuario(getattr(request, "user", None))
        path = request.path
        if rol in ROLES_OPERATIVOS and (path.startswith("/admin") or path.startswith("/administracion")):
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
    """Limita la consulta a la delegación del funcionario.

    La administración (sin perfil o con rol administrador) mantiene el ámbito municipal completo.
    """
    perfil = perfil_de_ambito(user)
    if perfil is None:
        return queryset
    return queryset.filter(**{campo: perfil.delegacion_id})


def perfil_de_ambito(user):
    """Perfil que restringe la delegación. Administración no acota el municipio."""
    perfil = perfil_funcionario(user)
    if perfil is None or perfil.rol == ROL_ADMINISTRADOR:
        return None
    return perfil
