"""Configuración del Sistema de Gestión de Resultados municipal."""

import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
if not DEBUG and SECRET_KEY in ("", "dev-only-change-me", "cambia-esta-clave"):
    raise ImproperlyConfigured("Define un SECRET_KEY propio en .env antes de ejecutar con DEBUG=False.")
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "institucional",
    "servicios",
    "oficina",
    "organizaciones",
    "rest_framework",
    # Se instala la app base de SimpleJWT solo para cargar sus traducciones al español.
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "institucional.claves.ClaveTemporalMiddleware",
    "laserena.permisos.RolMiddleware",
    "laserena.seguridad.CabecerasSeguridadMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "laserena.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "laserena.context_processors.administracion",
            ],
        },
    },
]

WSGI_APPLICATION = "laserena.wsgi.application"

if os.getenv("DB_ENGINE", "sqlite").lower() == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "sgr_laserena"),
            "USER": os.getenv("DB_USER", "sgr_user"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"},
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Todo el sistema en español: los textos propios ya lo están y Django, DRF y SimpleJWT traen sus traducciones.
LANGUAGE_CODE = "es-cl"
LANGUAGES = [("es-cl", "Español (Chile)")]
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Con Nginx delante, Django solo autoriza y Nginx entrega el archivo (X-Accel-Redirect).
MEDIA_X_ACCEL = os.getenv("MEDIA_X_ACCEL", str(not DEBUG)).lower() == "true"
LOGIN_URL = "institucional:acceso"
LOGIN_REDIRECT_URL = "institucional:mi_panel"
LOGOUT_REDIRECT_URL = "institucional:acceso"

# phpMyAdmin se publica en el mismo dominio (ver deploy/nginx.conf) para que
# Nginx pueda validar la sesión de Django antes de permitir el acceso.
PHPMYADMIN_URL = os.getenv("PHPMYADMIN_URL", "/phpmyadmin/")
PHPMYADMIN_DB = os.getenv("DB_NAME", "sgr_laserena")

# Correo para la recuperación de contraseña: SMTP de Gmail con contraseña de aplicación.
# Sin credenciales se usa el backend de archivo (correos_enviados/) para que el sitio no falle.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "").replace(" ", "")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "15"))
EMAIL_FILE_PATH = os.getenv("EMAIL_FILE_PATH", str(BASE_DIR / "correos_enviados"))
if EMAIL_BACKEND.endswith("smtp.EmailBackend") and not (EMAIL_HOST_USER and EMAIL_HOST_PASSWORD):
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
# Gmail reemplaza el remitente por la cuenta autenticada; por eso el valor por defecto es esa cuenta.
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or (f"SGR La Serena <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "SGR La Serena <no-responder@laserena.cl>")
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", str(60 * 60)))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Caché compartida entre los workers de Gunicorn (necesaria para contar intentos de login fallidos).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.getenv("CACHE_DIR", str(BASE_DIR / ".cache")),
    }
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 2 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Activar solo cuando el sitio se sirva con certificado HTTPS.
if os.getenv("HTTPS", "False").lower() == "true":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # La subconsulta auth_request de Nginx no debe recibir redirecciones.
    SECURE_REDIRECT_EXEMPT = [r"^acceso/verificar/$"]
    SECURE_HSTS_SECONDS = 30 * 24 * 60 * 60

# --- API REST (Django REST Framework + SimpleJWT + drf-spectacular) ---------------
# Todo endpoint exige un token de acceso válido salvo que la vista diga lo contrario.
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",)
    + (("rest_framework.renderers.BrowsableAPIRenderer",) if DEBUG else ()),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_CONTENT_NEGOTIATION_CLASS": "api.negociacion.NegociacionJSON",
    "EXCEPTION_HANDLER": "api.errores.manejar_excepcion",
    "DEFAULT_PAGINATION_CLASS": "api.paginacion.Paginacion",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_LIMITE_ANONIMO", "60/min"),
        "user": os.getenv("API_LIMITE_USUARIO", "600/min"),
        "token": os.getenv("API_LIMITE_TOKEN", "10/min"),
    },
    # Nginx agrega la IP real al final de X-Forwarded-For; así un cliente no evade el límite falsificando esa cabecera.
    "NUM_PROXIES": int(os.getenv("API_NUM_PROXIES", "1")),
    "UNICODE_JSON": True,
    "NON_FIELD_ERRORS_KEY": "errores_generales",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTOS", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=int(os.getenv("JWT_REFRESH_HORAS", "8"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.getenv("JWT_SIGNING_KEY") or SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_AUTHENTICATION_RULE": "laserena.permisos.puede_usar_api",
    "TOKEN_OBTAIN_SERIALIZER": "api.serializers.TokenSGRSerializer",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API SGR · Municipalidad de La Serena",
    "DESCRIPTION": (
        "API RESTful del Sistema de Gestión de Resultados (SGR) de las delegaciones municipales.\n\n"
        "1. Obtén los tokens en `POST /api/token/` con tu usuario (`username`) y contraseña (`password`) del SGR.\n"
        "2. Pulsa el botón **Authorize** (Autorizar) y pega el valor de `access` (sin escribir «Bearer»).\n"
        "3. El token de acceso dura 15 minutos; renuévalo con el token de renovación (`refresh`) en `POST /api/token/renovar/`.\n\n"
        "El perfil **Administrador** recibe todos los campos. Los perfiles **Supervisor** y **Administrativo** "
        "(perfil Usuario) solo reciben campos públicos y operacionales de su delegación: nunca contraseñas, "
        "correos, teléfonos ni contactos personales.\n\n"
        "Los errores siempre vuelven en JSON: `{\"error\": {\"codigo\", \"tipo\", \"mensaje\", \"detalle\"}}`. "
        "Los listados vienen paginados con `total`, `siguiente`, `anterior` y `resultados`."
    ),
    "VERSION": "1.0.0",
    "CONTACT": {"name": "Cristhopher Rubio y Rodrigo Álvarez · INACAP La Serena"},
    "SERVE_INCLUDE_SCHEMA": False,
    "PREPROCESSING_HOOKS": ["api.esquema.ocultar_rutas_anteriores"],
    "SCHEMA_PATH_PREFIX": r"/api/",
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": False, "displayRequestDuration": True, "tryItOutEnabled": True},
    # El esquema de seguridad «BearerAuth» (http, bearer, JWT) lo registra api/esquema.py.
    "ENUM_NAME_OVERRIDES": {
        "TipoCartaEnum": "oficina.models.Carta.TIPOS",
        "TipoTareaEnum": "servicios.models.TareaPreparatoria.TIPOS",
    },
    "TAGS": [
        {"name": "Autenticación JWT", "description": "Obtención, renovación, verificación y revocación de tokens."},
        {"name": "Usuarios", "description": "Mantenedor 1: cuentas, perfil y ficha de funcionario."},
        {"name": "Cartas", "description": "Mantenedor 2: cartas de Oficina de Partes (tubo de cartas)."},
        {"name": "Actividades", "description": "Transacción «Registrar actividad» con sus tareas preparatorias."},
    ],
}

FILE_UPLOAD_PERMISSIONS = 0o640
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"consola": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {
        "laserena.seguridad": {"handlers": ["consola"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
        "institucional": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
        "api": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
    },
}

if sys.argv[1:2] == ["test"]:
    LOGGING["loggers"]["laserena.seguridad"]["level"] = "CRITICAL"
    LOGGING["loggers"]["institucional"]["level"] = "CRITICAL"
    LOGGING["loggers"]["api"]["level"] = "CRITICAL"
