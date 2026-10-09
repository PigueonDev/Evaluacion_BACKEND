import os
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join

from .permisos import solo_personal


@solo_personal
def archivo_protegido(request, ruta):
    """Entrega archivos subidos (evidencias) solo al personal autenticado."""
    try:
        ruta_absoluta = safe_join(settings.MEDIA_ROOT, ruta)
    except SuspiciousFileOperation:
        raise Http404
    if not os.path.isfile(ruta_absoluta):
        raise Http404

    if settings.MEDIA_X_ACCEL:
        respuesta = HttpResponse()
        del respuesta["Content-Type"]
        respuesta["X-Accel-Redirect"] = f"/media-protegida/{quote(ruta)}"
    else:
        respuesta = FileResponse(open(ruta_absoluta, "rb"))
    respuesta["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(os.path.basename(ruta))}"
    return respuesta
