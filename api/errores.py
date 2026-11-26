"""Formato único de errores de la API: siempre JSON, con código HTTP, tipo y mensaje descriptivo."""

import logging
from math import ceil

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler, set_rollback

registro = logging.getLogger("api")
CLAVE_ERRORES_GENERALES = api_settings.NON_FIELD_ERRORS_KEY

TIPOS = {
    400: "solicitud_invalida",
    401: "no_autenticado",
    403: "sin_permiso",
    404: "no_encontrado",
    405: "metodo_no_permitido",
    406: "formato_no_aceptado",
    409: "conflicto",
    415: "tipo_de_contenido_no_soportado",
    429: "demasiadas_solicitudes",
    500: "error_interno",
}

MENSAJES = {
    400: "Los datos enviados no son válidos. Revisa el detalle de cada campo.",
    401: "Debes autenticarte con un token de acceso JWT válido (cabecera Authorization: Bearer <token>).",
    403: "Tu perfil no tiene permiso para realizar esta operación.",
    404: "El recurso solicitado no existe o no está dentro de tu ámbito.",
    429: "Demasiadas solicitudes. Intenta nuevamente más tarde.",
    500: "Ocurrió un error interno. El equipo del SGR fue notificado; intenta nuevamente más tarde.",
}

# Las traducciones al español de DRF y SimpleJWT dejan palabras en inglés («throttled», «blacklist»):
# esos mensajes se reemplazan según el código de error, que no cambia entre versiones.
MENSAJES_POR_CODIGO = {
    "token_not_valid": "El token es inválido, venció o fue revocado.",
    "no_active_account": "Usuario o contraseña incorrectos, o la cuenta no tiene un perfil activo del SGR.",
    "user_inactive": "La cuenta está desactivada.",
    "user_not_found": "La cuenta asociada al token ya no existe.",
    "bad_authorization_header": "La cabecera Authorization debe tener la forma «Bearer <token>».",
}


def cuerpo_error(codigo, mensaje=None, detalle=None):
    error = {"codigo": codigo, "tipo": TIPOS.get(codigo, "error"), "mensaje": mensaje or MENSAJES.get(codigo, "")}
    if detalle:
        error["detalle"] = detalle
    return {"error": error}


def _codigo_error(exc):
    codigos = exc.get_codes() if isinstance(exc, exceptions.APIException) else None
    if isinstance(codigos, dict):
        codigos = codigos.get("code")
    return codigos if isinstance(codigos, str) else None


def _mensaje(exc, datos, codigo):
    if isinstance(exc, exceptions.Throttled):
        return f"Demasiadas solicitudes. Intenta nuevamente en {ceil(exc.wait)} segundos." if exc.wait else MENSAJES[429]
    if _codigo_error(exc) in MENSAJES_POR_CODIGO:
        return MENSAJES_POR_CODIGO[_codigo_error(exc)]
    if isinstance(datos, dict) and isinstance(datos.get("detail"), str):
        return datos["detail"]
    if isinstance(datos, list) and datos and isinstance(datos[0], str):
        return " ".join(datos)
    return MENSAJES.get(codigo)


def manejar_excepcion(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound(MENSAJES[404])
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied(MENSAJES[403])

    respuesta = exception_handler(exc, context)
    if respuesta is None:
        # Nunca se expone la traza ni el mensaje original al cliente: solo queda en el log del servidor.
        vista = context.get("view")
        registro.exception("Error no controlado en la API (%s)", vista.__class__.__name__ if vista else "-")
        set_rollback()
        return Response(cuerpo_error(500), status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    codigo = respuesta.status_code
    if isinstance(exc, exceptions.ValidationError):
        detalle = respuesta.data if isinstance(respuesta.data, dict) else {CLAVE_ERRORES_GENERALES: respuesta.data}
        mensajes_generales = detalle.get(CLAVE_ERRORES_GENERALES)
        mensaje = MENSAJES[400]
        if mensajes_generales and len(detalle) == 1:
            mensaje = " ".join(str(m) for m in mensajes_generales)
        respuesta.data = cuerpo_error(codigo, mensaje, detalle)
    else:
        respuesta.data = cuerpo_error(codigo, _mensaje(exc, respuesta.data, codigo))
    return respuesta
