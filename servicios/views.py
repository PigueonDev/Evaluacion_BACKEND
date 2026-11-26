from datetime import datetime, timedelta
from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from institucional.models import Cargo, Delegacion, Funcionario
from laserena.filtros import parametro_permitido, texto_busqueda
from laserena.permisos import (
    acotar_ambito,
    con_permiso,
    es_administrador,
    perfil_de_ambito,
    perfil_funcionario,
    solo_administrador,
    solo_administrativo,
    solo_personal,
    solo_supervisor,
)

from .desempeno import resumen_equipo
from .forms import ActividadForm, CasoForm, CompromisoForm, EvidenciaForm, GestionForm, RevisionEvidenciaForm, RevisionForm, TareaFormSet
from .models import CODIGO_VERIFICADOR, DIAS_COMPROMISO_PROXIMO, MAXIMO_GESTIONES_POR_CASO, Actividad, Caso, Compromiso, Evidencia, Gestion, HistorialCompromiso, ItemMedicion, Meta, Periodo, Servicio, TareaPreparatoria
from .reglas import MAXIMO_ACTIVIDADES_POR_DIA, fin_semana_laboral, inicio_semana, semana_abierta
from .transacciones import actualizar_actividad, cargar_evidencia, marcar_tarea, registrar_actividad, revisar_actividad, revisar_evidencia, tareas_desde_formset


def catalogo(request):
    categorias = list(Servicio.objects.filter(activo=True).values_list("categoria", flat=True).distinct().order_by("categoria"))
    categoria = parametro_permitido(request, "categoria", categorias) or "todos"
    busqueda = texto_busqueda(request)
    servicios = Servicio.objects.filter(activo=True)
    if categoria != "todos":
        servicios = servicios.filter(categoria=categoria)
    if busqueda:
        servicios = servicios.filter(Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda) | Q(unidad__icontains=busqueda))
    contexto = {
        "introduccion": {"titulo": "Servicios y gestión territorial", "bajada": "Catálogo administrable de servicios municipales."},
        "servicios": servicios,
        "categorias": ["todos", *categorias],
        "categoria_activa": categoria,
        "busqueda": busqueda,
        "total": servicios.count(),
        "total_general": Servicio.objects.filter(activo=True).count(),
        "pagina_activa": "servicios",
    }
    return render(request, "servicios/catalogo.html", contexto)


def detalle(request, slug: str):
    servicio = get_object_or_404(Servicio, slug=slug, activo=True)
    relacionados = Servicio.objects.filter(categoria=servicio.categoria, activo=True).exclude(pk=servicio.pk)[:3]
    return render(request, "servicios/detalle.html", {"servicio": servicio, "relacionados": relacionados, "pagina_activa": "servicios"})


def _delegacion_usuario(user):
    perfil = perfil_de_ambito(user)
    return perfil.delegacion if perfil else None


def _actividades_ambito(user):
    queryset = Actividad.objects.select_related("funcionario", "funcionario__delegacion", "funcionario__cargo", "item", "periodo", "compromiso")
    return acotar_ambito(queryset, user, "funcionario__delegacion")


def _evidencias_ambito(user):
    queryset = Evidencia.objects.select_related(
        "actividad", "actividad__funcionario", "actividad__funcionario__delegacion", "actividad__item", "tarea", "autor",
    )
    return acotar_ambito(queryset, user, "actividad__funcionario__delegacion")


def _puede_cargar_evidencia(user, actividad):
    """El funcionario adjunta la captura de su propia actividad. El Administrador, de cualquiera."""
    if not user.has_perm("servicios.add_evidencia") or actividad.estado == "anulada":
        return False
    if es_administrador(user):
        return True
    perfil = perfil_funcionario(user)
    return perfil is not None and actividad.funcionario_id == perfil.pk


def _compromisos_ambito(user, solo_activos=True):
    queryset = Compromiso.objects.select_related("responsable", "delegacion")
    if solo_activos:
        queryset = queryset.filter(activo=True)
    return acotar_ambito(queryset, user, "delegacion")


def _casos_ambito(user):
    queryset = Caso.objects.select_related("delegacion")
    return acotar_ambito(queryset, user, "delegacion")


