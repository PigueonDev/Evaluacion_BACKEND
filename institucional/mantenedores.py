"""Pantallas de alta, edición y baja de los catálogos del alcance mínimo."""

from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from laserena.filtros import texto_busqueda
from laserena.permisos import solo_administrador
from servicios.models import ItemMedicion, Meta, Periodo, SubtipoAtencion, TipoAtencion

from .formularios import (
	DelegacionForm,
	HitoForm,
	MetaFuncionarioForm,
	PeriodoForm,
	SubtipoAtencionForm,
	TerritorioForm,
	TipoAtencionForm,
	VecinoForm,
)
from .models import Cargo, Delegacion, Hito, Territorio, Vecino


def _formulario(request, form, titulo, seccion, url_listado, pagina):
	return render(request, "oficina/formulario.html", {
		"form": form,
		"titulo": titulo,
		"seccion": seccion,
		"url_listado": url_listado,
		"pagina_activa": pagina,
	})


def _baja(request, objeto, nombre, url_listado, pagina, seccion):
	if request.method == "POST":
		try:
			objeto.delete()
		except ProtectedError:
			if hasattr(objeto, "activo"):
				objeto.activo = False
				objeto.save(update_fields=["activo"])
				messages.warning(request, f"{nombre} tiene registros asociados: quedó inactivo en lugar de eliminarse.")
			elif hasattr(objeto, "activa"):
				objeto.activa = False
				objeto.save(update_fields=["activa"])
				messages.warning(request, f"{nombre} tiene registros asociados: quedó inactiva en lugar de eliminarse.")
			else:
				messages.warning(request, f"{nombre} tiene registros asociados y no se puede eliminar.")
		else:
			messages.success(request, f"{nombre} eliminado.")
		return redirect(url_listado)
	return render(request, "institucional/confirmar.html", {
		"titulo": f"Eliminar {nombre}",
		"nombre": nombre,
		"seccion": seccion,
		"url_listado": url_listado,
		"pagina_activa": pagina,
	})


@solo_administrador
def delegaciones(request):
	busqueda = texto_busqueda(request)
	queryset = Delegacion.objects.all()
	if busqueda:
		queryset = queryset.filter(Q(nombre__icontains=busqueda) | Q(territorio__icontains=busqueda))
	return render(request, "institucional/delegaciones/listado.html", {"delegaciones": queryset, "busqueda": busqueda, "pagina_activa": "delegaciones"})


@solo_administrador
def delegacion_crear(request):
	form = DelegacionForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		delegacion = form.save()
		messages.success(request, f"Delegación {delegacion.nombre} creada.")
		return redirect("institucional:delegaciones")
	return _formulario(request, form, "Crear delegación", "Delegaciones", "institucional:delegaciones", "delegaciones")


@solo_administrador
def delegacion_editar(request, pk):
	delegacion = get_object_or_404(Delegacion, pk=pk)
	form = DelegacionForm(request.POST or None, instance=delegacion)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Delegación {delegacion.nombre} actualizada.")
		return redirect("institucional:delegaciones")
	return _formulario(request, form, f"Editar {delegacion.nombre}", "Delegaciones", "institucional:delegaciones", "delegaciones")


@solo_administrador
def delegacion_eliminar(request, pk):
	delegacion = get_object_or_404(Delegacion, pk=pk)
	return _baja(request, delegacion, delegacion.nombre, "institucional:delegaciones", "delegaciones", "Delegaciones")


@solo_administrador
def territorios(request):
	busqueda = texto_busqueda(request)
	queryset = Territorio.objects.all()
	if busqueda:
		queryset = queryset.filter(Q(nombre__icontains=busqueda) | Q(codigo__icontains=busqueda))
	return render(request, "institucional/territorios/listado.html", {"territorios": queryset, "busqueda": busqueda, "pagina_activa": "territorios"})


@solo_administrador
def territorio_crear(request):
	form = TerritorioForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		territorio = form.save()
		messages.success(request, f"Territorio {territorio.nombre} creado.")
		return redirect("institucional:territorios")
	return _formulario(request, form, "Crear territorio", "Territorios", "institucional:territorios", "territorios")


