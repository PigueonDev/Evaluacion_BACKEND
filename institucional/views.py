from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from laserena.permisos import (
    GRUPO_ADMINISTRADOR,
    GRUPO_ADMINISTRATIVO,
    GRUPO_SUPERVISOR,
    GRUPOS_SGR,
    acotar_ambito,
    es_administracion,
    grupo_usuario,
    parametro_permitido,
    perfil_funcionario,
    solo_administracion,
    solo_grupos,
    texto_busqueda,
)
from laserena.seguridad import ip_cliente
from oficina.models import Ausencia, BeneficioNino, Carta
from organizaciones.models import OrganizacionComunitaria
from servicios.models import Actividad, Auditoria, Caso, Compromiso, ItemMedicion, Meta, Periodo, Servicio
from servicios.reglas import MAXIMO_ACTIVIDADES_POR_DIA, fin_semana_laboral, inicio_semana

from .forms import AccesoForm, GrupoForm, NuevaClaveForm, RecuperarClaveForm, UsuarioForm
from .models import Autoridad, Cargo, Delegacion, Funcionario, Municipio

User = get_user_model()
USUARIOS_POR_PAGINA = 20

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


def _clave_intentos(request):
    usuario = request.POST.get("username", "")[:150].lower()
    return f"login-fallido:{ip_cliente(request)}:{usuario}"


class AccesoView(auth_views.LoginView):
    template_name = "institucional/acceso.html"
    authentication_form = AccesoForm
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


class RecuperarClaveView(auth_views.PasswordResetView):
    template_name = "institucional/recuperar/solicitar.html"
    email_template_name = "institucional/recuperar/correo.txt"
    html_email_template_name = "institucional/recuperar/correo.html"
    subject_template_name = "institucional/recuperar/asunto.txt"
    form_class = RecuperarClaveForm
    success_url = reverse_lazy("institucional:recuperar_enviado")


class RecuperarClaveEnviadoView(auth_views.PasswordResetDoneView):
    template_name = "institucional/recuperar/enviado.html"


class RecuperarClaveConfirmarView(auth_views.PasswordResetConfirmView):
    template_name = "institucional/recuperar/nueva_clave.html"
    form_class = NuevaClaveForm
    success_url = reverse_lazy("institucional:recuperar_listo")


class RecuperarClaveListoView(auth_views.PasswordResetCompleteView):
    template_name = "institucional/recuperar/listo.html"


@solo_grupos(GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO)
def mi_panel(request):
    """Dashboard según el grupo del usuario autenticado."""
    grupo = grupo_usuario(request.user)
    if grupo == GRUPO_ADMINISTRADOR:
        return redirect("institucional:panel")
    perfil = perfil_funcionario(request.user)
    hoy = timezone.localdate()
    semana = inicio_semana(hoy)
    periodo = Periodo.objects.filter(estado="abierto").first()
    contexto = {"perfil": perfil, "periodo": periodo, "semana_inicio": semana, "semana_fin": fin_semana_laboral(hoy), "pagina_activa": "mi_panel"}
    if grupo == GRUPO_SUPERVISOR:
        actividades = Actividad.objects.select_related("funcionario", "item").prefetch_related("tareas")
        compromisos = Compromiso.objects.filter(activo=True)
        metas = Meta.objects.select_related("item", "periodo", "funcionario", "cargo")
        if perfil is not None:
            actividades = actividades.filter(funcionario__delegacion=perfil.delegacion)
            compromisos = compromisos.filter(delegacion=perfil.delegacion)
            metas = metas.filter(funcionario__delegacion=perfil.delegacion)
        if periodo:
            metas = metas.filter(periodo=periodo)
        pendientes = actividades.filter(estado="pendiente", fecha__gte=semana)
        contexto.update({
            "pendientes": pendientes[:8],
            "total_pendientes": pendientes.count(),
            "listas_para_aprobar": sum(1 for actividad in pendientes if actividad.tareas_completas),
            "aprobadas_semana": actividades.filter(estado="validada", fecha__gte=semana).count(),
            "compromisos_vencidos": compromisos.exclude(estado="realizado").filter(fecha_comprometida__lt=hoy).count(),
            "organizaciones_por_verificar": OrganizacionComunitaria.objects.filter(estado="sin_verificar").count(),
            "cartas_abiertas": acotar_ambito(Carta.objects.exclude(estado__in=("respondida", "archivada")), request.user, "delegacion").count(),
            "beneficios_por_entregar": acotar_ambito(BeneficioNino.objects.filter(estado="registrado"), request.user, "delegacion").count(),
            "ausencias_vigentes": acotar_ambito(Ausencia.objects.filter(estado="vigente", fecha_termino__gte=hoy), request.user, "funcionario__delegacion").select_related("funcionario")[:5],
            "metas": [{"meta": meta, "cumplimiento": meta.cumplimiento, "semaforo": meta.semaforo()} for meta in metas],
        })
        return render(request, "institucional/dashboard_supervisor.html", contexto)
    actividades = Actividad.objects.none()
    metas = Meta.objects.none()
    if perfil is not None:
        actividades = Actividad.objects.filter(funcionario=perfil).select_related("item").prefetch_related("tareas")
        metas = Meta.objects.filter(funcionario=perfil).select_related("item", "periodo")
        if periodo:
            metas = metas.filter(periodo=periodo)
    filas = [{"meta": meta, "cumplimiento": meta.cumplimiento, "semaforo": meta.semaforo()} for meta in metas]
    total_ponderado = sum(float(fila["meta"].ponderador) * fila["cumplimiento"] / 100 for fila in filas)
    contexto.update({
        "hoy_registradas": actividades.filter(fecha=hoy).exclude(estado="anulada").count(),
        "maximo_diario": MAXIMO_ACTIVIDADES_POR_DIA,
        "semana": actividades.filter(fecha__gte=semana).exclude(estado="anulada"),
        "pendientes_aprobacion": actividades.filter(estado="pendiente", fecha__gte=semana).count(),
        "metas": filas,
        "cumplimiento_total": min(total_ponderado, float(periodo.tope_cumplimiento)) if periodo else 0,
        "cartas_derivadas": Carta.objects.filter(derivada_a=perfil).exclude(estado__in=("respondida", "archivada")).order_by("plazo_respuesta")[:5] if perfil else [],
        "mis_ausencias": Ausencia.objects.filter(funcionario=perfil, estado="vigente").order_by("-fecha_inicio")[:3] if perfil else [],
    })
    return render(request, "institucional/dashboard_administrativo.html", contexto)


