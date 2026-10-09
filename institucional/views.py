from urllib.parse import urlencode

from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from laserena.permisos import es_staff, solo_personal
from servicios.models import Actividad, Compromiso, ItemMedicion, Meta, Periodo, Servicio

from .models import Autoridad, Cargo, Delegacion, Funcionario, Municipio

RECURSOS_ADMINISTRABLES = [
    ("Gestión institucional", [
        (Delegacion, "Sedes y delegaciones", "Sedes y delegaciones territoriales con dirección, teléfono y responsable."),
        (Funcionario, "Funcionarios", "Funcionarios asociados a una delegación y un cargo."),
        (Cargo, "Cargos", "Cargos y funciones medibles."),
        (Autoridad, "Autoridades", "Alcaldía, concejo y equipo de gobierno comunal."),
        (Municipio, "Municipio", "Datos institucionales, misión y visión."),
    ]),
    ("Sistema de Gestión de Resultados", [
        (Servicio, "Servicios", "Catálogo de servicios y trámites ciudadanos."),
        (Actividad, "Actividades", "Actividades registradas con código de evidencia."),
        (Compromiso, "Compromisos", "Compromisos de la agenda colectiva."),
        (Meta, "Metas", "Metas y ponderadores por período."),
        (Periodo, "Períodos", "Períodos de medición y umbrales del semáforo."),
        (ItemMedicion, "Ítems de medición", "Ítems de medición asociados a metas."),
    ]),
]


MAXIMO_INTENTOS_LOGIN = 5
BLOQUEO_LOGIN_SEGUNDOS = 15 * 60


def _url_phpmyadmin(base, db, ruta, tabla=None):
    parametros = {"route": ruta, "db": db}
    if tabla:
        parametros["table"] = tabla
    return f"{base.rstrip('/')}/index.php?{urlencode(parametros)}"


def inicio(request):
    municipio = Municipio.objects.first()
    delegaciones = Delegacion.objects.filter(activa=True)
    contexto = {
        "municipio": municipio,
        "delegaciones": delegaciones,
        "antiguedad": 2026 - municipio.fundacion if municipio else 0,
        "servicios_destacados": Servicio.objects.filter(activo=True)[:6],
        "total_servicios": Servicio.objects.filter(activo=True).count(),
        "total_funcionarios": Funcionario.objects.filter(activo=True).count(),
        "pagina_activa": "inicio",
    }
    return render(request, "institucional/inicio.html", contexto)


def autoridades(request):
    contexto = {
        "municipio": Municipio.objects.first(),
        "alcaldia": Autoridad.objects.filter(cargo__icontains="alcald").first(),
        "concejo": Autoridad.objects.exclude(cargo__icontains="alcald"),
        "total_autoridades": Autoridad.objects.filter(activa=True).count(),
        "delegaciones": Delegacion.objects.filter(activa=True),
        "pagina_activa": "autoridades",
    }
    return render(request, "institucional/autoridades.html", contexto)


def _ip_cliente(request):
    ip = request.META.get("REMOTE_ADDR", "")
    if ip in ("127.0.0.1", "::1"):
        ip = request.META.get("HTTP_X_REAL_IP", ip)
    return ip


def _clave_intentos(request):
    usuario = request.POST.get("username", "")[:150].lower()
    return f"login-fallido:{_ip_cliente(request)}:{usuario}"


class AccesoView(auth_views.LoginView):
    template_name = "institucional/acceso.html"
    authentication_form = AdminAuthenticationForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if cache.get(_clave_intentos(request), 0) >= MAXIMO_INTENTOS_LOGIN:
            contexto = self.get_context_data(form=self.get_form_class()(request), bloqueado=True)
            return self.render_to_response(contexto, status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        clave = _clave_intentos(self.request)
        cache.set(clave, cache.get(clave, 0) + 1, BLOQUEO_LOGIN_SEGUNDOS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(_clave_intentos(self.request))
        return super().form_valid(form)


@solo_personal
def panel(request):
    base = settings.PHPMYADMIN_URL
    usa_mysql = settings.DATABASES["default"]["ENGINE"].endswith("mysql")
    db = settings.PHPMYADMIN_DB

    grupos = []
    for titulo, modelos in RECURSOS_ADMINISTRABLES:
        recursos = []
        for modelo, nombre, descripcion in modelos:
            opciones = modelo._meta
            prefijo = f"admin:{opciones.app_label}_{opciones.model_name}"
            recursos.append({
                "nombre": nombre,
                "descripcion": descripcion,
                "tabla": opciones.db_table,
                "total": modelo.objects.count(),
                "phpmyadmin_ver": _url_phpmyadmin(base, db, "/sql", opciones.db_table),
                "phpmyadmin_agregar": _url_phpmyadmin(base, db, "/table/change", opciones.db_table),
                "admin_ver": reverse(f"{prefijo}_changelist"),
                "admin_agregar": reverse(f"{prefijo}_add"),
            })
        grupos.append({"titulo": titulo, "recursos": recursos})

    contexto = {
        "grupos": grupos,
        "base_datos": db,
        "usa_mysql": usa_mysql,
        "phpmyadmin_bd": _url_phpmyadmin(base, db, "/database/structure"),
        "pagina_activa": "panel",
    }
    return render(request, "institucional/panel.html", contexto)


def verificar_acceso(request):
    """Subconsulta de Nginx (auth_request) que protege la ruta de phpMyAdmin."""
    return HttpResponse(status=204 if es_staff(request.user) else 401)