def _funcionarios_ambito(user):
    queryset = Funcionario.objects.filter(activo=True).select_related("delegacion", "cargo")
    return acotar_ambito(queryset, user, "delegacion")


def _fecha_get(request, nombre):
    valor = request.GET.get(nombre, "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def _contexto_semana(funcionario):
    hoy = timezone.localdate()
    hoy_registradas = 0
    if funcionario is not None:
        hoy_registradas = Actividad.objects.filter(funcionario=funcionario, fecha=hoy).exclude(estado="anulada").count()
    return {
        "semana_inicio": inicio_semana(hoy),
        "semana_fin": fin_semana_laboral(hoy),
        "semana_abierta_hoy": hoy.weekday() < 5,
        "hoy_registradas": hoy_registradas,
        "maximo_diario": MAXIMO_ACTIVIDADES_POR_DIA,
    }


@solo_administrador
def panel_municipal(request):
    actividades = _actividades_ambito(request.user)
    compromisos = _compromisos_ambito(request.user)
    periodo = Periodo.objects.filter(estado="abierto").first()
    metas = Meta.objects.select_related("item", "periodo", "funcionario", "cargo")
    if periodo:
        metas = metas.filter(periodo=periodo)
    perfil = perfil_de_ambito(request.user)
    if perfil is not None:
        metas = metas.filter(Q(funcionario__delegacion=perfil.delegacion) | Q(funcionario__isnull=True, cargo=perfil.cargo))
    delegaciones = Delegacion.objects.filter(activa=True)
    funcionarios = Funcionario.objects.filter(activo=True)
    if perfil is not None:
        delegaciones = delegaciones.filter(pk=perfil.delegacion_id)
        funcionarios = funcionarios.filter(delegacion=perfil.delegacion)
    contexto = {
        "periodo": periodo,
        "delegaciones": delegaciones.annotate(total_compromisos=Count("compromisos", filter=Q(compromisos__activo=True))),
        "total_funcionarios": funcionarios.count(),
        "total_actividades": actividades.count(),
        "actividades_validadas": actividades.filter(estado="validada").count(),
        "compromisos_pendientes": compromisos.exclude(estado="realizado").count(),
        "actividades_recientes": actividades[:8],
        "compromisos_recientes": compromisos[:8],
        "metas": [{"meta": meta, "cumplimiento": meta.cumplimiento, "semaforo": meta.semaforo()} for meta in metas],
        "pagina_activa": "panel_municipal",
    }
    return render(request, "servicios/panel_municipal.html", contexto)


@solo_administrativo
def actividades(request):
    queryset = _actividades_ambito(request.user)
    estado = parametro_permitido(request, "estado", dict(Actividad.ESTADOS))
    busqueda = texto_busqueda(request)
    if estado:
        queryset = queryset.filter(estado=estado)
    if busqueda:
        queryset = queryset.filter(Q(descripcion__icontains=busqueda) | Q(solicitante__icontains=busqueda) | Q(funcionario__nombre_completo__icontains=busqueda) | Q(item__nombre__icontains=busqueda))
    contexto = {"actividades": queryset, "estado_activo": estado, "busqueda": busqueda, "pagina_activa": "actividades"}
    return render(request, "servicios/actividades.html", contexto)


@solo_administrativo
def actividad_nueva(request):
    perfil = perfil_funcionario(request.user)
    if request.method == "POST":
        form = ActividadForm(request.POST, funcionario=perfil)
        formset = TareaFormSet(request.POST, prefix="tareas")
        if form.is_valid() and formset.is_valid():
            funcionario = perfil or form.cleaned_data.get("funcionario")
            try:
                actividad = registrar_actividad(form.save(commit=False), tareas_desde_formset(formset), funcionario, request.user)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"Actividad registrada con {actividad.tareas.count()} tareas preparatorias. Identificador: {actividad.codigo_evidencia}")
                return redirect("servicios:actividad_detalle", pk=actividad.pk)
    else:
        form = ActividadForm(funcionario=perfil, initial={"fecha": timezone.localdate()})
        formset = TareaFormSet(prefix="tareas")
    contexto = {
        "form": form,
        "formset": formset,
        "titulo": "Registrar actividad",
        "hay_periodo_abierto": Periodo.objects.filter(estado="abierto").exists(),
        "pagina_activa": "actividades",
        **_contexto_semana(perfil),
    }
    return render(request, "servicios/actividad_formulario.html", contexto)


