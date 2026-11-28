"""Endpoints RESTful del SGR con vistas basadas en funciones (@api_view) documentadas con @extend_schema."""

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError, Q
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView, TokenVerifyView

from institucional.models import Delegacion
from laserena.filtros import parametro_permitido, texto_busqueda
from laserena.permisos import (
    GRUPO_ADMINISTRATIVO,
    EsAdministradorOSoloLectura,
    EsPersonalSGR,
    PermisoActividad,
    PermisoCarta,
    PermisoRevision,
    PermisoTarea,
    es_administrador,
    grupo_usuario,
    perfil_de_ambito,
    perfil_funcionario,
)
from oficina.models import Carta
from oficina.views import _cartas_visibles
from servicios.models import Actividad, TareaPreparatoria
from servicios.reglas import semana_abierta
from servicios.transacciones import marcar_tarea, revisar_actividad
from servicios.views import _actividades_ambito

from .errores import cuerpo_error
from .exportar import TIPO_EXCEL, TIPO_PDF, exportar
from .paginacion import Paginacion
from .serializers import (
    ActividadAdminSerializer,
    ActividadEdicionSerializer,
    ActividadEntradaSerializer,
    ActividadUsuarioSerializer,
    CartaAdminSerializer,
    CartaSeguimientoSerializer,
    CartaUsuarioSerializer,
    ErrorSerializer,
    MensajeSerializer,
    PerfilActualSerializer,
    RevisionSerializer,
    TareaMarcaSerializer,
    TareaSerializer,
    TokenRespuestaSerializer,
    UsuarioAdminSerializer,
    UsuarioEntradaSerializer,
    UsuarioPublicoSerializer,
)

User = get_user_model()


def _paginar(request, queryset, serializer_class):
    paginador = Paginacion()
    pagina = paginador.paginate_queryset(queryset, request)
    return paginador.get_paginated_response(serializer_class(pagina, many=True, context={"request": request}).data)


def _obtener(queryset, pk):
    """El objeto debe existir y estar dentro del ámbito del usuario; si no, 404 (no se revela que existe)."""
    objeto = queryset.filter(pk=pk).first()
    if objeto is None:
        raise Http404
    return objeto


# --- Documentación compartida ---------------------------------------------------------------------

ERROR_400 = OpenApiResponse(ErrorSerializer, description="Datos inválidos: el detalle indica el error de cada campo.", examples=[
    OpenApiExample("Validación", value={"error": {"codigo": 400, "tipo": "solicitud_invalida", "mensaje": "Los datos enviados no son válidos. Revisa el detalle de cada campo.", "detalle": {"remitente": ["Este campo es requerido."]}}}),
])
ERROR_401 = OpenApiResponse(ErrorSerializer, description="Falta el token, está vencido o no es válido.", examples=[
    OpenApiExample("Sin token", value={"error": {"codigo": 401, "tipo": "no_autenticado", "mensaje": "Las credenciales de autenticación no se proveyeron."}}),
])
ERROR_403 = OpenApiResponse(ErrorSerializer, description="El perfil no tiene permiso para la operación.", examples=[
    OpenApiExample("Sin permiso", value={"error": {"codigo": 403, "tipo": "sin_permiso", "mensaje": "Tu perfil no tiene permiso para realizar esta operación sobre este recurso."}}),
])
ERROR_404 = OpenApiResponse(ErrorSerializer, description="No existe o no está dentro del ámbito (delegación) del usuario.", examples=[
    OpenApiExample("No encontrado", value={"error": {"codigo": 404, "tipo": "no_encontrado", "mensaje": "El recurso solicitado no existe o no está dentro de tu ámbito."}}),
])
ERRORES_LECTURA = {401: ERROR_401, 403: ERROR_403}
ERRORES_DETALLE = {401: ERROR_401, 403: ERROR_403, 404: ERROR_404}
ERRORES_ESCRITURA = {400: ERROR_400, 401: ERROR_401, 403: ERROR_403, 404: ERROR_404}

