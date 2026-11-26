"""Permisos del SGR: un solo módulo para la web, la API y la administración de grupos.

Orden del módulo:
1. Perfiles (Grupos de Django): Administrador, Supervisor y Administrativo.
2. Matriz de permisos por perfil y por acción (ver, agregar, modificar, eliminar y acciones propias).
3. Reglas de perfil: a qué perfil pertenece una cuenta.
4. Decoradores y middleware de las vistas web.
5. Ámbito: qué delegación ve cada perfil.
6. Permisos de la API (Django REST Framework y SimpleJWT).
7. Sincronización de grupos y nombres de permisos en español (después de cada migrate).
"""

import unicodedata
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.shortcuts import render
from rest_framework.permissions import SAFE_METHODS, BasePermission

# --- 1. Perfiles ---------------------------------------------------------------------------

GRUPO_ADMINISTRADOR = "Administrador"
GRUPO_SUPERVISOR = "Supervisor"
GRUPO_ADMINISTRATIVO = "Administrativo"
GRUPOS_SGR = (GRUPO_ADMINISTRADOR, GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO)
GRUPOS_OPERATIVOS = (GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO)

DESCRIPCION_PERFILES = {
    GRUPO_ADMINISTRADOR: "Coordinación: administra usuarios, grupos y mantenedores, y ve todo el municipio.",
    GRUPO_SUPERVISOR: "Delegado: aprueba actividades, verifica organizaciones y lleva la Oficina de Partes de su delegación.",
    GRUPO_ADMINISTRATIVO: "Funcionario: registra sus actividades, tareas, casos y compromisos en su delegación.",
}

# --- 2. Matriz de permisos -----------------------------------------------------------------

VER = "ver"
AGREGAR = "agregar"
MODIFICAR = "modificar"
ELIMINAR = "eliminar"
APROBAR = "aprobar"
VERIFICAR = "verificar"
ANULAR = "anular"
ACCIONES = (VER, AGREGAR, MODIFICAR, ELIMINAR, APROBAR, VERIFICAR, ANULAR)
ACCION_DJANGO = {VER: "view", AGREGAR: "add", MODIFICAR: "change", ELIMINAR: "delete"}
ACCION_POR_CODIGO = {codigo: accion for accion, codigo in ACCION_DJANGO.items()}

# Acciones propias del SGR: se declaran en `Meta.permissions` de cada modelo.
PERMISOS_ESPECIALES = {
    ("servicios.actividad", APROBAR): "servicios.aprobar_actividad",
    ("organizaciones.organizacioncomunitaria", VERIFICAR): "organizaciones.verificar_organizacion",
    ("oficina.ausencia", ANULAR): "oficina.anular_ausencia",
}
ACCION_ESPECIAL = {codigo.split(".")[1]: accion for (_, accion), codigo in PERMISOS_ESPECIALES.items()}

# El Administrador recibe todos los permisos de estas aplicaciones, más las cuentas y los grupos.
APPS_ADMINISTRADOR = ("institucional", "servicios", "oficina", "organizaciones")
MODELOS_AUTH_ADMINISTRADOR = ("user", "group")

PERMISOS_POR_PERFIL = {
    GRUPO_SUPERVISOR: {
        "institucional.funcionario": (VER,),
        "institucional.cargo": (VER,),
        "institucional.unidadmunicipal": (VER,),
        "servicios.actividad": (VER, APROBAR),
        "servicios.tareapreparatoria": (VER,),
        "servicios.compromiso": (VER,),
        "servicios.meta": (VER,),
        "oficina.carta": (VER, AGREGAR, MODIFICAR, ELIMINAR),
        "oficina.beneficionino": (VER, AGREGAR, MODIFICAR, ELIMINAR),
        "oficina.ausencia": (VER, AGREGAR, ANULAR),
        "oficina.ajustemeta": (VER,),
        "oficina.reconocimiento": (VER, AGREGAR, MODIFICAR),
        "organizaciones.organizacioncomunitaria": (VER, AGREGAR, MODIFICAR, VERIFICAR),
    },
    GRUPO_ADMINISTRATIVO: {
        "servicios.actividad": (VER, AGREGAR, MODIFICAR),
        "servicios.tareapreparatoria": (VER, AGREGAR, MODIFICAR),
        "servicios.caso": (VER, AGREGAR, MODIFICAR),
        "servicios.gestion": (AGREGAR, MODIFICAR),
        "servicios.compromiso": (VER, AGREGAR, MODIFICAR),
        "oficina.carta": (VER, MODIFICAR),
        "oficina.beneficionino": (VER, AGREGAR, MODIFICAR),
        "oficina.ausencia": (VER,),
        "oficina.reconocimiento": (VER,),
        "organizaciones.organizacioncomunitaria": (VER,),
    },
}