@solo_administrativo
def actividad_detalle(request, pk):
    actividad = get_object_or_404(_actividades_ambito(request.user).prefetch_related("tareas", "evidencias"), pk=pk)
    puede_cargar = _puede_cargar_evidencia(request.user, actividad)
    if request.method == "POST":
        if not puede_cargar:
            return render(request, "institucional/denegado.html", status=403)
        formulario = EvidenciaForm(request.POST, request.FILES, actividad=actividad)
        if formulario.is_valid():
            try:
                cargar_evidencia(actividad, formulario.cleaned_data["tarea"], formulario.cleaned_data["archivo"], request.user)
            except ValidationError as error:
                formulario.add_error(None, error)
            else:
                messages.success(request, "Captura enviada. Queda pendiente de revisión del delegado.")
                return redirect("servicios:actividad_detalle", pk=actividad.pk)
    else:
        formulario = EvidenciaForm(actividad=actividad) if puede_cargar else None
    return render(
        request,
        "servicios/actividad_detalle.html",
        {
            "actividad": actividad,
            "tareas": actividad.tareas.all(),
            "evidencias": actividad.evidencias.all(),
            "formulario_evidencia": formulario,
            "editable": actividad.estado == "pendiente" and semana_abierta(actividad.fecha),
            "pagina_activa": "actividades",
        },
    )


@solo_administrativo
def actividad_editar(request, pk):
    actividad = get_object_or_404(_actividades_ambito(request.user), pk=pk)
    if actividad.estado == "anulada":
        messages.warning(request, "La actividad está anulada. El código se conserva y no se reutiliza.")
        return redirect("servicios:actividad_detalle", pk=actividad.pk)
    if actividad.periodo.estado != "abierto":
        messages.warning(request, "El período está cerrado. La actividad se puede consultar, no modificar.")
        return redirect("servicios:actividad_detalle", pk=actividad.pk)
    if actividad.estado != "pendiente" or not semana_abierta(actividad.fecha):
        messages.warning(request, "La actividad ya fue revisada o su semana laboral cerró: queda bloqueada.")
        return redirect("servicios:actividad_detalle", pk=actividad.pk)
    if request.method == "POST":
        form = ActividadForm(request.POST, instance=actividad, funcionario=actividad.funcionario)
        if form.is_valid():
            try:
                actividad = actualizar_actividad(form.save(commit=False), request.user)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Actividad actualizada. El identificador no cambió.")
                return redirect("servicios:actividad_detalle", pk=actividad.pk)
    else:
        form = ActividadForm(instance=actividad, funcionario=actividad.funcionario)
    return render(
        request,
        "servicios/actividad_formulario.html",
        {"form": form, "actividad": actividad, "titulo": "Editar actividad", "hay_periodo_abierto": True, "pagina_activa": "actividades"},
    )


@solo_administrativo
@require_POST
def actividad_anular(request, pk):
    actividad = get_object_or_404(_actividades_ambito(request.user), pk=pk)
    if actividad.periodo.estado != "abierto":
        messages.warning(request, "No se modifica una actividad de un período cerrado.")
    elif not semana_abierta(actividad.fecha):
        messages.warning(request, "La semana laboral de esta actividad ya cerró: queda bloqueada.")
    elif actividad.estado == "validada":
        messages.warning(request, "Una actividad aprobada no se anula.")
    elif actividad.estado != "anulada":
        actividad.estado = "anulada"
        actividad.save(update_fields=["estado"])
        messages.success(request, f"Actividad anulada. El código {actividad.codigo_evidencia} queda reservado y no se reutiliza.")
    return redirect("servicios:actividad_detalle", pk=actividad.pk)


