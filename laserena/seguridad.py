import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

registro = logging.getLogger("laserena.seguridad")

POLITICA_CONTENIDO = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class CabecerasSeguridadMiddleware:
    """Content-Security-Policy y Permissions-Policy para todas las respuestas de Django."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.setdefault("Content-Security-Policy", POLITICA_CONTENIDO)
        respuesta.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        respuesta.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.user.is_authenticated:
            respuesta.setdefault("Cache-Control", "no-store, private")
        return respuesta


def ip_cliente(request):
    if request is None:
        return "-"
    ip = request.META.get("REMOTE_ADDR", "")
    if ip in ("127.0.0.1", "::1"):
        ip = request.META.get("HTTP_X_REAL_IP", ip)
    return ip


@receiver(user_logged_in)
def _login_exitoso(sender, request, user, **kwargs):
    registro.info("Login exitoso usuario=%s ip=%s", user.get_username(), ip_cliente(request))


@receiver(user_login_failed)
def _login_fallido(sender, credentials, request=None, **kwargs):
    registro.warning("Login fallido usuario=%s ip=%s", credentials.get("username", "-")[:150], ip_cliente(request))


@receiver(user_logged_out)
def _logout(sender, request, user, **kwargs):
    registro.info("Cierre de sesión usuario=%s ip=%s", user.get_username() if user else "-", ip_cliente(request))