def codigo_permiso(recurso, accion):
    """`("oficina.carta", "ver")` → `"oficina.view_carta"`."""
    if (recurso, accion) in PERMISOS_ESPECIALES:
        return PERMISOS_ESPECIALES[(recurso, accion)]
    app_label, modelo = recurso.split(".")
    return f"{app_label}.{ACCION_DJANGO[accion]}_{modelo}"


def codigos_del_perfil(grupo):
    """Códigos `app.codename` que concede el perfil operativo, en el orden de la matriz."""
    return [codigo_permiso(recurso, accion) for recurso, acciones in PERMISOS_POR_PERFIL.get(grupo, {}).items() for accion in acciones]


def accion_del_permiso(codename, modelo):
    """Acción en español de un permiso de Django (`view_carta` → `ver`)."""
    if codename in ACCION_ESPECIAL:
        return ACCION_ESPECIAL[codename]
    prefijo, _, resto = codename.partition("_")
    return ACCION_POR_CODIGO.get(prefijo) if resto == modelo else None


def nombre_recurso(tipo):
    """Nombre plural del modelo de un ContentType, con mayúscula inicial («Cartas de Oficina de Partes»)."""
    modelo = tipo.model_class()
    texto = str(modelo._meta.verbose_name_plural) if modelo else tipo.model
    return texto[:1].upper() + texto[1:]


def orden_alfabetico(texto):
    """Clave de orden que ignora tildes («Ítems» va junto a la «I»)."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def nombre_permiso(accion, verbose_name):
    return f"Puede {accion} {verbose_name}"


# --- 3. Reglas de perfil -------------------------------------------------------------------


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


def es_administrador(user):
    return grupo_usuario(user) == GRUPO_ADMINISTRADOR


def es_supervisor(user):
    return grupo_usuario(user) == GRUPO_SUPERVISOR


def es_administrativo(user):
    return grupo_usuario(user) == GRUPO_ADMINISTRATIVO


def permite_grupo(user, grupos):
    """El Administrador siempre pasa; los demás, solo si su perfil está en `grupos`."""
    grupo = grupo_usuario(user)
    if grupo is None:
        return False
    return grupo == GRUPO_ADMINISTRADOR or grupo in grupos


# --- 4. Decoradores y middleware de la web -------------------------------------------------


def _denegado(request):
    return render(request, "institucional/denegado.html", status=403)


def solo_perfiles(*grupos):
    """Exige sesión y uno de los perfiles indicados. El Administrador siempre pasa."""

    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not es_personal(request.user):
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
            if not permite_grupo(request.user, grupos):
                return _denegado(request)
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


def con_permiso(codigo):
    """Exige sesión y un permiso de Django concedido por el grupo (`app.codename`)."""

    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not es_personal(request.user):
                return redirect_to_login(request.get_full_path(), login_url=settings.LOGIN_URL)
            if not request.user.has_perm(codigo):
                return _denegado(request)
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


solo_administrador = solo_perfiles()
solo_supervisor = solo_perfiles(GRUPO_SUPERVISOR)
solo_administrativo = solo_perfiles(GRUPO_ADMINISTRATIVO)
solo_personal = solo_perfiles(*GRUPOS_OPERATIVOS)


class RolMiddleware:
    """Impide que un perfil operativo entre a la administración del sistema."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        grupo = grupo_usuario(getattr(request, "user", None))
        if grupo in GRUPOS_OPERATIVOS and request.path.startswith("/administracion"):
            return _denegado(request)
        return self.get_response(request)