PARAMETROS_PAGINA = [
    OpenApiParameter("pagina", OpenApiTypes.INT, description="Número de página (20 registros por página)."),
    OpenApiParameter("tamano", OpenApiTypes.INT, description="Registros por página, máximo 100."),
]
PARAMETRO_FORMATO = OpenApiParameter("formato", OpenApiTypes.STR, OpenApiParameter.PATH, enum=["excel", "pdf"], description="excel (.xlsx) o pdf.")
RESPUESTAS_EXPORTACION = {
    (200, TIPO_EXCEL): OpenApiResponse(OpenApiTypes.BINARY, description="Archivo Excel (.xlsx)."),
    (200, TIPO_PDF): OpenApiResponse(OpenApiTypes.BINARY, description="Archivo PDF con encabezado, pie y números de página."),
    **ERRORES_LECTURA,
}


# --- Autenticación JWT ------------------------------------------------------------------------------

EJEMPLO_TOKEN = {"access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…", "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…", "perfil": "Administrador"}


class _ConLimiteDeIntentos:
    """Limita los intentos por IP (10 por minuto por defecto) para frenar ataques de fuerza bruta."""

    throttle_scope = "token"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle

        return [ScopedRateThrottle()]


@extend_schema(
    tags=["Autenticación JWT"], auth=[],
    summary="Obtener el token de acceso y el de renovación",
    description="Entrega un **token de acceso** (`access`, 15 min) y un **token de renovación** (`refresh`, 8 h) a una cuenta activa del SGR. Los nombres `username`, `password`, `access` y `refresh` son los del estándar JWT de SimpleJWT. Copia el valor de `access` en el botón **Authorize** (Autorizar) de Swagger.",
    examples=[
        OpenApiExample("Credenciales", value={"username": "admin.demo", "password": "Serena-demo-2026"}, request_only=True),
        OpenApiExample("Tokens emitidos", value=EJEMPLO_TOKEN, response_only=True, status_codes=["200"]),
    ],
    responses={200: TokenRespuestaSerializer, 400: ERROR_400, 401: OpenApiResponse(ErrorSerializer, description="Usuario o contraseña incorrectos, o cuenta sin perfil SGR.", examples=[
        OpenApiExample("Credenciales inválidas", value={"error": {"codigo": 401, "tipo": "no_autenticado", "mensaje": "Usuario o contraseña incorrectos, o la cuenta no tiene un perfil activo del SGR."}}),
    ]), 429: OpenApiResponse(ErrorSerializer, description="Demasiados intentos desde la misma IP.")},
)
class ObtenerTokenView(_ConLimiteDeIntentos, TokenObtainPairView):
    pass


@extend_schema(
    tags=["Autenticación JWT"], auth=[],
    summary="Renovar el token de acceso",
    description="Recibe el token de renovación (`refresh`) y entrega un token de acceso nuevo **y un token de renovación nuevo**: el anterior queda en la lista negra (rotación).",
    responses={200: OpenApiResponse(description="Nuevo token de acceso y nuevo token de renovación."), 400: ERROR_400, 401: ERROR_401},
)
class RenovarTokenView(_ConLimiteDeIntentos, TokenRefreshView):
    pass


@extend_schema(tags=["Autenticación JWT"], auth=[], summary="Verificar un token", description="Responde 200 si el token es válido y no ha vencido; 401 si no lo es.",
    responses={200: OpenApiResponse(description="Token válido."), 401: ERROR_401})
class VerificarTokenView(_ConLimiteDeIntentos, TokenVerifyView):
    pass


@extend_schema(tags=["Autenticación JWT"], auth=[], summary="Cerrar sesión (revocar el token de renovación)",
    description="Agrega el token de renovación a la lista negra: ya no sirve para pedir tokens de acceso nuevos.",
    responses={200: OpenApiResponse(description="Token de renovación revocado."), 401: ERROR_401})
class RevocarTokenView(_ConLimiteDeIntentos, TokenBlacklistView):
    pass


@extend_schema(tags=["Autenticación JWT"], summary="Perfil de la cuenta autenticada", responses={200: PerfilActualSerializer, 401: ERROR_401})
@api_view(["GET"])
@permission_classes([EsPersonalSGR])
def perfil_actual(request):
    perfil = perfil_funcionario(request.user)
    es_admin = es_administrador(request.user)
    return Response({
        "usuario": request.user.get_username(),
        "nombre": perfil.nombre_completo if perfil else request.user.get_full_name(),
        "perfil": grupo_usuario(request.user),
        "es_administrador": es_admin,
        "delegacion": perfil.delegacion.nombre if perfil else None,
        "cargo": perfil.cargo.nombre if perfil else None,
        "ve_datos_sensibles": es_admin,
    })


