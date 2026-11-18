"""Formato único de errores de la API: siempre JSON, con código HTTP, tipo y mensaje descriptivo."""

import logging

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler, set_rollback

registro = logging.getLogger("api")

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
    401: "Debes autenticarte con un access token JWT válido (cabecera Authorization: Bearer <token>).",
    403: "Tu perfil no tiene permiso para realizar esta operación.",
    404: "El recurso solicitado no existe o no está dentro de tu ámbito.",
    500: "Ocurrió un error interno. El equipo del SGR fue notificado; intenta nuevamente más tarde.",
}


def cuerpo_error(codigo, mensaje=None, detalle=None):
    error = {"codigo": codigo, "tipo": TIPOS.get(codigo, "error"), "mensaje": mensaje or MENSAJES.get(codigo, "")}
    if detalle:
        error["detalle"] = detalle
    return {"error": error}


def _mensaje(datos, codigo):
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
        detalle = respuesta.data if isinstance(respuesta.data, dict) else {"no_field_errors": respuesta.data}
        mensajes_generales = detalle.get("non_field_errors") or detalle.get("no_field_errors")
        mensaje = MENSAJES[400]
        if mensajes_generales and len(detalle) == 1:
            mensaje = " ".join(str(m) for m in mensajes_generales)
        respuesta.data = cuerpo_error(codigo, mensaje, detalle)
    else:
        respuesta.data = cuerpo_error(codigo, _mensaje(respuesta.data, codigo))
    return respuesta