@solo_administrador
def territorio_editar(request, pk):
	territorio = get_object_or_404(Territorio, pk=pk)
	anterior = territorio.nombre
	form = TerritorioForm(request.POST or None, instance=territorio)
	if request.method == "POST" and form.is_valid():
		territorio = form.save()
		if anterior != territorio.nombre:
			Delegacion.objects.filter(territorio=anterior).update(territorio=territorio.nombre)
		messages.success(request, f"Territorio {territorio.nombre} actualizado.")
		return redirect("institucional:territorios")
	return _formulario(request, form, f"Editar {territorio.nombre}", "Territorios", "institucional:territorios", "territorios")


@solo_administrador
def territorio_eliminar(request, pk):
	territorio = get_object_or_404(Territorio, pk=pk)
	return _baja(request, territorio, territorio.nombre, "institucional:territorios", "territorios", "Territorios")


@solo_administrador
def vecinos(request):
	busqueda = texto_busqueda(request)
	queryset = Vecino.objects.select_related("delegacion")
	if busqueda:
		queryset = queryset.filter(Q(nombre__icontains=busqueda) | Q(rut__icontains=busqueda) | Q(telefono__icontains=busqueda))
	return render(request, "institucional/vecinos/listado.html", {"vecinos": queryset, "busqueda": busqueda, "pagina_activa": "vecinos"})


@solo_administrador
def vecino_crear(request):
	form = VecinoForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		vecino = form.save()
		messages.success(request, f"Vecino {vecino.nombre} registrado.")
		return redirect("institucional:vecinos")
	return _formulario(request, form, "Registrar vecino", "Vecinos", "institucional:vecinos", "vecinos")


@solo_administrador
def vecino_editar(request, pk):
	vecino = get_object_or_404(Vecino, pk=pk)
	form = VecinoForm(request.POST or None, instance=vecino)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Vecino {vecino.nombre} actualizado.")
		return redirect("institucional:vecinos")
	return _formulario(request, form, f"Editar {vecino.nombre}", "Vecinos", "institucional:vecinos", "vecinos")


@solo_administrador
def vecino_eliminar(request, pk):
	vecino = get_object_or_404(Vecino, pk=pk)
	return _baja(request, vecino, vecino.nombre, "institucional:vecinos", "vecinos", "Vecinos")


@solo_administrador
def hitos(request):
	busqueda = texto_busqueda(request)
	queryset = Hito.objects.select_related("delegacion", "responsable")
	if busqueda:
		queryset = queryset.filter(Q(nombre__icontains=busqueda) | Q(responsable__nombre_completo__icontains=busqueda))
	return render(request, "institucional/hitos/listado.html", {"hitos": queryset, "busqueda": busqueda, "pagina_activa": "hitos"})


@solo_administrador
def hito_crear(request):
	form = HitoForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		hito = form.save()
		messages.success(request, f"Hito {hito.nombre} creado.")
		return redirect("institucional:hitos")
	return _formulario(request, form, "Crear hito", "Hitos", "institucional:hitos", "hitos")


@solo_administrador
def hito_editar(request, pk):
	hito = get_object_or_404(Hito, pk=pk)
	form = HitoForm(request.POST or None, instance=hito)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Hito {hito.nombre} actualizado.")
		return redirect("institucional:hitos")
	return _formulario(request, form, f"Editar {hito.nombre}", "Hitos", "institucional:hitos", "hitos")


@solo_administrador
def hito_eliminar(request, pk):
	hito = get_object_or_404(Hito, pk=pk)
	return _baja(request, hito, hito.nombre, "institucional:hitos", "hitos", "Hitos")


@solo_administrador
def trimestres(request):
	return render(request, "institucional/trimestres/listado.html", {
		"periodos": Periodo.objects.all(),
		"pagina_activa": "trimestres",
	})


@solo_administrador
def trimestre_crear(request):
	form = PeriodoForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		periodo = form.save()
		messages.success(request, f"Trimestre {periodo.nombre} creado ({periodo.get_estado_display().lower()}).")
		return redirect("institucional:trimestres")
	return _formulario(request, form, "Abrir trimestre", "Trimestres", "institucional:trimestres", "trimestres")