@solo_administracion
def panel(request):
    """Dashboard del Administrador: vista global, mantenedores y transacciones."""
    base = settings.PHPMYADMIN_URL
    db = settings.PHPMYADMIN_DB
    hoy = timezone.localdate()
    semana = inicio_semana(hoy)
    usuarios_por_grupo = dict(Group.objects.filter(name__in=GRUPOS_SGR).annotate(total=Count("user")).values_list("name", "total"))
    organizaciones = dict(OrganizacionComunitaria.objects.values_list("estado").annotate(total=Count("id")))
    cartas = dict(Carta.objects.values_list("estado").annotate(total=Count("id")))
    beneficios = dict(BeneficioNino.objects.values_list("estado").annotate(total=Count("id")))
    actividades = dict(Actividad.objects.filter(fecha__gte=semana).values_list("estado").annotate(total=Count("id")))
    contexto = {
        "usuarios_por_grupo": [(nombre, usuarios_por_grupo.get(nombre, 0)) for nombre in GRUPOS_SGR],
        "total_usuarios": User.objects.filter(is_active=True).count(),
        "organizaciones": [(etiqueta, organizaciones.get(codigo, 0)) for codigo, etiqueta in OrganizacionComunitaria.ESTADOS],
        "total_organizaciones": sum(organizaciones.values()),
        "cartas": [(etiqueta, cartas.get(codigo, 0)) for codigo, etiqueta in Carta.ESTADOS],
        "total_cartas": sum(cartas.values()),
        "beneficios": [(etiqueta, beneficios.get(codigo, 0)) for codigo, etiqueta in BeneficioNino.ESTADOS],
        "total_beneficios": sum(beneficios.values()),
        "ausencias_vigentes": Ausencia.objects.filter(estado="vigente").count(),
        "actividades_semana": [(etiqueta, actividades.get(codigo, 0)) for codigo, etiqueta in Actividad.ESTADOS],
        "semana_inicio": semana,
        "semana_fin": fin_semana_laboral(hoy),
        "auditoria": Auditoria.objects.select_related("usuario")[:8],
        "delegaciones": Delegacion.objects.filter(activa=True).annotate(total_funcionarios=Count("funcionarios", filter=Q(funcionarios__activo=True))),
        "base_datos": db,
        "usa_mysql": settings.DATABASES["default"]["ENGINE"].endswith("mysql"),
        "phpmyadmin_bd": _url_phpmyadmin(base, db, "/database/structure"),
        "pagina_activa": "panel",
    }
    return render(request, "institucional/panel.html", contexto)


@solo_administracion
def cuentas(request):
    return redirect("institucional:usuarios")


