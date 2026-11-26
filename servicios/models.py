import re
import uuid
from datetime import datetime

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
from django.utils import timezone


User = get_user_model()

EXTENSIONES_EVIDENCIA = ["jpg", "jpeg", "png", "webp"]
FORMATOS_IMAGEN_EVIDENCIA = {"JPEG", "PNG", "WEBP"}
TAMANO_MAXIMO_EVIDENCIA = 5 * 1024 * 1024
MOTIVO_RECHAZO_MAX = 280
TELEFONO_ACTIVIDAD = re.compile(r"^\+?[0-9][0-9\s-]{7,18}$")
CODIGO_VERIFICADOR = re.compile(r"^[A-Z0-9]{2,10}-\d{4}-\d{3,}$")
MAXIMO_GESTIONES_POR_CASO = 3
DIAS_COMPROMISO_PROXIMO = 7
TRANSICIONES_COMPROMISO = {
	"ingresado": {"pendiente"},
	"pendiente": {"proceso"},
	"proceso": {"realizado"},
	"realizado": set(),
}


def validar_tamano_evidencia(archivo):
	if archivo.size > TAMANO_MAXIMO_EVIDENCIA:
		raise ValidationError("La evidencia no puede superar los 5 MB.")


def validar_imagen_evidencia(archivo):
	"""Captura de pantalla: solo PNG, JPG o WebP, y que el contenido sea esa imagen."""
	validar_tamano_evidencia(archivo)
	from PIL import Image, UnidentifiedImageError

	try:
		if hasattr(archivo, "seek"):
			archivo.seek(0)
		imagen = Image.open(archivo)
		imagen.load()
		formato = (imagen.format or "").upper()
	except (UnidentifiedImageError, OSError, ValueError):
		raise ValidationError("El archivo no es una imagen PNG, JPG o WebP válida.")
	finally:
		if hasattr(archivo, "seek"):
			archivo.seek(0)
	if formato not in FORMATOS_IMAGEN_EVIDENCIA:
		raise ValidationError("Solo se aceptan capturas en PNG, JPG o WebP.")


class Servicio(models.Model):
	slug = models.SlugField(max_length=120, unique=True)
	nombre = models.CharField(max_length=160)
	categoria = models.CharField("categoría", max_length=80)
	unidad = models.CharField(max_length=160)
	descripcion = models.TextField("descripción")
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "servicio"
		verbose_name_plural = "servicios"
		ordering = ["nombre"]

	def __str__(self):
		return self.nombre


class ItemMedicion(models.Model):
	TIPOS_MEDICION = [
		("conteo", "Conteo de actividades aprobadas"),
		("tasa_tubo", "Porcentaje de ingresos al tubo realizados"),
		("emergencia", "Emergencia: cumple si atendió al menos una"),
		("sin_puntaje", "Otra gestión: se registra, no puntúa"),
	]
	codigo = models.CharField("código", max_length=30, unique=True)
	nombre = models.CharField(max_length=160)
	descripcion = models.TextField("descripción", blank=True)
	unidad = models.CharField(max_length=40, default="cantidad")
	tipo_medicion = models.CharField("tipo de medición", max_length=20, choices=TIPOS_MEDICION, default="conteo")
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "ítem de medición"
		verbose_name_plural = "ítems de medición"
		ordering = ["codigo"]

	def __str__(self):
		return f"{self.codigo} - {self.nombre}"


class Periodo(models.Model):
	ESTADOS = [("abierto", "Abierto"), ("cerrado", "Cerrado")]
	nombre = models.CharField(max_length=120, unique=True)
	fecha_inicio = models.DateField("fecha de inicio")
	fecha_termino = models.DateField("fecha de término")
	estado = models.CharField(max_length=20, choices=ESTADOS, default="abierto")
	tope_cumplimiento = models.DecimalField("tope de cumplimiento", max_digits=5, decimal_places=2, default=150)
	tope_item = models.DecimalField("tope por ítem", max_digits=5, decimal_places=2, default=120)
	umbral_colectivo = models.DecimalField("umbral colectivo", max_digits=5, decimal_places=2, default=80)
	umbral_ambar = models.DecimalField("umbral naranjo", max_digits=5, decimal_places=2, default=60)
	bono_felicitacion = models.DecimalField("puntos por felicitación", max_digits=5, decimal_places=2, default=10)
	maximo_felicitaciones = models.PositiveSmallIntegerField("felicitaciones que suman como máximo", default=3)
	descuento_reclamo = models.DecimalField("puntos que descuenta cada reclamo", max_digits=5, decimal_places=2, default=20)

	class Meta:
		verbose_name = "período"
		verbose_name_plural = "períodos"
		ordering = ["-fecha_inicio"]

	def clean(self):
		if self.fecha_termino < self.fecha_inicio:
			raise ValidationError("La fecha de término no puede ser anterior al inicio.")

	@property
	def dias_totales(self):
		return (self.fecha_termino - self.fecha_inicio).days + 1

	def dias_transcurridos(self, fecha=None):
		fecha = fecha or timezone.localdate()
		if fecha < self.fecha_inicio:
			return 0
		return min((fecha - self.fecha_inicio).days + 1, self.dias_totales)

	def avance_esperado(self, fecha=None):
		"""Porcentaje del período transcurrido: el «objetivo al día de hoy» de la hoja SEMAFORO."""
		fecha = fecha or timezone.localdate()
		if fecha <= self.fecha_inicio:
			return 0
		if fecha >= self.fecha_termino:
			return 100
		return self.dias_transcurridos(fecha) / self.dias_totales * 100

	def semaforo(self, cumplimiento, fecha=None):
		esperado = self.avance_esperado(fecha)
		if cumplimiento >= esperado:
			return "verde"
		if cumplimiento >= esperado * float(self.umbral_ambar) / 100:
			return "ambar"
		return "rojo"

	def anterior(self):
		return Periodo.objects.filter(fecha_termino__lt=self.fecha_inicio).order_by("-fecha_termino").first()

	def __str__(self):
		return self.nombre


class Meta(models.Model):
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="metas", verbose_name="período")
	item = models.ForeignKey(ItemMedicion, on_delete=models.PROTECT, related_name="metas", verbose_name="ítem de medición")
	cargo = models.ForeignKey("institucional.Cargo", on_delete=models.PROTECT, null=True, blank=True, related_name="metas")
	funcionario = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, null=True, blank=True, related_name="metas")
	objetivo = models.DecimalField(max_digits=10, decimal_places=2)
	ponderador = models.DecimalField(max_digits=5, decimal_places=2)
	version = models.PositiveIntegerField("versión", default=1)

	class Meta:
		verbose_name = "meta"
		verbose_name_plural = "metas"

	def clean(self):
		if self.objetivo <= 0:
			raise ValidationError("La meta debe ser mayor que cero.")
		if not self.cargo and not self.funcionario:
			raise ValidationError("La meta debe asociarse a un cargo o funcionario.")

	def __str__(self):
		return f"{self.item} - {self.periodo}"

	def _filtrar_responsable(self, queryset, campo):
		if self.funcionario_id:
			return queryset.filter(**{campo: self.funcionario})
		if self.cargo_id:
			return queryset.filter(**{f"{campo}__cargo": self.cargo})
		return queryset.none()

	def compromisos_del_periodo(self):
		compromisos = Compromiso.objects.filter(
			activo=True, fecha_comprometida__gte=self.periodo.fecha_inicio, fecha_comprometida__lte=self.periodo.fecha_termino,
		)
		# Las solicitudes cuyo responsable es el delegado no entran a la tasa del tubo.
		compromisos = compromisos.exclude(responsable__cargo__nombre__iexact="Delegado")
		return self._filtrar_responsable(compromisos, "responsable")

	@property
	def avance_aprobado(self):
		"""Avance en la unidad del ítem: actividades aprobadas o, en «tasa_tubo», % de ingresos al tubo realizados."""
		if self.item.tipo_medicion == "tasa_tubo":
			compromisos = self.compromisos_del_periodo()
			total = compromisos.count()
			return round(compromisos.filter(estado="realizado").count() * 100 / total, 2) if total else 0
		actividades = Actividad.objects.puntuables().filter(periodo=self.periodo, item=self.item)
		return self._filtrar_responsable(actividades, "funcionario").count()

	@property
	def cumplimiento(self):
		tipo = self.item.tipo_medicion
		if tipo == "sin_puntaje":
			return 0
		avance = self.avance_aprobado
		if tipo == "emergencia":
			if avance:
				return 100
			# Una ausencia baja el objetivo bajo 1: la fracción no exigida queda cubierta.
			exigencia = float(self.objetivo)
			if exigencia < 1:
				return min(100, (1 - exigencia) * 100)
			return 0
		return min((avance / float(self.objetivo)) * 100, float(self.periodo.tope_item))

	@property
	def resultado_ponderado(self):
		return float(self.ponderador) * self.cumplimiento / 100

	def semaforo(self, fecha=None):
		return self.periodo.semaforo(self.cumplimiento, fecha)


class ActividadQuerySet(models.QuerySet):
	def puntuables(self):
		"""Aprobado, con tareas hechas, nombre y teléfono, y cuyo funcionario no es el delegado.

		Sin nombre o sin teléfono no hay puntaje. Las actividades del cargo Delegado no contabilizan.
		"""
		return (
			self.filter(estado="validada")
			.exclude(tareas__realizada=False)
			.exclude(funcionario__cargo__nombre__iexact="Delegado")
			.exclude(solicitante="")
			.exclude(telefono="")
		)


class Actividad(models.Model):
	ESTADOS = [
		("pendiente", "Pendiente"),
		("validada", "Aprobada"),
		("rechazada", "Rechazada"),
		("antecedentes", "Solicitud de más antecedentes"),
		("anulada", "Anulada"),
	]
	codigo_evidencia = models.UUIDField("código de evidencia", default=uuid.uuid4, unique=True, editable=False)
	funcionario = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="actividades")
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="actividades", verbose_name="período")
	item = models.ForeignKey(ItemMedicion, on_delete=models.PROTECT, related_name="actividades", verbose_name="ítem de medición")
	servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, null=True, blank=True, related_name="actividades")
	compromiso = models.ForeignKey("Compromiso", on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades")
	codigo_verificador = models.CharField("código verificador", max_length=30, unique=True, null=True, blank=True, editable=False)
	fecha = models.DateField(default=timezone.now)
	descripcion = models.TextField("descripción")
	accion = models.TextField("acción")
	contacto = models.CharField(max_length=160, blank=True)
	telefono = models.CharField("teléfono", max_length=30, blank=True)
	solicitante = models.CharField(
		"solicitante",
		max_length=160,
		blank=True,
		help_text="Nombre de quien solicita. Si hay un ingreso al tubo, es el mismo nombre.",
	)
	derivado_a = models.ForeignKey("institucional.UnidadMunicipal", on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades_derivadas", verbose_name="derivado a")
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	creada_en = models.DateTimeField("registrada el", auto_now_add=True)
	revisada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades_revisadas", verbose_name="revisada por")
	revisada_en = models.DateTimeField("revisada el", null=True, blank=True)
	observacion_revision = models.TextField("observación de la revisión", blank=True)

	objects = ActividadQuerySet.as_manager()

	class Meta:
		verbose_name = "actividad"
		verbose_name_plural = "actividades"
		ordering = ["-fecha", "-creada_en"]
		permissions = [("aprobar_actividad", "Puede aprobar o rechazar actividades")]

	@property
	def total_tareas(self):
		return self.tareas.count()

	@property
	def tareas_realizadas(self):
		return self.tareas.filter(realizada=True).count()

	@property
	def tareas_completas(self):
		return not self.tareas.filter(realizada=False).exists()

	@property
	def puntua(self):
		return self.estado == "validada" and self.tareas_completas

	def clean(self):
		errores = {}
		if not (self.descripcion or "").strip():
			errores["descripcion"] = "Indica la actividad o el problema."
		if not (self.accion or "").strip():
			errores["accion"] = "Indica la acción realizada."
		telefono = (self.telefono or "").strip()
		self.telefono = telefono
		if telefono and not TELEFONO_ACTIVIDAD.match(telefono):
			errores["telefono"] = "El teléfono debe contener entre 8 y 15 dígitos."
		fecha = self.fecha.date() if isinstance(self.fecha, datetime) else self.fecha
		if self.periodo_id:
			if self.periodo.estado != "abierto":
				errores["periodo"] = "Solo se puede registrar en un período abierto."
			elif fecha and (fecha < self.periodo.fecha_inicio or fecha > self.periodo.fecha_termino):
				errores["fecha"] = "La fecha debe estar dentro del período seleccionado."
		if self.item_id and not self.item.activo:
			errores["item"] = "El ítem de medición no está vigente."
		if self.compromiso_id and self.funcionario_id and self.compromiso.delegacion_id != self.funcionario.delegacion_id:
			errores["compromiso"] = "El compromiso debe pertenecer a la misma delegación."
		nombre = (self.solicitante or "").strip()
		if self.compromiso_id:
			del_tubo = (self.compromiso.solicitante or "").strip()
			if not nombre:
				nombre = del_tubo
			elif nombre.casefold() != del_tubo.casefold():
				errores["solicitante"] = f"Debe coincidir con el solicitante del ingreso al tubo ({del_tubo})."
		if self.pk and nombre:
			gestion = Gestion.objects.filter(actividad_id=self.pk).select_related("caso").first()
			if gestion is not None:
				del_caso = (gestion.caso.solicitante or "").strip()
				if del_caso and nombre.casefold() != del_caso.casefold():
					errores["solicitante"] = f"Debe coincidir con el solicitante del caso ({del_caso})."
		if not nombre:
			errores["solicitante"] = "Indica el nombre del solicitante."
		else:
			self.solicitante = nombre
		if errores:
			raise ValidationError(errores)

	def save(self, *args, **kwargs):
		if self.pk:
			anterior = Actividad.objects.filter(pk=self.pk).values_list("codigo_evidencia", flat=True).first()
			if anterior and self.codigo_evidencia != anterior:
				raise ValidationError("El código de evidencia es inmutable y no se reutiliza.")
		if not self.codigo_verificador and self.funcionario_id and self.periodo_id:
			self.codigo_verificador = self._siguiente_codigo_verificador()
		super().save(*args, **kwargs)
		if self.pk and self.solicitante:
			Caso.objects.filter(gestiones__actividad_id=self.pk, solicitante="").update(solicitante=self.solicitante)
			from .personas import recordar_persona

			recordar_persona(self.funcionario.delegacion, self.solicitante, "", self.telefono)

	@classmethod
	def asignar_codigos_pendientes(cls):
		"""Da código verificador a las actividades anteriores a la matriz cuyo funcionario ya tiene sigla."""
		asignados = 0
		for actividad in cls.objects.filter(codigo_verificador__isnull=True).select_related("funcionario__cargo").order_by("fecha", "pk"):
			codigo = actividad._siguiente_codigo_verificador()
			if codigo:
				actividad.codigo_verificador = codigo
				actividad.save(update_fields=["codigo_verificador"])
				asignados += 1
		return asignados

	def _siguiente_codigo_verificador(self):
		"""Código de la matriz: área + mes + día + correlativo del área en el período (COM1-1006-004)."""
		prefijo = self.funcionario.prefijo_codigo
		if not prefijo:
			return None
		fecha = self.fecha.date() if isinstance(self.fecha, datetime) else self.fecha
		usados = Actividad.objects.filter(periodo_id=self.periodo_id, codigo_verificador__startswith=f"{prefijo}-").count()
		correlativo = usados + 1
		while True:
			codigo = f"{prefijo}-{fecha:%m%d}-{correlativo:03d}"
			if not Actividad.objects.filter(codigo_verificador=codigo).exists():
				return codigo
			correlativo += 1

	def __str__(self):
		return f"{self.codigo_verificador or self.codigo_evidencia} - {self.funcionario.nombre_completo}"


class TareaPreparatoria(models.Model):
	"""Tarea escrita por quien registra la actividad. Nunca suma al cumplimiento por sí sola.

	No hay catálogo ni desplegable: el texto es la tarea (por ejemplo «Gestión de sillas»).
	El campo tipo queda fijo en «otra» para las filas antiguas; no se elige.
	"""

	TIPOS = [("otra", "Otra gestión")]
	actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="tareas")
	tipo = models.CharField(
		"tipo de gestión",
		max_length=20,
		choices=TIPOS,
		default="otra",
		error_messages={"invalid_choice": "La única opción es «Otra gestión». Escribe el nombre de la tarea en el texto."},
	)
	descripcion = models.CharField(
		"gestión",
		max_length=280,
		error_messages={"blank": "Escribe la gestión, por ejemplo «Gestión de sillas»."},
	)
	realizada = models.BooleanField(default=False)
	realizada_en = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["pk"]
		verbose_name = "tarea preparatoria"
		verbose_name_plural = "tareas preparatorias"

	def clean(self):
		self.descripcion = (self.descripcion or "").strip()
		if not self.descripcion:
			raise ValidationError({"descripcion": "Escribe la gestión, por ejemplo «Gestión de sillas»."})

	def __str__(self):
		return self.descripcion or self.get_tipo_display()


TIPOS_ATENCION_SOCIAL = [
	("informes_sociales", "Informes sociales"),
	("gestion_subsidios", "Gestión de subsidios"),
	("derivaciones", "Derivaciones"),
	("otras_gestiones", "Otras gestiones sociales"),
	("entrega_emergencia", "Entrega de emergencia"),
]
SUBATENCIONES_SOCIALES = [
	("informe_aporte_economico", "Informe aporte económico"),
	("informe_aporte_material", "Informe aporte material"),
	("informe_institucion", "Informe institución"),
	("ips", "IPS"),
	("pgu", "PGU"),
	("suf", "SUF"),
	("sap", "SAP"),
	("derivacion", "Derivación a otra unidad"),
	("orientacion_social", "Orientación social"),
	("exencion_aseo", "Exención pago aseo domiciliario"),
	("emergencia", "Emergencia"),
	("otros", "Otros"),
]
SUBATENCIONES_POR_TIPO = {
	"informes_sociales": ("informe_aporte_economico", "informe_aporte_material", "informe_institucion"),
	"gestion_subsidios": ("ips", "pgu", "suf", "sap"),
	"derivaciones": ("derivacion",),
	"otras_gestiones": ("orientacion_social", "exencion_aseo", "otros"),
	"entrega_emergencia": ("emergencia",),
}
FORMA_POR_SUBATENCION = {
	"informe_aporte_economico": "Dinero",
	"informe_aporte_material": "Material",
	"informe_institucion": "Documento",
	"ips": "Documento",
	"pgu": "Aporte",
	"suf": "Aporte",
	"sap": "Aporte",
}
class TipoAtencion(models.Model):
	"""Tipo de atención social. El mantenedor reemplaza la lista fija."""

	codigo = models.SlugField("código", max_length=40, unique=True)
	nombre = models.CharField(max_length=120, unique=True)
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "tipo de atención"
		verbose_name_plural = "tipos de atención"
		ordering = ["nombre"]

	def __str__(self):
		return self.nombre


class SubtipoAtencion(models.Model):
	tipo = models.ForeignKey(TipoAtencion, on_delete=models.PROTECT, related_name="subtipos")
	codigo = models.SlugField("código", max_length=40)
	nombre = models.CharField(max_length=120)
	forma = models.CharField("forma de entrega", max_length=40, blank=True)
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "subtipo de atención"
		verbose_name_plural = "subtipos de atención"
		ordering = ["tipo__nombre", "nombre"]
		constraints = [
			models.UniqueConstraint(fields=["tipo", "codigo"], name="subtipo_codigo_unico_por_tipo"),
		]

	def __str__(self):
		return f"{self.tipo.nombre} · {self.nombre}"


def _subtipo_corresponde(tipo_codigo, sub_codigo):
	subtipo = SubtipoAtencion.objects.filter(codigo=sub_codigo).select_related("tipo").first()
	if subtipo is not None:
		return subtipo.tipo.codigo == tipo_codigo and subtipo.activo and subtipo.tipo.activo
	return sub_codigo in SUBATENCIONES_POR_TIPO.get(tipo_codigo, ())


# Plazos de las hojas de Gestor Social: (desde, hasta, días máximos, etiqueta).
PLAZOS_ATENCION_SOCIAL = (
	("fecha_ingreso", "fecha_programada_visita", 10, "Ingreso a visita programada"),
	("fecha_programada_visita", "fecha_visita", 0, "Visita programada a visita realizada"),
	("fecha_visita", "fecha_entrega_informe", 4, "Visita a entrega del informe"),
	("fecha_entrega_informe", "fecha_entrega_beneficio", 4, "Informe a entrega del beneficio"),
	("fecha_ingreso", "fecha_entrega_beneficio", 20, "Ingreso a entrega del beneficio"),
)


class Caso(models.Model):
	identificacion = models.CharField("identificación", max_length=30, unique=True)
	nombre = models.CharField(max_length=160)
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="casos")
	tipo_atencion = models.CharField("tipo de atención", max_length=40, blank=True)
	sub_atencion = models.CharField("subatención", max_length=40, blank=True)
	rut = models.CharField("RUT", max_length=12, blank=True)
	telefono = models.CharField("teléfono", max_length=30, blank=True)
	solicitante = models.CharField(
		"solicitante",
		max_length=160,
		blank=True,
		help_text="Nombre de quien solicita. Es el mismo de la actividad y del ingreso al tubo cuando están asociados.",
	)
	requiere_visita = models.BooleanField("requiere visita", default=False)
	fecha_ingreso = models.DateField("fecha de ingreso", default=timezone.localdate)
	fecha_programada_visita = models.DateField("fecha programada de visita", null=True, blank=True)
	fecha_visita = models.DateField("fecha de visita", null=True, blank=True)
	fecha_entrega_informe = models.DateField("fecha de entrega del informe", null=True, blank=True)
	fecha_entrega_beneficio = models.DateField("fecha de entrega del beneficio", null=True, blank=True)
	devoluciones_informe = models.PositiveSmallIntegerField("devoluciones del informe", default=0)
	observacion = models.TextField("observación", blank=True)
	activo = models.BooleanField(default=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["nombre"]
		verbose_name = "caso de atención"
		verbose_name_plural = "casos de atención"

	def __str__(self):
		return f"{self.identificacion} — {self.nombre}"

	@property
	def gestiones_vigentes(self):
		return self.gestiones.filter(activa=True).order_by("numero")

	def atenciones_contadas(self):
		"""Cada gestión vigente aporta una sola vez al informe del caso."""
		return self.gestiones_vigentes.count()

	def get_tipo_atencion_display(self):
		tipo = TipoAtencion.objects.filter(codigo=self.tipo_atencion).first()
		if tipo is not None:
			return tipo.nombre
		return dict(TIPOS_ATENCION_SOCIAL).get(self.tipo_atencion, self.tipo_atencion)

	def get_sub_atencion_display(self):
		subtipo = SubtipoAtencion.objects.filter(codigo=self.sub_atencion).first()
		if subtipo is not None:
			return subtipo.nombre
		return dict(SUBATENCIONES_SOCIALES).get(self.sub_atencion, self.sub_atencion)

	@property
	def forma(self):
		subtipo = SubtipoAtencion.objects.filter(codigo=self.sub_atencion).first()
		if subtipo is not None and subtipo.forma:
			return subtipo.forma
		return FORMA_POR_SUBATENCION.get(self.sub_atencion, "")

	def plazos(self):
		"""Tramos de la atención social con sus días y si exceden el máximo de la matriz."""
		tramos = []
		for desde, hasta, maximo, etiqueta in PLAZOS_ATENCION_SOCIAL:
			inicio, fin = getattr(self, desde), getattr(self, hasta)
			if inicio and fin:
				dias = (fin - inicio).days
				tramos.append({"etiqueta": etiqueta, "dias": dias, "maximo": maximo, "excedido": dias > maximo})
		return tramos

	@property
	def plazos_excedidos(self):
		return [tramo for tramo in self.plazos() if tramo["excedido"]]

	def clean(self):
		from laserena.rut import normalizar_rut

		errores = {}
		if self.sub_atencion and not self.tipo_atencion:
			errores["tipo_atencion"] = "Indica el tipo de atención de la subatención."
		elif self.sub_atencion and not _subtipo_corresponde(self.tipo_atencion, self.sub_atencion):
			errores["sub_atencion"] = "La subatención no corresponde al tipo de atención elegido."
		if self.rut:
			try:
				self.rut = normalizar_rut(self.rut)
			except ValidationError as error:
				errores["rut"] = error.messages
		telefono = (self.telefono or "").strip()
		if telefono and not TELEFONO_ACTIVIDAD.match(telefono):
			errores["telefono"] = "El teléfono debe contener entre 8 y 15 dígitos."
		orden = ("fecha_ingreso", "fecha_programada_visita", "fecha_visita", "fecha_entrega_informe", "fecha_entrega_beneficio")
		anteriores = []
		for campo in orden:
			valor = getattr(self, campo)
			if valor and any(valor < previo for previo in anteriores):
				errores[campo] = "Esta fecha no puede ser anterior a las etapas previas de la atención."
			if valor:
				anteriores.append(valor)
		if (self.fecha_programada_visita or self.fecha_visita) and not self.requiere_visita:
			errores["requiere_visita"] = "Marca «requiere visita» si registras fechas de visita."
		if errores:
			raise ValidationError(errores)

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)
		from .personas import recordar_persona

		recordar_persona(self.delegacion, self.solicitante, self.rut, self.telefono)