def contexto_perfil(request):
    """Variables de plantilla con el perfil de quien navega (ver laserena.context_processors)."""
    grupo = grupo_usuario(getattr(request, "user", None))
    return {
        "grupo_sgr": grupo,
        "es_personal": grupo is not None,
        "es_administrador": grupo == GRUPO_ADMINISTRADOR,
        "es_supervisor": grupo == GRUPO_SUPERVISOR,
        "es_administrativo": grupo == GRUPO_ADMINISTRATIVO,
    }


# --- 5. Ámbito -----------------------------------------------------------------------------


def perfil_funcionario(user):
    """Ficha de funcionario del usuario, si la tiene."""
    if not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "perfil_sgr", None)


def perfil_de_ambito(user):
    """Ficha que restringe la delegación. El Administrador no acota el municipio."""
    perfil = perfil_funcionario(user)
    if perfil is None or es_administrador(user):
        return None
    return perfil


def acotar_ambito(queryset, user, campo):
    """Limita la consulta a la delegación del funcionario. El Administrador ve todo el municipio."""
    perfil = perfil_de_ambito(user)
    if perfil is None:
        return queryset
    return queryset.filter(**{campo: perfil.delegacion_id})


# --- 6. API (Django REST Framework y SimpleJWT) --------------------------------------------
# Perfil Administrador: ve todos los campos y todo el municipio.
# Perfil Usuario (Supervisor y Administrativo): solo campos públicos y su delegación.

ACCION_POR_METODO = {
    "GET": VER,
    "HEAD": VER,
    "OPTIONS": VER,
    "POST": AGREGAR,
    "PUT": MODIFICAR,
    "PATCH": MODIFICAR,
    "DELETE": ELIMINAR,
}


def puede_usar_api(user):
    """Regla de SimpleJWT: solo cuentas activas con un perfil del SGR reciben token."""
    return user is not None and user.is_active and es_personal(user)


class EsPersonalSGR(BasePermission):
    message = "Tu cuenta no tiene un perfil del SGR (Administrador, Supervisor o Administrativo)."

    def has_permission(self, request, view):
        return es_personal(request.user)


class EsAdministradorOSoloLectura(BasePermission):
    """Lectura para todo el personal; crear, modificar y eliminar solo el perfil Administrador."""

    message = "Solo el perfil Administrador puede crear, modificar o eliminar este recurso."

    def has_permission(self, request, view):
        if not es_personal(request.user):
            return False
        return request.method in SAFE_METHODS or es_administrador(request.user)


def permiso_modelo(recurso, acciones=None):
    """Permiso DRF que exige, según el método HTTP, el permiso de Django del grupo sobre `recurso`."""
    mapa = {**ACCION_POR_METODO, **(acciones or {})}

    class PermisoModelo(BasePermission):
        message = "Tu perfil no tiene permiso para realizar esta operación sobre este recurso."

        def has_permission(self, request, view):
            accion = mapa.get(request.method)
            if accion is None or not es_personal(request.user):
                return False
            return request.user.has_perm(codigo_permiso(recurso, accion))

    PermisoModelo.__name__ = f"Permiso_{recurso.replace('.', '_')}"
    return PermisoModelo


PermisoCarta = permiso_modelo("oficina.carta")
# La API no borra actividades: DELETE las anula (queda el código reservado), igual que la web.
PermisoActividad = permiso_modelo("servicios.actividad", {"DELETE": MODIFICAR})
PermisoRevision = permiso_modelo("servicios.actividad", {"POST": APROBAR})
PermisoTarea = permiso_modelo("servicios.tareapreparatoria")


# --- 7. Grupos y nombres de permisos -------------------------------------------------------


def _permisos(codigos):
    from django.contrib.auth.models import Permission

    filtro = Q(pk__in=[])
    for codigo in codigos:
        app_label, codename = codigo.split(".")
        filtro |= Q(content_type__app_label=app_label, codename=codename)
    return Permission.objects.filter(filtro)