@solo_administrativo
@require_POST
def tarea_marcar(request, pk, tarea_pk):
    actividad = get_object_or_404(_actividades_ambito(request.user), pk=pk)
    tarea = get_object_or_404(TareaPreparatoria, pk=tarea_pk, actividad=actividad)
    try:
        marcar_tarea(tarea, request.POST.get("realizada") == "1", request.user)
    except ValidationError as error:
        messages.warning(request, " ".join(error.messages))
    else:
        messages.success(request, f"Tarea «{tarea}» {'realizada' if tarea.realizada else 'marcada como pendiente'}. Las tareas no suman al cumplimiento.")
    return redirect("servicios:actividad_detalle", pk=actividad.pk)


@con_permiso("servicios.aprobar_evidencia")
def evidencias(request):
    queryset = _evidencias_ambito(request.user)
    estado = parametro_permitido(request, "estado", [*dict(Evidencia.ESTADOS), "todas"]) or "pendiente"
    if estado != "todas":
        queryset = queryset.filter(estado=estado)
    return render(
        request,
        "servicios/evidencias.html",
        {
            "evidencias": queryset,
            "estado_activo": estado,
            "estados": Evidencia.ESTADOS,
            "pagina_activa": "evidencias",
        },
    )


@con_permiso("servicios.aprobar_evidencia")
@require_POST
def evidencia_revisar(request, pk):
    evidencia = get_object_or_404(_evidencias_ambito(request.user), pk=pk)
    form = RevisionEvidenciaForm(request.POST)
    if not form.is_valid():
        if request.POST.get("decision") == "rechazar":
            messages.warning(request, "Indica un motivo breve para rechazar la evidencia.")
        else:
            messages.warning(request, "Decisión no válida.")
        return redirect("servicios:evidencias")
    try:
        revisar_evidencia(evidencia, form.cleaned_data["decision"], request.user, form.cleaned_data["motivo"])
    except ValidationError as error:
        messages.warning(request, " ".join(error.messages))
    else:
        if form.cleaned_data["decision"] == "aprobar":
            messages.success(request, "Evidencia aprobada.")
        else:
            messages.success(request, "Evidencia rechazada. El funcionario verá el motivo.")
    return redirect("servicios:evidencias")


@solo_supervisor
def aprobaciones(request):
    base = _actividades_ambito(request.user).prefetch_related("tareas")
    hoy = timezone.localdate()
    pendientes = [a for a in base.filter(estado="pendiente", fecha__gte=inicio_semana(hoy))]
    revisadas = base.filter(estado__in=["validada", "rechazada"], fecha__gte=inicio_semana(hoy))
    contexto = {
        "pendientes": pendientes,
        "revisadas": revisadas[:20],
        "semana_inicio": inicio_semana(hoy),
        "semana_fin": fin_semana_laboral(hoy),
        "form": RevisionForm(),
        "pagina_activa": "aprobaciones",
    }
    return render(request, "servicios/aprobaciones.html", contexto)


@solo_supervisor
@require_POST
def actividad_revisar(request, pk):
    actividad = get_object_or_404(_actividades_ambito(request.user), pk=pk)
    if not request.user.has_perm("servicios.aprobar_actividad"):
        return render(request, "institucional/denegado.html", status=403)
    form = RevisionForm(request.POST)
    if not form.is_valid():
        messages.warning(request, "Decisión no válida.")
        return redirect("servicios:aprobaciones")
    try:
        revisar_actividad(actividad, form.cleaned_data["decision"], request.user, form.cleaned_data["observacion"])
    except ValidationError as error:
        messages.warning(request, " ".join(error.messages))
    else:
        if form.cleaned_data["decision"] == "aprobar":
            messages.success(request, f"Actividad de {actividad.funcionario.nombre_completo} aprobada: ya suma a su cumplimiento.")
        else:
            messages.success(request, "Actividad rechazada. No suma al cumplimiento.")
    return redirect("servicios:aprobaciones")


@solo_administrativo
def actividad_por_codigo(request):
    codigo = request.GET.get("codigo", "").strip()
    actividad = None
    aviso = ""
    if codigo:
        filtro = None
        try:
            filtro = {"codigo_evidencia": UUID(codigo)}
        except ValueError:
            if CODIGO_VERIFICADOR.match(codigo.upper()):
                filtro = {"codigo_verificador": codigo.upper()}
        if filtro is None:
            aviso = "El código no tiene el formato de un identificador válido."
        else:
            actividad = _actividades_ambito(request.user).filter(**filtro).first()
            if actividad is None:
                aviso = "No hay una actividad con ese código en tu ámbito."
    return render(
        request,
        "servicios/actividad_codigo.html",
        {"codigo": codigo, "actividad": actividad, "aviso": aviso, "pagina_activa": "actividades"},
    )