@solo_administrador
@require_POST
def trimestre_estado(request, pk):
	periodo = get_object_or_404(Periodo, pk=pk)
	estado = request.POST.get("estado")
	if estado not in dict(Periodo.ESTADOS):
		messages.warning(request, "Estado de trimestre no válido.")
	else:
		periodo.estado = estado
		periodo.save(update_fields=["estado"])
		messages.success(request, f"{periodo.nombre} quedó {periodo.get_estado_display().lower()}.")
	return redirect("institucional:trimestres")


@solo_administrador
def trimestre_metas(request, pk):
	periodo = get_object_or_404(Periodo, pk=pk)
	form = MetaFuncionarioForm(request.POST or None, periodo=periodo)
	if request.method == "POST" and form.is_valid():
		meta = form.save()
		messages.success(request, f"Meta de {meta.funcionario.nombre_completo} en {meta.item.nombre}: {meta.objetivo} con ponderador {meta.ponderador} %.")
		return redirect("institucional:trimestre_metas", pk=periodo.pk)
	personales = Meta.objects.filter(periodo=periodo, funcionario__isnull=False).select_related("funcionario", "funcionario__cargo", "item")
	return render(request, "institucional/trimestres/metas.html", {
		"periodo": periodo,
		"form": form,
		"personales": personales,
		"items": ItemMedicion.objects.filter(activo=True),
		"pagina_activa": "trimestres",
	})


@solo_administrador
def tipos_atencion(request):
	return render(request, "institucional/tipos/listado.html", {
		"tipos": TipoAtencion.objects.prefetch_related("subtipos"),
		"pagina_activa": "tipos",
	})


@solo_administrador
def tipo_crear(request):
	form = TipoAtencionForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		tipo = form.save()
		messages.success(request, f"Tipo {tipo.nombre} creado.")
		return redirect("institucional:tipos_atencion")
	return _formulario(request, form, "Crear tipo de atención", "Tipos de atención", "institucional:tipos_atencion", "tipos")


@solo_administrador
def tipo_editar(request, pk):
	tipo = get_object_or_404(TipoAtencion, pk=pk)
	form = TipoAtencionForm(request.POST or None, instance=tipo)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Tipo {tipo.nombre} actualizado.")
		return redirect("institucional:tipos_atencion")
	return _formulario(request, form, f"Editar {tipo.nombre}", "Tipos de atención", "institucional:tipos_atencion", "tipos")


@solo_administrador
def tipo_eliminar(request, pk):
	tipo = get_object_or_404(TipoAtencion, pk=pk)
	return _baja(request, tipo, tipo.nombre, "institucional:tipos_atencion", "tipos", "Tipos de atención")


@solo_administrador
def subtipo_crear(request, tipo_pk):
	tipo = get_object_or_404(TipoAtencion, pk=tipo_pk)
	form = SubtipoAtencionForm(request.POST or None, tipo=tipo)
	if request.method == "POST" and form.is_valid():
		subtipo = form.save()
		messages.success(request, f"Subtipo {subtipo.nombre} creado.")
		return redirect("institucional:tipos_atencion")
	return _formulario(request, form, f"Crear subtipo de {tipo.nombre}", "Tipos de atención", "institucional:tipos_atencion", "tipos")


@solo_administrador
def subtipo_editar(request, pk):
	subtipo = get_object_or_404(SubtipoAtencion, pk=pk)
	form = SubtipoAtencionForm(request.POST or None, instance=subtipo)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Subtipo {subtipo.nombre} actualizado.")
		return redirect("institucional:tipos_atencion")
	return _formulario(request, form, f"Editar {subtipo.nombre}", "Tipos de atención", "institucional:tipos_atencion", "tipos")


@solo_administrador
def subtipo_eliminar(request, pk):
	subtipo = get_object_or_404(SubtipoAtencion, pk=pk)
	return _baja(request, subtipo, subtipo.nombre, "institucional:tipos_atencion", "tipos", "Tipos de atención")


@solo_administrador
def cargo_crear(request):
	from .forms import CargoForm

	form = CargoForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		cargo = form.save()
		messages.success(request, f"Cargo {cargo.nombre} creado.")
		return redirect("institucional:cargos")
	return _formulario(request, form, "Crear cargo", "Cargos", "institucional:cargos", "cargos")


@solo_administrador
def cargo_eliminar(request, pk):
	cargo = get_object_or_404(Cargo, pk=pk)
	return _baja(request, cargo, cargo.nombre, "institucional:cargos", "cargos", "Cargos")
