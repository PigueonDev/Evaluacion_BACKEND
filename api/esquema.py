from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class BearerAuthScheme(SimpleJWTScheme):
    """Esquema «BearerAuth» de Swagger para SimpleJWT: un solo candado en Authorize, solo en los endpoints protegidos."""

    name = "BearerAuth"
    priority = 1