class Gestion(models.Model):
	caso = models.ForeignKey(Caso, on_delete=models.CASCADE, related_name="gestiones")
	actividad = models.OneToOneField(Actividad, on_delete=models.PROTECT, null=True, blank=True, related_name="gestion")
	numero = models.PositiveSmallIntegerField("número")
	fecha = models.DateField(default=timezone.now)
	descripcion = models.TextField("descripción")
	activa = models.BooleanField(default=True)

	class Meta:
		ordering = ["numero"]
		verbose_name = "gestión de atención"
		verbose_name_plural = "gestiones de atención"
		constraints = [
			models.UniqueConstraint(fields=["caso", "numero"], name="gestion_numero_unico_por_caso"),
			models.CheckConstraint(check=models.Q(numero__gte=1) & models.Q(numero__lte=MAXIMO_GESTIONES_POR_CASO), name="gestion_numero_entre_1_y_3"),
		]

	def clean(self):
		errores = {}
		if self.numero < 1 or self.numero > MAXIMO_GESTIONES_POR_CASO:
			errores["numero"] = "La gestión debe numerarse entre 1 y 3."
		if self.caso_id:
			existentes = Gestion.objects.filter(caso_id=self.caso_id)
			if self.pk:
				existentes = existentes.exclude(pk=self.pk)
			if existentes.count() >= MAXIMO_GESTIONES_POR_CASO:
				raise ValidationError("Un caso admite como máximo tres gestiones.")
			if self.numero and existentes.filter(numero=self.numero).exists():
				errores["numero"] = "Ese número de gestión ya está usado en el caso."
		if self.actividad_id and self.caso_id and self.actividad.funcionario.delegacion_id != self.caso.delegacion_id:
			errores["actividad"] = "La actividad debe ser de la misma delegación del caso."
		if self.actividad_id and self.caso_id:
			nombre_act = (self.actividad.solicitante or "").strip()
			if not nombre_act and self.actividad.compromiso_id:
				nombre_act = (self.actividad.compromiso.solicitante or "").strip()
			nombre_caso = (self.caso.solicitante or "").strip()
			if nombre_act and nombre_caso and nombre_act.casefold() != nombre_caso.casefold():
				errores["actividad"] = f"El solicitante del caso ({nombre_caso}) debe coincidir con el de la actividad ({nombre_act})."
		if errores:
			raise ValidationError(errores)

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)
		if not self.actividad_id or not self.caso_id:
			return
		nombre_act = (self.actividad.solicitante or "").strip()
		if not nombre_act and self.actividad.compromiso_id:
			nombre_act = (self.actividad.compromiso.solicitante or "").strip()
		nombre_caso = (self.caso.solicitante or "").strip()
		if nombre_act and not nombre_caso:
			Caso.objects.filter(pk=self.caso_id).update(solicitante=nombre_act)
		elif nombre_caso and not nombre_act:
			Actividad.objects.filter(pk=self.actividad_id).update(solicitante=nombre_caso)

	def __str__(self):
		return f"Gestión {self.numero} de {self.caso.identificacion}"