@solo_administrativo
def casos(request):
    queryset = _casos_ambito(request.user)
    busqueda = texto_busqueda(request)
    if busqueda:
        queryset = queryset.filter(Q(identificacion__icontains=busqueda) | Q(nombre__icontains=busqueda) | Q(solicitante__icontains=busqueda))
    return render(
        request,
        "servicios/casos.html",
        {"casos": queryset, "busqueda": busqueda, "pagina_activa": "casos"},
    )


@solo_administrativo
def caso_nuevo(request):
    delegacion = _delegacion_usuario(request.user)
    if request.method == "POST":
        form = CasoForm(request.POST, delegacion=delegacion)
        if form.is_valid():
            caso = form.save()
            messages.success(request, f"Caso {caso.identificacion} registrado. La identificación principal no se duplica en las gestiones.")
            return redirect("servicios:caso_detalle", pk=caso.pk)
    else:
        form = CasoForm(delegacion=delegacion)
    return render(request, "servicios/caso_formulario.html", {"form": form, "titulo": "Registrar caso", "pagina_activa": "casos"})


@solo_administrativo
def caso_detalle(request, pk):
    caso = get_object_or_404(_casos_ambito(request.user).prefetch_related("gestiones__actividad"), pk=pk)
    return render(
        request,
        "servicios/caso_detalle.html",
        {
            "caso": caso,
            "gestiones": caso.gestiones.all(),
            "cupo_disponible": caso.gestiones.count() < MAXIMO_GESTIONES_POR_CASO,
            "atenciones": caso.atenciones_contadas(),
            "pagina_activa": "casos",
        },
    )


@solo_administrativo
def caso_editar(request, pk):
    caso = get_object_or_404(_casos_ambito(request.user), pk=pk)
    delegacion = _delegacion_usuario(request.user) or caso.delegacion
    if request.method == "POST":
        form = CasoForm(request.POST, instance=caso, delegacion=delegacion if perfil_funcionario(request.user) else None)
        if form.is_valid():
            caso = form.save()
            messages.success(request, "Caso actualizado. La identificación principal sigue siendo única.")
            return redirect("servicios:caso_detalle", pk=caso.pk)
    else:
        form = CasoForm(instance=caso, delegacion=delegacion if perfil_funcionario(request.user) else None)
    return render(request, "servicios/caso_formulario.html", {"form": form, "caso": caso, "titulo": "Editar caso", "pagina_activa": "casos"})


@solo_administrativo
@require_POST
def caso_desactivar(request, pk):
    caso = get_object_or_404(_casos_ambito(request.user), pk=pk)
    caso.activo = not caso.activo
    caso.save(update_fields=["activo"])
    messages.success(request, "Caso desactivado." if not caso.activo else "Caso activado.")
    return redirect("servicios:caso_detalle", pk=caso.pk)


@solo_administrativo
def gestion_nueva(request, pk):
    caso = get_object_or_404(_casos_ambito(request.user), pk=pk)
    if caso.gestiones.count() >= MAXIMO_GESTIONES_POR_CASO:
        messages.warning(request, "Este caso ya tiene las tres gestiones permitidas.")
        return redirect("servicios:caso_detalle", pk=caso.pk)
    if request.method == "POST":
        form = GestionForm(request.POST, caso=caso)
        if form.is_valid():
            gestion = form.save()
            messages.success(request, f"Gestión {gestion.numero} asociada al caso {caso.identificacion}.")
            return redirect("servicios:caso_detalle", pk=caso.pk)
    else:
        form = GestionForm(caso=caso, initial={"fecha": timezone.localdate()})
    return render(
        request,
        "servicios/gestion_formulario.html",
        {"form": form, "caso": caso, "titulo": "Registrar gestión", "pagina_activa": "casos"},
    )


