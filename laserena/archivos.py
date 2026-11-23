import os
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join

from .permisos import solo_personal

TIPOS_IMAGEN = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _disposicion(ruta):
    """Las capturas se muestran en el navegador. El resto se descarga."""
    extension = os.path.splitext(ruta)[1].lower()
    tipo = TIPOS_IMAGEN.get(extension)
    if tipo:
        return "inline", tipo
    return "attachment", None


@solo_personal
def archivo_protegido(request, ruta):
    """Entrega archivos subidos (evidencias) solo al personal autenticado."""
    try:
        ruta_absoluta = safe_join(settings.MEDIA_ROOT, ruta)
    except SuspiciousFileOperation:
        raise Http404
    if not os.path.isfile(ruta_absoluta):
        raise Http404

    disposicion, tipo = _disposicion(ruta)
    if settings.MEDIA_X_ACCEL:
        respuesta = HttpResponse()
        del respuesta["Content-Type"]
        respuesta["X-Accel-Redirect"] = f"/media-protegida/{quote(ruta)}"
    else:
        opciones = {"content_type": tipo} if tipo else {}
        respuesta = FileResponse(open(ruta_absoluta, "rb"), **opciones)
    respuesta["Content-Disposition"] = f"{disposicion}; filename*=UTF-8''{quote(os.path.basename(ruta))}"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta
