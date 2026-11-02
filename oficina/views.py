from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from institucional.models import Delegacion
from laserena.permisos import (
	GRUPO_ADMINISTRATIVO,
	acotar_ambito,
	con_permiso,
	grupo_usuario,
	parametro_permitido,
	perfil_funcionario,
	texto_busqueda,
)
from laserena.rut import normalizar_rut

from .forms import AusenciaForm, BeneficioForm, CartaForm, CartaSeguimientoForm
from .models import Ausencia, BeneficioNino, Carta
from .transacciones import anular_ausencia, registrar_ausencia

POR_PAGINA = 20


def _paginar(request, queryset):
	pagina = Paginator(queryset, POR_PAGINA).get_page(request.GET.get("pagina"))
	parametros = request.GET.copy()
	parametros.pop("pagina", None)
	return pagina, parametros.urlencode()


def _cartas_visibles(user):
	cartas = acotar_ambito(Carta.objects.select_related("delegacion", "derivada_a", "organizacion"), user, "delegacion")
	if grupo_usuario(user) == GRUPO_ADMINISTRATIVO:
		cartas = cartas.filter(derivada_a=perfil_funcionario(user))
	return cartas


def _filtro_delegacion(request):
	permitidas = {str(pk) for pk in Delegacion.objects.values_list("pk", flat=True)}
	return parametro_permitido(request, "delegacion", permitidas)


# --- Cartas de Oficina de Partes -------------------------------------------------

@con_permiso("oficina.view_carta")
def cartas(request):
	visibles = _cartas_visibles(request.user)
	cartas = visibles
	busqueda = texto_busqueda(request)
	estado = parametro_permitido(request, "estado", dict(Carta.ESTADOS))
	delegacion = _filtro_delegacion(request)
	if busqueda:
		cartas = cartas.filter(Q(folio__icontains=busqueda) | Q(remitente__icontains=busqueda) | Q(asunto__icontains=busqueda))
	if estado:
		cartas = cartas.filter(estado=estado)
	if delegacion:
		cartas = cartas.filter(delegacion_id=delegacion)
	pagina, parametros = _paginar(request, cartas)
	resumen = dict(visibles.values_list("estado").annotate(total=Count("id")))
	return render(request, "oficina/cartas.html", {
		"pagina": pagina, "parametros": parametros, "total": pagina.paginator.count,
		"busqueda": busqueda, "estado_activo": estado, "delegacion_activa": delegacion,
		"estados": Carta.ESTADOS, "delegaciones": Delegacion.objects.filter(activa=True),
		"resumen": [(etiqueta, resumen.get(codigo, 0), codigo) for codigo, etiqueta in Carta.ESTADOS],
		"pagina_activa": "cartas",
	})


@con_permiso("oficina.view_carta")
def carta_detalle(request, pk):
	carta = get_object_or_404(_cartas_visibles(request.user).select_related("registrada_por"), pk=pk)
	return render(request, "oficina/carta_detalle.html", {"carta": carta, "pagina_activa": "cartas"})


@con_permiso("oficina.add_carta")
def carta_crear(request):
	form = CartaForm(request.POST or None, usuario=request.user)
	if request.method == "POST" and form.is_valid():
		carta = form.save(commit=False)
		carta.registrada_por = request.user
		carta.save()
		messages.success(request, f"Carta ingresada con folio {carta.folio}.")
		return redirect("oficina:carta_detalle", pk=carta.pk)
	return render(request, "oficina/formulario.html", {"form": form, "titulo": "Ingresar carta", "seccion": "Cartas", "url_listado": "oficina:cartas", "pagina_activa": "cartas"})


@con_permiso("oficina.change_carta")
def carta_editar(request, pk):
	carta = get_object_or_404(_cartas_visibles(request.user), pk=pk)
	clase = CartaSeguimientoForm if grupo_usuario(request.user) == GRUPO_ADMINISTRATIVO else CartaForm
	form = clase(request.POST or None, instance=carta, usuario=request.user)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, f"Carta {carta.folio} actualizada.")
		return redirect("oficina:carta_detalle", pk=carta.pk)
	return render(request, "oficina/formulario.html", {
		"form": form, "objeto": carta, "titulo": f"Editar carta {carta.folio}", "seccion": "Cartas",
		"url_listado": "oficina:cartas", "url_detalle": "oficina:carta_detalle", "pagina_activa": "cartas",
	})


@con_permiso("oficina.delete_carta")
def carta_eliminar(request, pk):
	carta = get_object_or_404(_cartas_visibles(request.user), pk=pk)
	if request.method == "POST":
		folio = carta.folio
		carta.delete()
		messages.success(request, f"Carta {folio} eliminada.")
		return redirect("oficina:cartas")
	return render(request, "oficina/eliminar.html", {
		"objeto": carta, "nombre": f"la carta {carta.folio} ({carta.asunto})", "seccion": "Cartas",
		"url_listado": "oficina:cartas", "url_detalle": "oficina:carta_detalle",
		"sugerencia": "Si la carta ya se tramitó, puedes dejarla en estado Archivada en vez de eliminarla.", "pagina_activa": "cartas",
	})


# --- Beneficios para niños ----------------------------------------------------------

def _beneficios_visibles(user):
	return acotar_ambito(BeneficioNino.objects.select_related("delegacion", "organizacion"), user, "delegacion")


@con_permiso("oficina.view_beneficionino")
def beneficios(request):
	visibles = _beneficios_visibles(request.user)
	beneficios = visibles
	busqueda = texto_busqueda(request)
	estado = parametro_permitido(request, "estado", dict(BeneficioNino.ESTADOS))
	tipo = parametro_permitido(request, "tipo", dict(BeneficioNino.TIPOS))
	delegacion = _filtro_delegacion(request)
	if busqueda:
		filtro = Q(nombre_nino__icontains=busqueda) | Q(apoderado__icontains=busqueda)
		try:
			filtro |= Q(rut_nino=normalizar_rut(busqueda))
		except ValidationError:
			filtro |= Q(rut_nino__startswith=busqueda.replace(".", ""))
		beneficios = beneficios.filter(filtro)
	if estado:
		beneficios = beneficios.filter(estado=estado)
	if tipo:
		beneficios = beneficios.filter(tipo=tipo)
	if delegacion:
		beneficios = beneficios.filter(delegacion_id=delegacion)
	pagina, parametros = _paginar(request, beneficios)
	resumen = dict(visibles.values_list("estado").annotate(total=Count("id")))
	return render(request, "oficina/beneficios.html", {
		"pagina": pagina, "parametros": parametros, "total": pagina.paginator.count,
		"busqueda": busqueda, "estado_activo": estado, "tipo_activo": tipo, "delegacion_activa": delegacion,
		"estados": BeneficioNino.ESTADOS, "tipos": BeneficioNino.TIPOS, "delegaciones": Delegacion.objects.filter(activa=True),
		"resumen": [(etiqueta, resumen.get(codigo, 0), codigo) for codigo, etiqueta in BeneficioNino.ESTADOS],
		"pagina_activa": "beneficios",
	})


@con_permiso("oficina.view_beneficionino")
def beneficio_detalle(request, pk):
	beneficio = get_object_or_404(_beneficios_visibles(request.user).select_related("registrado_por"), pk=pk)
	return render(request, "oficina/beneficio_detalle.html", {"beneficio": beneficio, "pagina_activa": "beneficios"})


@con_permiso("oficina.add_beneficionino")
def beneficio_crear(request):
	form = BeneficioForm(request.POST or None, usuario=request.user)
	if request.method == "POST" and form.is_valid():
		beneficio = form.save(commit=False)
		beneficio.registrado_por = request.user
		beneficio.save()
		messages.success(request, f"Beneficio registrado para {beneficio.nombre_nino}.")
		return redirect("oficina:beneficio_detalle", pk=beneficio.pk)
	return render(request, "oficina/formulario.html", {"form": form, "titulo": "Registrar beneficio", "seccion": "Beneficios para niños", "url_listado": "oficina:beneficios", "pagina_activa": "beneficios"})


@con_permiso("oficina.change_beneficionino")
def beneficio_editar(request, pk):
	beneficio = get_object_or_404(_beneficios_visibles(request.user), pk=pk)
	form = BeneficioForm(request.POST or None, instance=beneficio, usuario=request.user)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "Beneficio actualizado.")
		return redirect("oficina:beneficio_detalle", pk=beneficio.pk)
	return render(request, "oficina/formulario.html", {
		"form": form, "objeto": beneficio, "titulo": f"Editar beneficio de {beneficio.nombre_nino}", "seccion": "Beneficios para niños",
		"url_listado": "oficina:beneficios", "url_detalle": "oficina:beneficio_detalle", "pagina_activa": "beneficios",
	})


@con_permiso("oficina.delete_beneficionino")
def beneficio_eliminar(request, pk):
	beneficio = get_object_or_404(_beneficios_visibles(request.user), pk=pk)
	if request.method == "POST":
		nombre = beneficio.nombre_nino
		beneficio.delete()
		messages.success(request, f"Beneficio de {nombre} eliminado.")
		return redirect("oficina:beneficios")
	return render(request, "oficina/eliminar.html", {
		"objeto": beneficio, "nombre": f"el beneficio de {beneficio.nombre_nino} ({beneficio.rut_formateado})", "seccion": "Beneficios para niños",
		"url_listado": "oficina:beneficios", "url_detalle": "oficina:beneficio_detalle",
		"sugerencia": "Si el beneficio no se entregará, puedes dejarlo Anulado para conservar el registro.", "pagina_activa": "beneficios",
	})


# --- Transacción: registrar ausencia --------------------------------------------------

def _ausencias_visibles(user):
	ausencias = acotar_ambito(Ausencia.objects.select_related("funcionario__delegacion", "periodo", "registrada_por"), user, "funcionario__delegacion")
	if grupo_usuario(user) == GRUPO_ADMINISTRATIVO:
		ausencias = ausencias.filter(funcionario=perfil_funcionario(user))
	return ausencias


@con_permiso("oficina.view_ausencia")
def ausencias(request):
	ausencias = _ausencias_visibles(request.user)
	estado = parametro_permitido(request, "estado", dict(Ausencia.ESTADOS))
	busqueda = texto_busqueda(request)
	if estado:
		ausencias = ausencias.filter(estado=estado)
	if busqueda:
		ausencias = ausencias.filter(funcionario__nombre_completo__icontains=busqueda)
	pagina, parametros = _paginar(request, ausencias)
	return render(request, "oficina/ausencias.html", {
		"pagina": pagina, "parametros": parametros, "total": pagina.paginator.count, "busqueda": busqueda,
		"estado_activo": estado, "estados": Ausencia.ESTADOS, "pagina_activa": "ausencias",
	})


@con_permiso("oficina.add_ausencia")
def ausencia_registrar(request):
	form = AusenciaForm(request.POST or None, usuario=request.user)
	if request.method == "POST" and form.is_valid():
		try:
			ausencia = registrar_ausencia(form.save(commit=False), request.user)
		except ValidationError as error:
			if hasattr(error, "error_dict"):
				for campo, errores in error.message_dict.items():
					form.add_error(campo if campo in form.fields else None, errores)
			else:
				form.add_error(None, error.messages)
		else:
			messages.success(request, f"Ausencia registrada: {ausencia.ajustes.count()} meta(s) ajustada(s) para {ausencia.funcionario.nombre_completo}.")
			return redirect("oficina:ausencia_detalle", pk=ausencia.pk)
	return render(request, "oficina/ausencia_formulario.html", {"form": form, "pagina_activa": "ausencias"})


@con_permiso("oficina.view_ausencia")
def ausencia_detalle(request, pk):
	ausencia = get_object_or_404(_ausencias_visibles(request.user), pk=pk)
	return render(request, "oficina/ausencia_detalle.html", {
		"ausencia": ausencia, "ajustes": ausencia.ajustes.select_related("meta__item"), "pagina_activa": "ausencias",
	})


@con_permiso("oficina.anular_ausencia")
@require_POST
def ausencia_anular(request, pk):
	ausencia = get_object_or_404(_ausencias_visibles(request.user), pk=pk)
	try:
		anular_ausencia(ausencia, request.user)
	except ValidationError as error:
		messages.warning(request, " ".join(error.messages))
	else:
		messages.success(request, "Ausencia anulada y metas restituidas.")
	return redirect("oficina:ausencia_detalle", pk=ausencia.pk)