@solo_administracion
def usuarios(request):
    queryset = User.objects.prefetch_related("groups").select_related("perfil_sgr", "perfil_sgr__delegacion").order_by("username")
    busqueda = texto_busqueda(request)
    grupos = list(Group.objects.order_by("name").values_list("name", flat=True))
    grupo = parametro_permitido(request, "grupo", grupos)
    if busqueda:
        queryset = queryset.filter(Q(username__icontains=busqueda) | Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda) | Q(email__icontains=busqueda))
    if grupo:
        queryset = queryset.filter(groups__name=grupo)
    pagina = Paginator(queryset, USUARIOS_POR_PAGINA).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return render(request, "institucional/usuarios/listado.html", {
        "pagina": pagina, "busqueda": busqueda, "grupos": grupos, "grupo_activo": grupo,
        "parametros": parametros.urlencode(), "pagina_activa": "usuarios",
    })


@solo_administracion
def usuario_crear(request):
    form = UsuarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        messages.success(request, f"Cuenta {usuario.username} creada en el grupo {form.cleaned_data['grupo'].name}.")
        return redirect("institucional:usuarios")
    return render(request, "institucional/usuarios/formulario.html", {
        "form": form, "titulo": "Crear usuario", "hay_parametros": Delegacion.objects.exists() and Cargo.objects.exists(), "pagina_activa": "usuarios",
    })


@solo_administracion
def usuario_editar(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    form = UsuarioForm(request.POST or None, usuario=usuario)
    form.solicitante = request.user
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Cuenta {usuario.username} actualizada.")
        return redirect("institucional:usuarios")
    return render(request, "institucional/usuarios/formulario.html", {
        "form": form, "cuenta": usuario, "titulo": f"Editar usuario {usuario.username}", "hay_parametros": True, "pagina_activa": "usuarios",
    })


@solo_administracion
def usuario_eliminar(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if usuario == request.user:
        messages.warning(request, "No puedes eliminar tu propia cuenta.")
        return redirect("institucional:usuarios")
    if request.method == "POST":
        try:
            usuario.delete()
        except ProtectedError:
            usuario.is_active = False
            usuario.save(update_fields=["is_active"])
            messages.warning(request, f"{usuario.username} tiene registros asociados (auditoría, evidencias): se desactivó en lugar de eliminarse.")
        else:
            messages.success(request, f"Cuenta {usuario.username} eliminada.")
        return redirect("institucional:usuarios")
    return render(request, "institucional/usuarios/eliminar.html", {"cuenta": usuario, "pagina_activa": "usuarios"})


@solo_administracion
def grupos(request):
    busqueda = texto_busqueda(request)
    queryset = Group.objects.annotate(total_usuarios=Count("user", distinct=True), total_permisos=Count("permissions", distinct=True)).order_by("name")
    if busqueda:
        queryset = queryset.filter(name__icontains=busqueda)
    return render(request, "institucional/grupos/listado.html", {"grupos": queryset, "busqueda": busqueda, "base": GRUPOS_SGR, "pagina_activa": "grupos"})


@solo_administracion
def grupo_crear(request):
    form = GrupoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        grupo = form.save()
        messages.success(request, f"Grupo {grupo.name} creado.")
        return redirect("institucional:grupos")
    return render(request, "institucional/grupos/formulario.html", {"form": form, "titulo": "Crear grupo", "pagina_activa": "grupos"})


@solo_administracion
def grupo_editar(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    form = GrupoForm(request.POST or None, instance=grupo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Grupo {grupo.name} actualizado.")
        return redirect("institucional:grupos")
    return render(request, "institucional/grupos/formulario.html", {
        "form": form, "grupo": grupo, "titulo": f"Editar grupo {grupo.name}",
        "miembros": grupo.user_set.order_by("username"), "pagina_activa": "grupos",
    })


@solo_administracion
def grupo_eliminar(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    if grupo.name in GRUPOS_SGR:
        messages.warning(request, f"{grupo.name} es uno de los tres perfiles base del SGR y no se elimina.")
        return redirect("institucional:grupos")
    if request.method == "POST":
        nombre = grupo.name
        grupo.delete()
        messages.success(request, f"Grupo {nombre} eliminado.")
        return redirect("institucional:grupos")
    return render(request, "institucional/grupos/eliminar.html", {"grupo": grupo, "pagina_activa": "grupos"})


def verificar_acceso(request):
    """Subconsulta de Nginx (auth_request) que protege la ruta de phpMyAdmin."""
    return HttpResponse(status=204 if es_administracion(request.user) else 401)


def acceso_denegado(request, exception=None):
    return render(request, "institucional/denegado.html", status=403)