class Evidencia(models.Model):
	"""Captura del trabajo ya hecho. Acredita una actividad y el texto de una de sus tareas."""

	ESTADOS = [
		("pendiente", "Pendiente"),
		("aprobada", "Aprobada"),
		("rechazada", "Rechazada"),
		("antecedentes", "Solicitud de más antecedentes"),
	]
	actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="evidencias")
	tarea = models.ForeignKey(
		TareaPreparatoria,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="evidencias",
		verbose_name="tarea que acredita",
	)
	texto_tarea = models.CharField(
		"tarea que acredita",
		max_length=280,
		blank=True,
		default="",
		help_text="Texto de la tarea al momento de adjuntar la captura. No cambia si después se edita la tarea.",
	)
	archivo = models.FileField(
		"captura",
		upload_to="evidencias/%Y/%m/",
		validators=[FileExtensionValidator(EXTENSIONES_EVIDENCIA), validar_imagen_evidencia],
	)
	autor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="evidencias_cargadas")
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	observacion = models.TextField("motivo del rechazo", blank=True)
	cargada_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = "evidencia"
		verbose_name_plural = "evidencias"
		ordering = ["-cargada_en"]
		permissions = [("aprobar_evidencia", "Puede aprobar o rechazar evidencias")]

	def clean(self):
		errores = {}
		if self.tarea_id and self.actividad_id and self.tarea.actividad_id != self.actividad_id:
			errores["tarea"] = "La tarea debe pertenecer a la actividad."
		if self.tarea_id and not (self.texto_tarea or "").strip():
			self.texto_tarea = self.tarea.descripcion
		self.texto_tarea = (self.texto_tarea or "").strip()
		self.observacion = (self.observacion or "").strip()
		if not self.pk:
			if self.actividad_id and self.actividad.estado == "anulada":
				errores["actividad"] = "No se adjunta evidencia a una actividad anulada."
			if self.tarea_id and not self.tarea.realizada:
				errores["texto_tarea"] = "Solo puedes adjuntar la captura de una tarea ya realizada."
			if self.estado == "pendiente" and self.tarea_id and Evidencia.objects.filter(tarea_id=self.tarea_id, estado="pendiente").exists():
				errores["texto_tarea"] = "Esta tarea ya tiene una evidencia pendiente de revisión."
			elif (
				self.estado == "pendiente"
				and not self.tarea_id
				and self.actividad_id
				and self.texto_tarea
				and Evidencia.objects.filter(actividad_id=self.actividad_id, texto_tarea__iexact=self.texto_tarea, estado="pendiente").exists()
			):
				errores["texto_tarea"] = "Esta tarea ya tiene una evidencia pendiente de revisión."
		if not self.texto_tarea:
			errores["texto_tarea"] = "Escribe la tarea que esta captura acredita."
		if self.estado in ("rechazada", "antecedentes"):
			etiqueta = "del rechazo" if self.estado == "rechazada" else "de la solicitud de antecedentes"
			if not self.observacion:
				errores["observacion"] = f"Indica un motivo breve {etiqueta}."
			elif len(self.observacion) > MOTIVO_RECHAZO_MAX:
				errores["observacion"] = "El motivo no puede superar los 280 caracteres."
		elif self.estado not in ("pendiente", "aprobada"):
			errores["estado"] = "El estado debe ser pendiente, aprobada, rechazada o solicitud de más antecedentes."
		if errores:
			raise ValidationError(errores)

	def __str__(self):
		return f"Evidencia de {self.texto_tarea or self.actividad}"


