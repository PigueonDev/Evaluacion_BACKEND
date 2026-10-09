from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from institucional.models import Delegacion, Funcionario
from laserena.permisos import parametro_permitido, solo_personal, texto_busqueda

from .models import Actividad, Compromiso, Meta, Periodo, Servicio


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


@solo_personal
def dashboard(request):
    actividades = Actividad.objects.select_related("funcionario", "item", "periodo")
    compromisos = Compromiso.objects.select_related("responsable", "delegacion")
    periodo = Periodo.objects.filter(estado="abierto").first()
    metas = Meta.objects.select_related("item", "periodo", "funcionario", "cargo")
    if periodo:
        metas = metas.filter(periodo=periodo)
    contexto = {
        "periodo": periodo,
        "delegaciones": Delegacion.objects.filter(activa=True).annotate(total_compromisos=Count("compromisos")),
        "total_funcionarios": Funcionario.objects.filter(activo=True).count(),
        "total_actividades": actividades.count(),
        "actividades_validadas": actividades.filter(estado="validada").count(),
        "compromisos_pendientes": compromisos.exclude(estado="realizado").count(),
        "actividades_recientes": actividades[:8],
        "compromisos_recientes": compromisos[:8],
        "metas": [{"meta": meta, "cumplimiento": meta.cumplimiento, "semaforo": meta.semaforo()} for meta in metas],
        "pagina_activa": "dashboard",
    }
    return render(request, "servicios/dashboard.html", contexto)


@solo_personal
def actividades(request):
    queryset = Actividad.objects.select_related("funcionario", "item", "periodo")
    estado = parametro_permitido(request, "estado", dict(Actividad.ESTADOS))
    busqueda = texto_busqueda(request)
    if estado:
        queryset = queryset.filter(estado=estado)
    if busqueda:
        queryset = queryset.filter(Q(descripcion__icontains=busqueda) | Q(funcionario__nombre_completo__icontains=busqueda) | Q(item__nombre__icontains=busqueda))
    contexto = {"actividades": queryset, "estado_activo": estado, "busqueda": busqueda, "pagina_activa": "actividades"}
    return render(request, "servicios/actividades.html", contexto)


@solo_personal
def agenda(request):
    compromisos = Compromiso.objects.select_related("responsable", "delegacion")
    estado = parametro_permitido(request, "estado", dict(Compromiso.ESTADOS))
    busqueda = texto_busqueda(request)
    if estado:
        compromisos = compromisos.filter(estado=estado)
    if busqueda:
        compromisos = compromisos.filter(Q(descripcion__icontains=busqueda) | Q(solicitante__icontains=busqueda) | Q(delegacion__nombre__icontains=busqueda))
    contexto = {"compromisos": compromisos, "estado_activo": estado, "busqueda": busqueda, "pagina_activa": "agenda"}
    return render(request, "servicios/agenda.html", contexto)