@solo_administrativo
def gestion_editar(request, caso_pk, pk):
    caso = get_object_or_404(_casos_ambito(request.user), pk=caso_pk)
    gestion = get_object_or_404(caso.gestiones, pk=pk)
    if request.method == "POST":
        form = GestionForm(request.POST, instance=gestion, caso=caso)
        if form.is_valid():
            form.save()
            messages.success(request, "Gestión actualizada.")
            return redirect("servicios:caso_detalle", pk=caso.pk)
    else:
        form = GestionForm(instance=gestion, caso=caso)
    return render(
        request,
        "servicios/gestion_formulario.html",
        {"form": form, "caso": caso, "gestion": gestion, "titulo": "Editar gestión", "pagina_activa": "casos"},
    )


@solo_administrativo
@require_POST
def gestion_desactivar(request, caso_pk, pk):
    caso = get_object_or_404(_casos_ambito(request.user), pk=caso_pk)
    gestion = get_object_or_404(caso.gestiones, pk=pk)
    gestion.activa = not gestion.activa
    gestion.save(update_fields=["activa"])
    messages.success(request, "Gestión desactivada. Sigue ocupando su cupo y no se vuelve a contar." if not gestion.activa else "Gestión activada.")
    return redirect("servicios:caso_detalle", pk=caso.pk)


@solo_administrativo
def agenda(request):
    compromisos = _compromisos_ambito(request.user).order_by("fecha_comprometida", "creado_en")
    responsables = _funcionarios_ambito(request.user).order_by("nombre_completo")
    ids = [str(funcionario.pk) for funcionario in responsables]
    responsable = parametro_permitido(request, "responsable", ids)
    estado = parametro_permitido(request, "estado", dict(Compromiso.ESTADOS))
    busqueda = texto_busqueda(request)
    if responsable:
        compromisos = compromisos.filter(responsable_id=responsable)
    if estado:
        compromisos = compromisos.filter(estado=estado)
    if busqueda:
        compromisos = compromisos.filter(Q(descripcion__icontains=busqueda) | Q(solicitante__icontains=busqueda) | Q(delegacion__nombre__icontains=busqueda))
    compromisos = compromisos.order_by("fecha_comprometida", "creado_en")
    contexto = {
        "compromisos": compromisos,
        "responsables": responsables,
        "estado_activo": estado,
        "responsable_activo": responsable,
        "busqueda": busqueda,
        "pagina_activa": "agenda",
    }
    return render(request, "servicios/agenda.html", contexto)


def _publicar_compromiso(form, usuario):
    compromiso = form.save(commit=False)
    compromiso.estado = "ingresado"
    compromiso.activo = True
    compromiso.full_clean()
    compromiso.save()
    HistorialCompromiso.objects.create(
        compromiso=compromiso,
        estado_anterior="",
        estado_nuevo="ingresado",
        autor=usuario,
        observacion="Compromiso publicado en el ámbito autorizado.",
    )
    return compromiso


@solo_administrativo
def compromiso_nuevo(request):
    delegacion = _delegacion_usuario(request.user)
    if request.method == "POST":
        form = CompromisoForm(request.POST, delegacion=delegacion)
        if form.is_valid():
            try:
                with transaction.atomic():
                    compromiso = _publicar_compromiso(form, request.user)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Compromiso publicado en la agenda de la delegación autorizada.")
                return redirect("servicios:compromiso_detalle", pk=compromiso.pk)
    else:
        form = CompromisoForm(delegacion=delegacion)
    return render(
        request,
        "servicios/compromiso_formulario.html",
        {"form": form, "titulo": "Publicar compromiso", "pagina_activa": "agenda"},
    )


@solo_personal
def compromiso_detalle(request, pk):
    compromiso = get_object_or_404(_compromisos_ambito(request.user, solo_activos=False).prefetch_related("historial__autor"), pk=pk)
    return render(
        request,
        "servicios/compromiso_detalle.html",
        {"compromiso": compromiso, "historial": compromiso.historial.all(), "pagina_activa": "agenda"},
    )