def permisos_del_sistema():
    """Todos los permisos que administra el SGR (los que recibe el Administrador)."""
    from django.contrib.auth.models import Permission

    return Permission.objects.filter(
        Q(content_type__app_label__in=APPS_ADMINISTRADOR)
        | Q(content_type__app_label="auth", content_type__model__in=MODELOS_AUTH_ADMINISTRADOR)
    )


def asegurar_grupos():
    """Crea los tres grupos del SGR y les asigna su conjunto de permisos."""
    from django.contrib.auth.models import Group

    definicion = {
        GRUPO_ADMINISTRADOR: permisos_del_sistema(),
        GRUPO_SUPERVISOR: _permisos(codigos_del_perfil(GRUPO_SUPERVISOR)),
        GRUPO_ADMINISTRATIVO: _permisos(codigos_del_perfil(GRUPO_ADMINISTRATIVO)),
    }
    grupos = {}
    for nombre, permisos in definicion.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.set(permisos)
        grupos[nombre] = grupo
    return grupos


def asignar_grupo(usuario, nombre_grupo):
    """Deja al usuario en un único grupo SGR, conservando otros grupos ajenos al SGR."""
    from django.contrib.auth.models import Group

    grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
    usuario.groups.remove(*Group.objects.filter(name__in=GRUPOS_SGR).exclude(pk=grupo.pk))
    usuario.groups.add(grupo)
    if hasattr(usuario, "_grupo_sgr"):
        del usuario._grupo_sgr
    return usuario


def traducir_permisos(permisos):
    """Deja en español los nombres que Django crea en inglés («Can add carta» → «Puede agregar carta…»)."""
    from django.utils import translation

    with translation.override(settings.LANGUAGE_CODE):
        for permiso in permisos.select_related("content_type"):
            modelo = permiso.content_type.model_class()
            accion = accion_del_permiso(permiso.codename, permiso.content_type.model)
            if modelo is None or accion is None or (permiso.codename in ACCION_ESPECIAL):
                continue
            nombre = nombre_permiso(accion, modelo._meta.verbose_name)
            if permiso.name != nombre:
                permiso.name = nombre
                permiso.save(update_fields=["name"])


def sincronizar_grupos(sender, **kwargs):
    # organizaciones es la última app del SGR instalada: para entonces ya existen todos sus permisos.
    if sender.name == "organizaciones":
        traducir_permisos(permisos_del_sistema())
        asegurar_grupos()


def matriz_permisos(grupos=None):
    """Matriz legible de perfiles × permisos, leída desde la base de datos.

    Devuelve `(perfiles, filas)`. Cada fila es un recurso con, por perfil, la lista de acciones en
    español que tiene concedidas (en el orden de ACCIONES).
    """
    from django.contrib.auth.models import Group
    from django.utils import translation

    grupos = list(grupos or Group.objects.filter(name__in=GRUPOS_SGR).prefetch_related("permissions__content_type"))
    grupos.sort(key=lambda g: GRUPOS_SGR.index(g.name) if g.name in GRUPOS_SGR else len(GRUPOS_SGR))
    concedidos = {g.name: {(p.content_type_id, p.codename) for p in g.permissions.all()} for g in grupos}
    filas = []
    with translation.override(settings.LANGUAGE_CODE):
        por_tipo = {}
        for permiso in permisos_del_sistema().select_related("content_type"):
            por_tipo.setdefault(permiso.content_type, []).append(permiso)
        for tipo, permisos in por_tipo.items():
            etiqueta = nombre_recurso(tipo)
            celdas = []
            for grupo in grupos:
                acciones = [accion_del_permiso(p.codename, tipo.model) or p.codename for p in permisos if (tipo.id, p.codename) in concedidos[grupo.name]]
                acciones.sort(key=lambda a: ACCIONES.index(a) if a in ACCIONES else len(ACCIONES))
                celdas.append([a.capitalize() for a in acciones])
            filas.append({"aplicacion": tipo.app_label, "recurso": etiqueta, "celdas": celdas})
    orden_apps = ("auth",) + APPS_ADMINISTRADOR
    filas.sort(key=lambda f: (orden_apps.index(f["aplicacion"]), orden_alfabetico(f["recurso"])))
    return [g.name for g in grupos], filas