class Validacion(models.Model):
	DECISIONES = [
		("aprobada", "Aprobada"),
		("rechazada", "Rechazada"),
		("antecedentes", "Solicitud de más antecedentes"),
	]
	evidencia = models.ForeignKey(Evidencia, on_delete=models.CASCADE, related_name="validaciones")
	verificador = models.ForeignKey(User, on_delete=models.PROTECT, related_name="validaciones_realizadas")
	decision = models.CharField("decisión", max_length=20, choices=DECISIONES)
	observacion = models.TextField("observación", blank=True)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = "validación"
		verbose_name_plural = "validaciones"


class Compromiso(models.Model):
	"""Ingreso al tubo de trabajo de la delegación."""

	ESTADOS = [("ingresado", "Ingresado"), ("pendiente", "Pendiente"), ("proceso", "En proceso"), ("realizado", "Realizado")]
	AMBITOS = [("interno", "Interno (INT)"), ("externo", "Externo (EXT)")]
	codigo = models.CharField("código", max_length=20, unique=True, null=True, blank=True, editable=False)
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="compromisos")
	responsable = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="compromisos")
	fecha_solicitud = models.DateField("fecha de solicitud", default=timezone.localdate)
	ambito = models.CharField("interno o externo", max_length=10, choices=AMBITOS, default="externo")
	origen = models.CharField(max_length=160)
	solicitante = models.CharField(max_length=160)
	rut = models.CharField("RUT", max_length=12, blank=True)
	telefono = models.CharField("teléfono", max_length=30, blank=True)
	territorio = models.CharField(max_length=160)
	area_apoyo = models.ForeignKey("institucional.UnidadMunicipal", on_delete=models.SET_NULL, null=True, blank=True, related_name="compromisos_apoyados", verbose_name="área de apoyo")
	descripcion = models.TextField("descripción")
	fecha_comprometida = models.DateField()
	estado = models.CharField(max_length=20, choices=ESTADOS, default="ingresado")
	observacion = models.TextField("observación", blank=True)
	activo = models.BooleanField(default=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = "compromiso"
		verbose_name_plural = "compromisos"
		ordering = ["fecha_comprometida", "creado_en"]

	@property
	def vencido(self):
		return self.estado != "realizado" and self.fecha_comprometida < timezone.localdate()

	def transiciones_disponibles(self):
		return TRANSICIONES_COMPROMISO.get(self.estado, set())

	def puede_transitar(self, estado_nuevo):
		return estado_nuevo == self.estado or estado_nuevo in self.transiciones_disponibles()

	def aplicar_estado(self, estado_nuevo, autor, observacion=""):
		"""Cambia el estado solo si la transición está permitida y deja historial.

		No abre un flujo aparte: es la validación del mantenedor al editar el registro.
		"""
		if not self.puede_transitar(estado_nuevo):
			etiqueta = dict(self.ESTADOS).get(estado_nuevo, estado_nuevo)
			raise ValidationError({"estado": f"No se puede pasar de {self.get_estado_display()} a {etiqueta}."})
		anterior = self.estado
		self.estado = estado_nuevo
		self.save()
		if anterior != estado_nuevo:
			HistorialCompromiso.objects.create(
				compromiso=self,
				estado_anterior=anterior,
				estado_nuevo=estado_nuevo,
				autor=autor,
				observacion=observacion,
			)
		return self

	def clean(self):
		from laserena.rut import normalizar_rut

		errores = {}
		if self.rut:
			try:
				self.rut = normalizar_rut(self.rut)
			except ValidationError as error:
				errores["rut"] = error.messages
		telefono = (self.telefono or "").strip()
		self.telefono = telefono
		if telefono and not TELEFONO_ACTIVIDAD.match(telefono):
			errores["telefono"] = "El teléfono debe contener entre 8 y 15 dígitos."
		if not (self.solicitante or "").strip():
			errores["solicitante"] = "Indica el nombre del solicitante."
		if errores:
			raise ValidationError(errores)

	def save(self, *args, **kwargs):
		self.solicitante = (self.solicitante or "").strip()
		super().save(*args, **kwargs)
		if not self.codigo and self.pk:
			anio = (self.fecha_solicitud or timezone.localdate()).year
			self.codigo = f"TB-{anio}-{self.pk:04d}"
			super().save(update_fields=["codigo"])
		if not self.pk or not self.solicitante:
			return
		Actividad.objects.filter(compromiso_id=self.pk).exclude(solicitante=self.solicitante).update(solicitante=self.solicitante)
		Caso.objects.filter(gestiones__actividad__compromiso_id=self.pk).exclude(solicitante=self.solicitante).update(solicitante=self.solicitante)
		from .personas import recordar_persona

		recordar_persona(self.delegacion, self.solicitante, self.rut, self.telefono)

	@property
	def fuera_de_plazo(self):
		cierre = self.historial.filter(estado_nuevo="realizado").order_by("fecha").first()
		if cierre is None:
			return self.vencido
		return timezone.localtime(cierre.fecha).date() > self.fecha_comprometida

	def __str__(self):
		return f"{self.solicitante} - {self.fecha_comprometida}"


class HistorialCompromiso(models.Model):
	compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name="historial")
	estado_anterior = models.CharField("estado anterior", max_length=20, blank=True)
	estado_nuevo = models.CharField("estado nuevo", max_length=20)
	autor = models.ForeignKey(User, on_delete=models.PROTECT)
	observacion = models.TextField("observación", blank=True)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = "historial de compromiso"
		verbose_name_plural = "historiales de compromiso"
		ordering = ["fecha"]


class Auditoria(models.Model):
	usuario = models.ForeignKey(User, on_delete=models.PROTECT)
	accion = models.CharField("acción", max_length=80)
	entidad = models.CharField(max_length=120)
	identificador = models.CharField(max_length=80)
	valor_anterior = models.JSONField("valor anterior", null=True, blank=True)
	valor_nuevo = models.JSONField("valor nuevo", null=True, blank=True)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name = "registro de auditoría"
		verbose_name_plural = "registros de auditoría"
		ordering = ["-fecha"]
