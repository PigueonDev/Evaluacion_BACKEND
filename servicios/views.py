from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from institucional.models import Delegacion, Funcionario

from .models import Actividad, Compromiso, Periodo, Servicio


def area_administrativa(view):
    """Exige sesión de personal. Una cuenta ciudadana no abre estas pantallas."""

    @login_required(login_url="servicios:ingreso")
    def envuelta(request, *args, **kwargs):
        if not request.user.is_staff:
            logout(request)
            return redirect(f"{reverse('servicios:ingreso')}?sin_permiso=1")
        return view(request, *args, **kwargs)

    return envuelta


class IngresoAdministrativoView(LoginView):
    template_name = "servicios/ingreso.html"
    redirect_authenticated_user = False

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            destino = self.get_redirect_url() or reverse("servicios:dashboard")
            return redirect(destino)
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        formulario = super().get_form(form_class)
        formulario.fields["username"].widget.attrs.update({"class": "form-control", "autofocus": True})
        formulario.fields["password"].widget.attrs.update({"class": "form-control"})
        return formulario

    def form_valid(self, form):
        usuario = form.get_user()
        if not usuario.is_staff:
            form.add_error(None, "Esta cuenta no tiene acceso al área administrativa.")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["sin_permiso"] = self.request.GET.get("sin_permiso") == "1"
        contexto["pagina_activa"] = "ingreso"
        return contexto


@require_POST
def salir(request):
    logout(request)
    return redirect("institucional:inicio")


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


@area_administrativa
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
        "area_administrativa": True,
    }
    return render(request, "servicios/dashboard.html", contexto)


@area_administrativa
def actividades(request):
    queryset = Actividad.objects.select_related("funcionario", "item", "periodo")
    estado = request.GET.get("estado", "").strip()
    if estado:
        queryset = queryset.filter(estado=estado)
    return render(
        request,
        "servicios/actividades.html",
        {"actividades": queryset, "estado_activo": estado, "pagina_activa": "actividades", "area_administrativa": True},
    )


@area_administrativa
def agenda(request):
    compromisos = Compromiso.objects.select_related("responsable", "delegacion")
    estado = request.GET.get("estado", "").strip()
    if estado:
        compromisos = compromisos.filter(estado=estado)
    return render(
        request,
        "servicios/agenda.html",
        {"compromisos": compromisos, "estado_activo": estado, "pagina_activa": "agenda", "area_administrativa": True},
    )
