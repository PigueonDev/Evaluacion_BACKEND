from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from institucional.models import Delegacion, Funcionario

from .models import Actividad, Compromiso, Periodo, Servicio


def catalogo(request):
    categoria = request.GET.get("categoria", "todos").strip() or "todos"
    servicios = Servicio.objects.filter(activo=True)
    if categoria != "todos":
        servicios = servicios.filter(categoria__iexact=categoria)
    categorias = Servicio.objects.filter(activo=True).values_list("categoria", flat=True).distinct().order_by("categoria")
    contexto = {
        "introduccion": {"titulo": "Servicios y gestión territorial", "bajada": "Catálogo administrable de servicios municipales."},
        "servicios": servicios,
        "categorias": ["todos", *categorias],
        "categoria_activa": categoria,
        "total": servicios.count(),
        "total_general": Servicio.objects.filter(activo=True).count(),
        "pagina_activa": "servicios",
    }
    return render(request, "servicios/catalogo.html", contexto)


def detalle(request, slug: str):
    servicio = get_object_or_404(Servicio, slug=slug, activo=True)
    relacionados = Servicio.objects.filter(categoria=servicio.categoria, activo=True).exclude(pk=servicio.pk)[:3]
    return render(request, "servicios/detalle.html", {"servicio": servicio, "relacionados": relacionados, "pagina_activa": "servicios"})


def dashboard(request):
    actividades = Actividad.objects.select_related("funcionario", "item", "periodo")
    compromisos = Compromiso.objects.select_related("responsable", "delegacion")
    contexto = {
        "periodo": Periodo.objects.filter(estado="abierto").first(),
        "delegaciones": Delegacion.objects.filter(activa=True).annotate(total_compromisos=Count("compromisos")),
        "total_funcionarios": Funcionario.objects.filter(activo=True).count(),
        "total_actividades": actividades.count(),
        "actividades_validadas": actividades.filter(estado="validada").count(),
        "compromisos_pendientes": compromisos.exclude(estado="realizado").count(),
        "actividades_recientes": actividades[:8],
        "compromisos_recientes": compromisos[:8],
        "pagina_activa": "dashboard",
    }
    return render(request, "servicios/dashboard.html", contexto)


def actividades(request):
    queryset = Actividad.objects.select_related("funcionario", "item", "periodo")
    estado = request.GET.get("estado", "").strip()
    if estado:
        queryset = queryset.filter(estado=estado)
    return render(request, "servicios/actividades.html", {"actividades": queryset, "estado_activo": estado, "pagina_activa": "actividades"})


def agenda(request):
    compromisos = Compromiso.objects.select_related("responsable", "delegacion")
    estado = request.GET.get("estado", "").strip()
    if estado:
        compromisos = compromisos.filter(estado=estado)
    return render(request, "servicios/agenda.html", {"compromisos": compromisos, "estado_activo": estado, "pagina_activa": "agenda"})