# --- Mantenedor 1: usuarios ---------------------------------------------------------------------------

EJEMPLO_USUARIO = {
    "usuario": "territorial.norte", "nombres": "Paula", "apellidos": "Rojas", "correo": "paula.rojas@laserena.cl",
    "perfil": "Administrativo", "activo": True, "identificador": "F-210", "delegacion": 1, "cargo": 5, "codigo_area": "COM2",
    "clave": "Territorio-Norte-2026", "clave_confirmacion": "Territorio-Norte-2026",
}


def _usuarios_visibles(user):
    usuarios = User.objects.select_related("perfil_sgr__delegacion", "perfil_sgr__cargo").prefetch_related("groups").order_by("username")
    if es_administrador(user):
        return usuarios
    perfil = perfil_de_ambito(user)
    if perfil is None:
        return usuarios.none()
    return usuarios.filter(is_active=True, perfil_sgr__activo=True, perfil_sgr__delegacion=perfil.delegacion)


def _serializer_usuario(request):
    return UsuarioAdminSerializer if es_administrador(request.user) else UsuarioPublicoSerializer


@extend_schema(
    methods=["GET"], tags=["Usuarios"], summary="Listar usuarios",
    description="Administrador: todas las cuentas con correo, último acceso y ficha completa. "
                "Supervisor y Administrativo: solo nombre, perfil, cargo y delegación del personal activo de su delegación.",
    parameters=[OpenApiParameter("q", OpenApiTypes.STR, description="Busca por usuario o nombre."), *PARAMETROS_PAGINA],
    responses={200: UsuarioAdminSerializer(many=True), **ERRORES_LECTURA},
)
@extend_schema(
    methods=["POST"], tags=["Usuarios"], summary="Crear usuario (solo Administrador)",
    description="Crea la cuenta, la asigna a su perfil y crea su ficha de funcionario. La contraseña se valida con las políticas de Django y nunca se devuelve.",
    request=UsuarioEntradaSerializer,
    examples=[OpenApiExample("Nuevo Administrativo", value=EJEMPLO_USUARIO, request_only=True)],
    responses={201: UsuarioAdminSerializer, **ERRORES_ESCRITURA},
)
@api_view(["GET", "POST"])
@permission_classes([EsAdministradorOSoloLectura])
def usuarios_lista(request):
    if request.method == "GET":
        usuarios = _usuarios_visibles(request.user)
        busqueda = texto_busqueda(request)
        if busqueda:
            usuarios = usuarios.filter(Q(username__icontains=busqueda) | Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda) | Q(perfil_sgr__nombre_completo__icontains=busqueda))
        return _paginar(request, usuarios, _serializer_usuario(request))

    serializer = UsuarioEntradaSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    usuario = serializer.save()
    return Response(UsuarioAdminSerializer(usuario).data, status=status.HTTP_201_CREATED)