@solo_administrativo
def compromiso_editar(request, pk):
    compromiso = get_object_or_404(_compromisos_ambito(request.user, solo_activos=False), pk=pk)
    if not compromiso.activo:
        messages.warning(request, "El compromiso está desactivado. Su historial se conserva.")
        return redirect("servicios:compromiso_detalle", pk=compromiso.pk)
    delegacion = _delegacion_usuario(request.user)
    estado_anterior = compromiso.estado
    if request.method == "POST":
        form = CompromisoForm(request.POST, instance=compromiso, delegacion=delegacion, edicion=True)
        if form.is_valid():
            nuevo_estado = form.cleaned_data["estado"]
            observacion = form.cleaned_data.get("observacion_cambio", "")
            try:
                with transaction.atomic():
                    compromiso = form.save(commit=False)
                    compromiso.estado = estado_anterior
                    compromiso.full_clean()
                    compromiso.save()
                    if nuevo_estado != estado_anterior:
                        compromiso.aplicar_estado(nuevo_estado, request.user, observacion)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if compromiso.estado == "realizado":
                    messages.success(request, "Compromiso actualizado. El cierre quedó como Realizado.")
                else:
                    messages.success(request, "Compromiso actualizado.")
                return redirect("servicios:compromiso_detalle", pk=compromiso.pk)
    else:
        form = CompromisoForm(instance=compromiso, delegacion=delegacion, edicion=True)
    return render(
        request,
        "servicios/compromiso_formulario.html",
        {"form": form, "compromiso": compromiso, "titulo": "Editar compromiso", "pagina_activa": "agenda"},
    )


@solo_administrativo
@require_POST
def compromiso_desactivar(request, pk):
    compromiso = get_object_or_404(_compromisos_ambito(request.user, solo_activos=False), pk=pk)
    compromiso.activo = not compromiso.activo
    compromiso.save(update_fields=["activo"])
    messages.success(request, "Compromiso desactivado. El historial no se borra." if not compromiso.activo else "Compromiso publicado nuevamente.")
    return redirect("servicios:compromiso_detalle", pk=compromiso.pk)


@solo_supervisor
def resumen_matriz(request):
    """Hojas RESUMEN y SEMAFORO de la matriz: cumplimiento ponderado, semáforo y ranking por colaborador."""
    periodos = Periodo.objects.all()
    elegido = parametro_permitido(request, "periodo", {str(pk) for pk in periodos.values_list("pk", flat=True)})
    periodo = periodos.filter(pk=elegido).first() if elegido else (periodos.filter(estado="abierto").first() or periodos.first())
    perfil = perfil_de_ambito(request.user)
    delegaciones = Delegacion.objects.filter(activa=True)
    if perfil is not None:
        delegacion = perfil.delegacion
        delegaciones = delegaciones.filter(pk=delegacion.pk)
    else:
        elegida = parametro_permitido(request, "delegacion", {str(pk) for pk in delegaciones.values_list("pk", flat=True)})
        delegacion = delegaciones.filter(pk=elegida).first() if elegida else None
    funcionarios = Funcionario.objects.filter(activo=True).select_related("cargo", "delegacion")
    if delegacion is not None:
        funcionarios = funcionarios.filter(delegacion=delegacion)
    hoy = timezone.localdate()
    equipo = resumen_equipo(funcionarios, periodo, hoy) if periodo else None
    return render(request, "servicios/resumen_matriz.html", {
        "periodo": periodo,
        "periodos": periodos,
        "delegacion": delegacion,
        "delegaciones": delegaciones,
        "puede_elegir_delegacion": perfil is None,
        "equipo": equipo,
        "esperado": periodo.avance_esperado(hoy) if periodo else 0,
        "pagina_activa": "resumen_matriz",
    })


