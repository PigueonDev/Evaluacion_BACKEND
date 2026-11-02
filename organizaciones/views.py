from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from laserena.permisos import con_permiso, parametro_permitido, texto_busqueda

from .forms import OrganizacionForm
from .models import TERRITORIOS, OrganizacionComunitaria

POR_PAGINA = 25


@con_permiso("organizaciones.view_organizacioncomunitaria")
def listado(request):
	organizaciones = OrganizacionComunitaria.objects.all()
	busqueda = texto_busqueda(request)
	estado = parametro_permitido(request, "estado", dict(OrganizacionComunitaria.ESTADOS))
	territorio = parametro_permitido(request, "territorio", dict(TERRITORIOS))
	tipo = parametro_permitido(request, "tipo", dict(OrganizacionComunitaria.TIPOS))
	if busqueda:
		filtro = Q(nombre__icontains=busqueda) | Q(domicilio__icontains=busqueda)
		if busqueda.isdigit():
			filtro |= Q(numero_registro_pj=int(busqueda))
		organizaciones = organizaciones.filter(filtro)
	if estado:
		organizaciones = organizaciones.filter(estado=estado)
	if territorio:
		organizaciones = organizaciones.filter(territorio=territorio)
	if tipo:
		organizaciones = organizaciones.filter(tipo=tipo)
	pagina = Paginator(organizaciones, POR_PAGINA).get_page(request.GET.get("pagina"))
	parametros = request.GET.copy()
	parametros.pop("pagina", None)
	resumen = dict(OrganizacionComunitaria.objects.values_list("estado").annotate(total=Count("id")))
	contexto = {
		"pagina": pagina,
		"busqueda": busqueda,
		"estado_activo": estado,
		"territorio_activo": territorio,
		"tipo_activo": tipo,
		"estados": OrganizacionComunitaria.ESTADOS,
		"territorios": TERRITORIOS,
		"tipos": OrganizacionComunitaria.TIPOS,
		"parametros": parametros.urlencode(),
		"total": pagina.paginator.count,
		"resumen": [(etiqueta, resumen.get(codigo, 0), codigo) for codigo, etiqueta in OrganizacionComunitaria.ESTADOS],
		"pagina_activa": "organizaciones",
	}
	return render(request, "organizaciones/listado.html", contexto)


@con_permiso("organizaciones.view_organizacioncomunitaria")
def detalle(request, pk):
	organizacion = get_object_or_404(OrganizacionComunitaria.objects.select_related("verificada_por"), pk=pk)
	return render(request, "organizaciones/detalle.html", {
		"organizacion": organizacion,
		"estados": OrganizacionComunitaria.ESTADOS,
		"pagina_activa": "organizaciones",
	})


@con_permiso("organizaciones.add_organizacioncomunitaria")
def crear(request):
	form = OrganizacionForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		organizacion = form.save()
		messages.success(request, f"Organización «{organizacion}» creada en estado Sin verificar.")
		return redirect("organizaciones:detalle", pk=organizacion.pk)
	return render(request, "organizaciones/formulario.html", {"form": form, "titulo": "Nueva organización", "pagina_activa": "organizaciones"})


@con_permiso("organizaciones.change_organizacioncomunitaria")
def editar(request, pk):
	organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
	form = OrganizacionForm(request.POST or None, instance=organizacion)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "Organización actualizada.")
		return redirect("organizaciones:detalle", pk=organizacion.pk)
	return render(request, "organizaciones/formulario.html", {
		"form": form, "organizacion": organizacion, "titulo": "Editar organización", "pagina_activa": "organizaciones",
	})


@con_permiso("organizaciones.delete_organizacioncomunitaria")
def eliminar(request, pk):
	organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
	if request.method == "POST":
		nombre = str(organizacion)
		organizacion.delete()
		messages.success(request, f"Organización «{nombre}» eliminada.")
		return redirect("organizaciones:listado")
	return render(request, "organizaciones/eliminar.html", {"organizacion": organizacion, "pagina_activa": "organizaciones"})


@con_permiso("organizaciones.verificar_organizacion")
@require_POST
def verificar(request, pk):
	organizacion = get_object_or_404(OrganizacionComunitaria, pk=pk)
	try:
		organizacion.cambiar_estado(request.POST.get("estado", ""), request.user)
	except ValidationError as error:
		messages.warning(request, " ".join(error.messages))
	else:
		messages.success(request, f"Estado actualizado a «{organizacion.get_estado_display()}».")
	return redirect("organizaciones:detalle", pk=organizacion.pk)