@extend_schema(methods=["GET"], tags=["Usuarios"], summary="Detalle de un usuario", responses={200: UsuarioAdminSerializer, **ERRORES_DETALLE})
@extend_schema(
    methods=["PUT"], tags=["Usuarios"], summary="Modificar usuario (solo Administrador)",
    description="Si `clave` va vacía se conserva la contraseña actual. Un Administrador no puede quitarse su propio perfil ni desactivarse.",
    request=UsuarioEntradaSerializer, responses={200: UsuarioAdminSerializer, **ERRORES_ESCRITURA},
)
@extend_schema(
    methods=["DELETE"], tags=["Usuarios"], summary="Eliminar usuario (solo Administrador)",
    description="Si la cuenta tiene registros asociados (auditoría, actividades) se desactiva en vez de borrarse.",
    responses={200: MensajeSerializer, **ERRORES_ESCRITURA},
)
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([EsAdministradorOSoloLectura])
def usuario_detalle(request, pk):
    usuario = _obtener(_usuarios_visibles(request.user), pk)

    if request.method == "GET":
        return Response(_serializer_usuario(request)(usuario).data)

    if request.method == "PUT":
        serializer = UsuarioEntradaSerializer(usuario, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        return Response(UsuarioAdminSerializer(User.objects.get(pk=usuario.pk)).data)

    if usuario == request.user:
        return Response(cuerpo_error(400, "No puedes eliminar tu propia cuenta."), status=status.HTTP_400_BAD_REQUEST)
    nombre = usuario.username
    try:
        usuario.delete()
    except ProtectedError:
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        return Response({"mensaje": f"{nombre} tiene registros asociados: la cuenta se desactivó en lugar de eliminarse.", "id": pk})
    return Response({"mensaje": f"Cuenta {nombre} eliminada.", "id": pk})


# --- Mantenedor 2: cartas de Oficina de Partes -----------------------------------------------------------

EJEMPLO_CARTA = {
    "fecha_ingreso": "2026-11-16", "numero_oficina_partes": "4521", "destinatario": "delegado", "tipo": "solicitud",
    "remitente": "Junta de Vecinos Las Rosas", "contacto_remitente": "+56 9 8765 4321", "asunto": "Poda de árboles en pasaje Los Aromos",
    "detalle": "Solicitan poda por riesgo de caída de ramas.", "delegacion": 1, "estado": "ingresada", "plazo_respuesta": "2026-11-30",
}


def _filtrar_cartas(request, cartas):
    busqueda = texto_busqueda(request)
    if busqueda:
        cartas = cartas.filter(Q(folio__icontains=busqueda) | Q(numero_oficina_partes__icontains=busqueda) | Q(remitente__icontains=busqueda) | Q(asunto__icontains=busqueda))
    estado = parametro_permitido(request, "estado", dict(Carta.ESTADOS))
    if estado:
        cartas = cartas.filter(estado=estado)
    resolucion = parametro_permitido(request, "resolucion", dict(Carta.RESOLUCIONES))
    if resolucion:
        cartas = cartas.filter(resolucion=resolucion)
    delegacion = parametro_permitido(request, "delegacion", {str(pk) for pk in Delegacion.objects.values_list("pk", flat=True)})
    if delegacion:
        cartas = cartas.filter(delegacion_id=delegacion)
    return cartas


def cartas_para_exportar(request):
    return _filtrar_cartas(request, _cartas_visibles(request.user).select_related("derivada_a_unidad", "registrada_por"))


def _serializer_carta(request):
    return CartaAdminSerializer if es_administrador(request.user) else CartaUsuarioSerializer


def _contexto_carta(request):
    contexto = {"request": request}
    perfil = perfil_de_ambito(request.user)
    if perfil is not None:
        contexto["valores_fijos"] = {"delegacion": perfil.delegacion}
    return contexto


PARAMETROS_CARTAS = [
    OpenApiParameter("q", OpenApiTypes.STR, description="Busca por folio, N° OP, remitente o asunto."),
    OpenApiParameter("estado", OpenApiTypes.STR, enum=[c for c, _ in Carta.ESTADOS]),
    OpenApiParameter("resolucion", OpenApiTypes.STR, enum=[c for c, _ in Carta.RESOLUCIONES], description="Estado en la matriz (tubo de cartas)."),
    OpenApiParameter("delegacion", OpenApiTypes.INT, description="ID de la delegación (útil para el Administrador)."),
]


@extend_schema(
    methods=["GET"], tags=["Cartas"], summary="Listar cartas",
    description="Administrador: todas las delegaciones y todos los campos. Supervisor: su delegación, sin `contacto_remitente` ni `registrada_por`. "
                "Administrativo: solo las cartas derivadas a él.",
    parameters=[*PARAMETROS_CARTAS, *PARAMETROS_PAGINA], responses={200: CartaAdminSerializer(many=True), **ERRORES_LECTURA},
)
@extend_schema(
    methods=["POST"], tags=["Cartas"], summary="Ingresar carta",
    description="Genera el folio `OP-AAAA-NNNN`. El Supervisor registra en su delegación (el campo `delegacion` se ignora). El Administrativo no puede ingresar cartas (403).",
    request=CartaAdminSerializer,
    examples=[
        OpenApiExample("Nueva carta", value=EJEMPLO_CARTA, request_only=True),
        OpenApiExample("Carta creada", value={"id": 12, "folio": "OP-2026-0012", **EJEMPLO_CARTA, "estado_texto": "Ingresada", "vencida": False}, response_only=True, status_codes=["201"]),
    ],
    responses={201: CartaAdminSerializer, **ERRORES_ESCRITURA},
)
@api_view(["GET", "POST"])
@permission_classes([PermisoCarta])
def cartas_lista(request):
    if request.method == "GET":
        cartas = _filtrar_cartas(request, _cartas_visibles(request.user).select_related("registrada_por"))
        return _paginar(request, cartas, _serializer_carta(request))

    contexto = _contexto_carta(request)
    serializer = _serializer_carta(request)(data=request.data, context=contexto)
    serializer.is_valid(raise_exception=True)
    carta = serializer.save(registrada_por=request.user, **contexto.get("valores_fijos", {}))
    return Response(_serializer_carta(request)(carta, context=contexto).data, status=status.HTTP_201_CREATED)


@extend_schema(methods=["GET"], tags=["Cartas"], summary="Detalle de una carta", responses={200: CartaAdminSerializer, **ERRORES_DETALLE})
@extend_schema(
    methods=["PUT"], tags=["Cartas"], summary="Modificar carta",
    description="Administrador y Supervisor modifican la carta completa. El Administrativo solo envía `estado` (derivada, en_respuesta, respondida), "
                "`resolucion`, `respuesta` y `fecha_respuesta` de las cartas derivadas a él.",
    request=CartaAdminSerializer,
    examples=[OpenApiExample("Responder", value={**EJEMPLO_CARTA, "estado": "respondida", "respuesta": "Se programó la poda para el 20/11.", "fecha_respuesta": "2026-11-17"}, request_only=True)],
    responses={200: CartaAdminSerializer, **ERRORES_ESCRITURA},
)
@extend_schema(methods=["DELETE"], tags=["Cartas"], summary="Eliminar carta", description="Solo Administrador y Supervisor.", responses={200: MensajeSerializer, **ERRORES_DETALLE})
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([PermisoCarta])
def carta_detalle(request, pk):
    carta = _obtener(_cartas_visibles(request.user).select_related("registrada_por"), pk)
    salida = _serializer_carta(request)

    if request.method == "GET":
        return Response(salida(carta).data)

    if request.method == "PUT":
        contexto = _contexto_carta(request)
        entrada = CartaSeguimientoSerializer if grupo_usuario(request.user) == GRUPO_ADMINISTRATIVO else salida
        serializer = entrada(carta, data=request.data, context=contexto)
        serializer.is_valid(raise_exception=True)
        carta = serializer.save()
        return Response(salida(carta, context=contexto).data)

    folio = carta.folio
    carta.delete()
    return Response({"mensaje": f"Carta {folio} eliminada.", "id": pk})


@extend_schema(
    tags=["Cartas"], summary="Exportar cartas a Excel o PDF",
    description="Aplica los mismos filtros y el mismo ámbito del listado. El perfil Usuario recibe el archivo sin las columnas sensibles.",
    parameters=[PARAMETRO_FORMATO, *PARAMETROS_CARTAS], responses=RESPUESTAS_EXPORTACION,
)
@api_view(["GET"])
@permission_classes([PermisoCarta])
def cartas_exportar(request, formato):
    return exportar("cartas", formato, cartas_para_exportar(request), request.user, es_administrador(request.user))


# --- Transacción: registrar actividad ---------------------------------------------------------------------

EJEMPLO_ACTIVIDAD = {
    "fecha": "2026-11-17", "periodo": 2, "item": 7, "descripcion": "Taller de huertos urbanos con la JJVV Villa Alegre",
    "accion": "Se coordinó el taller y se inscribieron 25 vecinos.", "contacto": "María González (presidenta)", "telefono": "+56 9 1234 5678",
    "solicitante": "Junta de Vecinos Villa Alegre", "derivado_a": None, "compromiso": None,
    "tareas": [{"descripcion": "Gestión de sillas"}, {"descripcion": "Gestión de afiches y WhatsApp"}],
}


def _filtrar_actividades(request, actividades):
    estado = parametro_permitido(request, "estado", dict(Actividad.ESTADOS))
    if estado:
        actividades = actividades.filter(estado=estado)
    busqueda = texto_busqueda(request)
    if busqueda:
        actividades = actividades.filter(Q(descripcion__icontains=busqueda) | Q(solicitante__icontains=busqueda) | Q(funcionario__nombre_completo__icontains=busqueda) | Q(item__nombre__icontains=busqueda) | Q(codigo_verificador__icontains=busqueda))
    return actividades


def actividades_para_exportar(request):
    return _filtrar_actividades(request, _actividades_ambito(request.user).select_related("derivado_a"))


def _serializer_actividad(request):
    return ActividadAdminSerializer if es_administrador(request.user) else ActividadUsuarioSerializer


def _actividad_propia(request, actividad):
    """El Administrativo solo modifica sus propias actividades; el Administrador, cualquiera."""
    if es_administrador(request.user):
        return True
    return actividad.funcionario_id == getattr(perfil_funcionario(request.user), "pk", None)


SOLO_PROPIAS = Response(cuerpo_error(403, "Solo puedes modificar tus propias actividades."), status=status.HTTP_403_FORBIDDEN)

PARAMETROS_ACTIVIDADES = [
    OpenApiParameter("q", OpenApiTypes.STR, description="Busca por actividad, funcionario, ítem o código verificador."),
    OpenApiParameter("estado", OpenApiTypes.STR, enum=[c for c, _ in Actividad.ESTADOS]),
]


@extend_schema(
    methods=["GET"], tags=["Actividades"], summary="Consultar actividades",
    description="Actividades de la delegación del usuario (Administrador: todo el municipio) con sus tareas. "
                "`contacto` y `telefono` de la persona atendida solo aparecen para el Administrador.",
    parameters=[*PARAMETROS_ACTIVIDADES, *PARAMETROS_PAGINA], responses={200: ActividadAdminSerializer(many=True), **ERRORES_LECTURA},
)
@extend_schema(
    methods=["POST"], tags=["Actividades"], summary="Registrar actividad (transacción)",
    description="Guarda la actividad, sus tareas preparatorias y la auditoría en una sola transacción atómica, que bloquea la ficha del funcionario para que dos registros simultáneos no superen el cupo diario. "
                "Reglas: día hábil de la semana en curso, sin fechas futuras, máximo 7 actividades por día, período abierto, ítem del cargo. "
                "Si una regla falla no se guarda nada. Lo registra el Administrativo (para sí mismo) o el Administrador (indicando `funcionario`).",
    request=ActividadEntradaSerializer,
    examples=[OpenApiExample("Actividad con tareas", value=EJEMPLO_ACTIVIDAD, request_only=True)],
    responses={201: ActividadAdminSerializer, **ERRORES_ESCRITURA},
)
@api_view(["GET", "POST"])
@permission_classes([PermisoActividad])
def actividades_lista(request):
    if request.method == "GET":
        actividades = _filtrar_actividades(request, _actividades_ambito(request.user).select_related("derivado_a", "revisada_por").prefetch_related("tareas"))
        return _paginar(request, actividades, _serializer_actividad(request))

    contexto = {"request": request}
    if not es_administrador(request.user):
        perfil = perfil_funcionario(request.user)
        if perfil is None:
            return Response(cuerpo_error(400, "Tu cuenta no tiene ficha de funcionario: no puede registrar actividades."), status=status.HTTP_400_BAD_REQUEST)
        contexto["funcionario"] = perfil
    serializer = ActividadEntradaSerializer(data=request.data, context=contexto)
    serializer.is_valid(raise_exception=True)
    actividad = serializer.save()
    return Response(_serializer_actividad(request)(Actividad.objects.get(pk=actividad.pk)).data, status=status.HTTP_201_CREATED)


@extend_schema(methods=["GET"], tags=["Actividades"], summary="Detalle de una actividad", responses={200: ActividadAdminSerializer, **ERRORES_DETALLE})
@extend_schema(
    methods=["PUT"], tags=["Actividades"], summary="Modificar actividad",
    description="Solo mientras está pendiente de aprobación y su semana laboral sigue abierta. El Administrativo modifica únicamente las suyas.",
    request=ActividadEdicionSerializer, responses={200: ActividadAdminSerializer, **ERRORES_ESCRITURA},
)
@extend_schema(
    methods=["DELETE"], tags=["Actividades"], summary="Anular actividad",
    description="La actividad no se borra: queda **anulada** y su código verificador reservado. No se anula una actividad aprobada ni de una semana cerrada.",
    responses={200: ActividadAdminSerializer, **ERRORES_ESCRITURA},
)
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([PermisoActividad])
def actividad_detalle(request, pk):
    actividad = _obtener(_actividades_ambito(request.user).prefetch_related("tareas"), pk)
    salida = _serializer_actividad(request)

    if request.method == "GET":
        return Response(salida(actividad).data)
    if not _actividad_propia(request, actividad):
        return SOLO_PROPIAS
    if actividad.periodo.estado != "abierto":
        return Response(cuerpo_error(400, "El período está cerrado: la actividad se puede consultar, no modificar."), status=status.HTTP_400_BAD_REQUEST)

    if request.method == "PUT":
        serializer = ActividadEdicionSerializer(actividad, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(salida(Actividad.objects.get(pk=pk)).data)

    if not semana_abierta(actividad.fecha):
        return Response(cuerpo_error(400, "La semana laboral de esta actividad ya cerró: queda bloqueada."), status=status.HTTP_400_BAD_REQUEST)
    if actividad.estado == "validada":
        return Response(cuerpo_error(400, "Una actividad aprobada no se anula."), status=status.HTTP_400_BAD_REQUEST)
    if actividad.estado == "anulada":
        return Response(cuerpo_error(400, "La actividad ya estaba anulada."), status=status.HTTP_400_BAD_REQUEST)
    actividad.estado = "anulada"
    actividad.save(update_fields=["estado"])
    return Response(salida(actividad).data)


@extend_schema(
    tags=["Actividades"], summary="Marcar una tarea preparatoria",
    description="Marca la tarea como realizada o pendiente. Solo con la actividad pendiente y la semana abierta.",
    request=TareaMarcaSerializer, examples=[OpenApiExample("Realizada", value={"realizada": True}, request_only=True)],
    responses={200: TareaSerializer, **ERRORES_ESCRITURA},
)
@api_view(["PUT"])
@permission_classes([PermisoTarea])
def tarea_marcar(request, pk, tarea_pk):
    actividad = _obtener(_actividades_ambito(request.user), pk)
    if not _actividad_propia(request, actividad):
        return SOLO_PROPIAS
    tarea = _obtener(TareaPreparatoria.objects.filter(actividad=actividad), tarea_pk)
    serializer = TareaMarcaSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    marcar_tarea(tarea, serializer.validated_data["realizada"], request.user)
    return Response(TareaSerializer(tarea).data)


@extend_schema(
    tags=["Actividades"], summary="Aprobar o rechazar una actividad (Supervisor)",
    description="Solo se aprueba con todas las tareas realizadas. Para rechazar hay que indicar la observación. Una vez aprobada suma al cumplimiento de la matriz.",
    request=RevisionSerializer,
    examples=[OpenApiExample("Aprobar", value={"decision": "aprobar", "observacion": ""}, request_only=True),
              OpenApiExample("Rechazar", value={"decision": "rechazar", "observacion": "Falta la evidencia del taller."}, request_only=True)],
    responses={200: ActividadAdminSerializer, **ERRORES_ESCRITURA},
)
@api_view(["POST"])
@permission_classes([PermisoRevision])
def actividad_revision(request, pk):
    actividad = _obtener(_actividades_ambito(request.user), pk)
    serializer = RevisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    revisar_actividad(actividad, serializer.validated_data["decision"], request.user, serializer.validated_data["observacion"])
    return Response(_serializer_actividad(request)(Actividad.objects.get(pk=pk)).data)


@extend_schema(
    tags=["Actividades"], summary="Exportar actividades a Excel o PDF",
    description="Mismos filtros y ámbito del listado. El perfil Usuario recibe el archivo sin `Contacto` ni `Teléfono`.",
    parameters=[PARAMETRO_FORMATO, *PARAMETROS_ACTIVIDADES], responses=RESPUESTAS_EXPORTACION,
)
@api_view(["GET"])
@permission_classes([PermisoActividad])
def actividades_exportar(request, formato):
    return exportar("actividades", formato, actividades_para_exportar(request), request.user, es_administrador(request.user))


@extend_schema(exclude=True)
@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def ruta_no_encontrada(request, ruta=""):
    return Response(cuerpo_error(404, "La ruta solicitada no existe en la API. Revisa la documentación en /api/swagger/."), status=status.HTTP_404_NOT_FOUND)
