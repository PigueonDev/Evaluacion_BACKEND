"""Control de acceso de la API sobre los mismos grupos y permisos del SGR web.

Perfil Administrador: grupo Administrador (o superusuario). Ve todos los campos y todo el municipio.
Perfil Usuario: grupos Supervisor y Administrativo. Ven solo campos públicos y su delegación.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from laserena.permisos import es_administracion, es_personal

ACCION_POR_METODO = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "add",
    "PUT": "change",
    "PATCH": "change",
    "DELETE": "delete",
}


def puede_usar_api(user):
    """Regla de SimpleJWT: solo cuentas activas con un perfil del SGR reciben token."""
    return user is not None and user.is_active and es_personal(user)


def es_perfil_administrador(user):
    return es_administracion(user)


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
        return request.method in SAFE_METHODS or es_administracion(request.user)


def permiso_modelo(app_label, modelo, acciones=None):
    """Permiso que exige el permiso de Django del grupo según el método HTTP (view, add, change, delete)."""
    mapa = {**ACCION_POR_METODO, **(acciones or {})}

    class PermisoModelo(BasePermission):
        message = "Tu perfil no tiene permiso para realizar esta operación sobre este recurso."

        def has_permission(self, request, view):
            accion = mapa.get(request.method)
            if accion is None or not es_personal(request.user):
                return False
            codigo = accion if "." in accion else f"{app_label}.{accion}_{modelo}"
            return request.user.has_perm(codigo)

    PermisoModelo.__name__ = f"Permiso_{app_label}_{modelo}"
    return PermisoModelo


PermisoCarta = permiso_modelo("oficina", "carta")
# La API no borra actividades: DELETE las anula (queda el código reservado), igual que la web.
PermisoActividad = permiso_modelo("servicios", "actividad", {"DELETE": "change"})
PermisoRevision = permiso_modelo("servicios", "actividad", {"POST": "servicios.aprobar_actividad"})
PermisoTarea = permiso_modelo("servicios", "tareapreparatoria")
