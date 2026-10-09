"""Configuración del Sistema de Gestión de Resultados municipal."""

import os
import sys
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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "institucional",
    "servicios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

LANGUAGE_CODE = "es-cl"
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
LOGIN_REDIRECT_URL = "institucional:panel"
LOGOUT_REDIRECT_URL = "institucional:inicio"

# phpMyAdmin se publica en el mismo dominio (ver deploy/nginx.conf) para que
# Nginx pueda validar la sesión de Django antes de permitir el acceso.
PHPMYADMIN_URL = os.getenv("PHPMYADMIN_URL", "/phpmyadmin/")
PHPMYADMIN_DB = os.getenv("DB_NAME", "sgr_laserena")

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
    },
}

if sys.argv[1:2] == ["test"]:
    LOGGING["loggers"]["laserena.seguridad"]["level"] = "CRITICAL"