@solo_supervisor
def resumen_agenda(request):
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=DIAS_COMPROMISO_PROXIMO)
    base = _compromisos_ambito(request.user).prefetch_related("historial")
    pendientes = base.exclude(estado="realizado")
    proximos = pendientes.filter(fecha_comprometida__gte=hoy, fecha_comprometida__lte=limite)
    vencidos = pendientes.filter(fecha_comprometida__lt=hoy).order_by("fecha_comprometida")
    realizados = base.filter(estado="realizado")
    realizados_tarde = [compromiso for compromiso in realizados if compromiso.fuera_de_plazo]
    por_funcionario = (
        base.values("responsable_id", "responsable__nombre_completo")
        .annotate(
            total=Count("id"),
            realizados=Count("id", filter=Q(estado="realizado")),
            pendientes=Count("id", filter=~Q(estado="realizado")),
        )
        .order_by("responsable__nombre_completo")
    )
    filas = []
    for fila in por_funcionario:
        total = fila["total"] or 1
        filas.append({
            **fila,
            "porcentaje_realizado": round(fila["realizados"] * 100 / total, 1),
            "porcentaje_pendiente": round(fila["pendientes"] * 100 / total, 1),
        })
    contexto = {
        "pendientes": pendientes.count(),
        "proximos": proximos,
        "vencidos": vencidos,
        "realizados": realizados.count(),
        "realizados_tarde": realizados_tarde,
        "filas": filas,
        "dias_proximos": DIAS_COMPROMISO_PROXIMO,
        "pagina_activa": "agenda",
    }
    return render(request, "servicios/resumen_agenda.html", contexto)


@solo_supervisor
def consulta(request):
    actividades = _actividades_ambito(request.user)
    perfil = perfil_de_ambito(request.user)
    if perfil is not None:
        delegaciones = Delegacion.objects.filter(pk=perfil.delegacion_id)
    else:
        delegaciones = Delegacion.objects.filter(activa=True)
    funcionarios = _funcionarios_ambito(request.user)
    cargos = Cargo.objects.filter(activo=True, funcionarios__in=funcionarios).distinct()
    periodos = Periodo.objects.all()
    items = ItemMedicion.objects.filter(activo=True)
    delegacion = parametro_permitido(request, "delegacion", [str(item.pk) for item in delegaciones])
    funcionario = parametro_permitido(request, "funcionario", [str(item.pk) for item in funcionarios])
    cargo = parametro_permitido(request, "cargo", [str(item.pk) for item in cargos])
    periodo = parametro_permitido(request, "periodo", [str(item.pk) for item in periodos])
    item = parametro_permitido(request, "item", [str(item_medicion.pk) for item_medicion in items])
    estado = parametro_permitido(request, "estado", dict(Actividad.ESTADOS))
    desde = _fecha_get(request, "desde")
    hasta = _fecha_get(request, "hasta")
    busqueda = texto_busqueda(request)
    if delegacion:
        actividades = actividades.filter(funcionario__delegacion_id=delegacion)
    if funcionario:
        actividades = actividades.filter(funcionario_id=funcionario)
    if cargo:
        actividades = actividades.filter(funcionario__cargo_id=cargo)
    if periodo:
        actividades = actividades.filter(periodo_id=periodo)
    if item:
        actividades = actividades.filter(item_id=item)
    if estado:
        actividades = actividades.filter(estado=estado)
    if desde:
        actividades = actividades.filter(fecha__gte=desde)
    if hasta:
        actividades = actividades.filter(fecha__lte=hasta)
    if busqueda:
        actividades = actividades.filter(
            Q(descripcion__icontains=busqueda) | Q(solicitante__icontains=busqueda) | Q(accion__icontains=busqueda) | Q(funcionario__nombre_completo__icontains=busqueda)
            | Q(codigo_verificador__iexact=busqueda.replace(" ", ""))
        )
    contexto = {
        "actividades": actividades,
        "delegaciones": delegaciones,
        "funcionarios": funcionarios,
        "cargos": cargos,
        "periodos": periodos,
        "items": items,
        "estados": Actividad.ESTADOS,
        "delegacion_activa": delegacion,
        "funcionario_activo": funcionario,
        "cargo_activo": cargo,
        "periodo_activo": periodo,
        "item_activo": item,
        "estado_activo": estado,
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "busqueda": busqueda,
        "consulta_query": request.GET.urlencode(),
        "total": actividades.count(),
        "pagina_activa": "consulta",
    }
    return render(request, "servicios/consulta.html", contexto)


@solo_supervisor
def consulta_actividad(request, pk):
    actividad = get_object_or_404(_actividades_ambito(request.user).prefetch_related("evidencias"), pk=pk)
    return render(
        request,
        "servicios/consulta_detalle.html",
        {
            "actividad": actividad,
            "evidencias": actividad.evidencias.all(),
            "consulta_query": request.GET.urlencode(),
            "pagina_activa": "consulta",
        },
    )
