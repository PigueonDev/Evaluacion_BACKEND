from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class BearerAuthScheme(SimpleJWTScheme):
    """Esquema «BearerAuth» de Swagger para SimpleJWT: un solo candado en Authorize, solo en los endpoints protegidos."""

    name = "BearerAuth"
    priority = 1


def ocultar_rutas_anteriores(endpoints, **kwargs):
    """Hook de drf-spectacular: Swagger muestra solo las rutas en español."""
    from .urls import RUTAS_ANTERIORES

    anteriores = {f"/api/{ruta}" for ruta in RUTAS_ANTERIORES}
    return [endpoint for endpoint in endpoints if endpoint[0] not in anteriores]
