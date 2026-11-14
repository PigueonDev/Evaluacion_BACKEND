import re
import uuid
from datetime import datetime

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
from django.utils import timezone


User = get_user_model()

EXTENSIONES_EVIDENCIA = ["pdf", "jpg", "jpeg", "png", "webp"]
TAMANO_MAXIMO_EVIDENCIA = 5 * 1024 * 1024
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


class Servicio(models.Model):
	slug = models.SlugField(max_length=120, unique=True)
	nombre = models.CharField(max_length=160)
	categoria = models.CharField(max_length=80)
	unidad = models.CharField(max_length=160)
	descripcion = models.TextField()
	activo = models.BooleanField(default=True)

	class Meta:
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
	codigo = models.CharField(max_length=30, unique=True)
	nombre = models.CharField(max_length=160)
	descripcion = models.TextField(blank=True)
	unidad = models.CharField(max_length=40, default="cantidad")
	tipo_medicion = models.CharField("tipo de medición", max_length=20, choices=TIPOS_MEDICION, default="conteo")
	activo = models.BooleanField(default=True)

	class Meta:
		ordering = ["codigo"]

	def __str__(self):
		return f"{self.codigo} - {self.nombre}"


class Periodo(models.Model):
	ESTADOS = [("abierto", "Abierto"), ("cerrado", "Cerrado")]
	nombre = models.CharField(max_length=120, unique=True)
	fecha_inicio = models.DateField()
	fecha_termino = models.DateField()
	estado = models.CharField(max_length=20, choices=ESTADOS, default="abierto")
	tope_cumplimiento = models.DecimalField(max_digits=5, decimal_places=2, default=150)
	tope_item = models.DecimalField(max_digits=5, decimal_places=2, default=120)
	umbral_colectivo = models.DecimalField(max_digits=5, decimal_places=2, default=80)
	umbral_ambar = models.DecimalField(max_digits=5, decimal_places=2, default=60)
	bono_felicitacion = models.DecimalField("puntos por felicitación", max_digits=5, decimal_places=2, default=10)
	maximo_felicitaciones = models.PositiveSmallIntegerField("felicitaciones que suman como máximo", default=3)
	descuento_reclamo = models.DecimalField("puntos que descuenta cada reclamo", max_digits=5, decimal_places=2, default=20)

	class Meta:
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
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="metas")
	item = models.ForeignKey(ItemMedicion, on_delete=models.PROTECT, related_name="metas")
	cargo = models.ForeignKey("institucional.Cargo", on_delete=models.PROTECT, null=True, blank=True, related_name="metas")
	funcionario = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, null=True, blank=True, related_name="metas")
	objetivo = models.DecimalField(max_digits=10, decimal_places=2)
	ponderador = models.DecimalField(max_digits=5, decimal_places=2)
	version = models.PositiveIntegerField(default=1)

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
			return 100 if avance else 0
		return min((avance / float(self.objetivo)) * 100, float(self.periodo.tope_item))

	@property
	def resultado_ponderado(self):
		return float(self.ponderador) * self.cumplimiento / 100

	def semaforo(self, fecha=None):
		return self.periodo.semaforo(self.cumplimiento, fecha)


class ActividadQuerySet(models.QuerySet):
	def puntuables(self):
		"""Solo suma al cumplimiento lo aprobado por el Supervisor y con todas sus tareas realizadas."""
		return self.filter(estado="validada").exclude(tareas__realizada=False)


class Actividad(models.Model):
	ESTADOS = [("pendiente", "Pendiente"), ("validada", "Aprobada"), ("rechazada", "Rechazada"), ("anulada", "Anulada")]
	codigo_evidencia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	funcionario = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="actividades")
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="actividades")
	item = models.ForeignKey(ItemMedicion, on_delete=models.PROTECT, related_name="actividades")
	servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, null=True, blank=True, related_name="actividades")
	compromiso = models.ForeignKey("Compromiso", on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades")
	codigo_verificador = models.CharField("código verificador", max_length=30, unique=True, null=True, blank=True, editable=False)
	fecha = models.DateField(default=timezone.now)
	descripcion = models.TextField()
	accion = models.TextField()
	contacto = models.CharField(max_length=160, blank=True)
	telefono = models.CharField(max_length=30, blank=True)
	derivado_a = models.ForeignKey("institucional.UnidadMunicipal", on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades_derivadas", verbose_name="derivado a")
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	creada_en = models.DateTimeField(auto_now_add=True)
	revisada_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades_revisadas")
	revisada_en = models.DateTimeField(null=True, blank=True)
	observacion_revision = models.TextField(blank=True)

	objects = ActividadQuerySet.as_manager()

	class Meta:
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
	"""Gestión previa a la actividad (sillas, colación, regalos...). Nunca suma al cumplimiento por sí sola."""

	TIPOS = [
		("sillas", "Solicitar sillas y mesas"),
		("colacion", "Solicitar colación"),
		("regalos", "Solicitar regalos"),
		("local", "Reservar local o espacio"),
		("animacion", "Contratar animadores o artistas"),
		("difusion", "Difusión e invitaciones"),
		("otra", "Otra gestión"),
	]
	actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="tareas")
	tipo = models.CharField(max_length=20, choices=TIPOS)
	descripcion = models.CharField(max_length=200, blank=True)
	realizada = models.BooleanField(default=False)
	realizada_en = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["pk"]
		verbose_name = "tarea preparatoria"
		verbose_name_plural = "tareas preparatorias"

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
# Plazos de las hojas de Gestor Social: (desde, hasta, días máximos, etiqueta).
PLAZOS_ATENCION_SOCIAL = (
	("fecha_ingreso", "fecha_programada_visita", 10, "Ingreso a visita programada"),
	("fecha_programada_visita", "fecha_visita", 0, "Visita programada a visita realizada"),
	("fecha_visita", "fecha_entrega_informe", 4, "Visita a entrega del informe"),
	("fecha_entrega_informe", "fecha_entrega_beneficio", 4, "Informe a entrega del beneficio"),
	("fecha_ingreso", "fecha_entrega_beneficio", 20, "Ingreso a entrega del beneficio"),
)


class Caso(models.Model):
	identificacion = models.CharField(max_length=30, unique=True)
	nombre = models.CharField(max_length=160)
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="casos")
	tipo_atencion = models.CharField("tipo de atención", max_length=30, choices=TIPOS_ATENCION_SOCIAL, blank=True)
	sub_atencion = models.CharField("subatención", max_length=30, choices=SUBATENCIONES_SOCIALES, blank=True)
	rut = models.CharField("RUT", max_length=12, blank=True)
	telefono = models.CharField("teléfono", max_length=30, blank=True)
	requiere_visita = models.BooleanField("requiere visita", default=False)
	fecha_ingreso = models.DateField("fecha de ingreso", default=timezone.localdate)
	fecha_programada_visita = models.DateField("fecha programada de visita", null=True, blank=True)
	fecha_visita = models.DateField("fecha de visita", null=True, blank=True)
	fecha_entrega_informe = models.DateField("fecha de entrega del informe", null=True, blank=True)
	fecha_entrega_beneficio = models.DateField("fecha de entrega del beneficio", null=True, blank=True)
	devoluciones_informe = models.PositiveSmallIntegerField("devoluciones del informe", default=0)
	observacion = models.TextField(blank=True)
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

	@property
	def forma(self):
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
		elif self.sub_atencion and self.sub_atencion not in SUBATENCIONES_POR_TIPO.get(self.tipo_atencion, ()):
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


class Gestion(models.Model):
	caso = models.ForeignKey(Caso, on_delete=models.CASCADE, related_name="gestiones")
	actividad = models.OneToOneField(Actividad, on_delete=models.PROTECT, null=True, blank=True, related_name="gestion")
	numero = models.PositiveSmallIntegerField()
	fecha = models.DateField(default=timezone.now)
	descripcion = models.TextField()
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
		if errores:
			raise ValidationError(errores)

	def __str__(self):
		return f"Gestión {self.numero} de {self.caso.identificacion}"


class Evidencia(models.Model):
	ESTADOS = [("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada"), ("correccion", "Solicita corrección")]
	actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="evidencias")
	archivo = models.FileField(
		upload_to="evidencias/%Y/%m/",
		validators=[FileExtensionValidator(EXTENSIONES_EVIDENCIA), validar_tamano_evidencia],
	)
	autor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="evidencias_cargadas")
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	observacion = models.TextField(blank=True)
	cargada_en = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"Evidencia de {self.actividad.codigo_evidencia}"


class Validacion(models.Model):
	DECISIONES = [("aprobada", "Aprobada"), ("rechazada", "Rechazada"), ("correccion", "Solicita corrección")]
	evidencia = models.ForeignKey(Evidencia, on_delete=models.CASCADE, related_name="validaciones")
	verificador = models.ForeignKey(User, on_delete=models.PROTECT, related_name="validaciones_realizadas")
	decision = models.CharField(max_length=20, choices=DECISIONES)
	observacion = models.TextField(blank=True)
	fecha = models.DateTimeField(auto_now_add=True)


class Compromiso(models.Model):
	"""Ingreso al tubo de trabajo de la delegación."""

	ESTADOS = [("ingresado", "Ingresado"), ("pendiente", "Pendiente"), ("proceso", "En proceso"), ("realizado", "Realizado")]
	AMBITOS = [("interno", "Interno (INT)"), ("externo", "Externo (EXT)")]
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="compromisos")
	responsable = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="compromisos")
	fecha_solicitud = models.DateField("fecha de solicitud", default=timezone.localdate)
	ambito = models.CharField("interno o externo", max_length=10, choices=AMBITOS, default="externo")
	origen = models.CharField(max_length=160)
	solicitante = models.CharField(max_length=160)
	territorio = models.CharField(max_length=160)
	area_apoyo = models.ForeignKey("institucional.UnidadMunicipal", on_delete=models.SET_NULL, null=True, blank=True, related_name="compromisos_apoyados", verbose_name="área de apoyo")
	descripcion = models.TextField()
	fecha_comprometida = models.DateField()
	estado = models.CharField(max_length=20, choices=ESTADOS, default="ingresado")
	observacion = models.TextField(blank=True)
	activo = models.BooleanField(default=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	class Meta:
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
	estado_anterior = models.CharField(max_length=20, blank=True)
	estado_nuevo = models.CharField(max_length=20)
	autor = models.ForeignKey(User, on_delete=models.PROTECT)
	observacion = models.TextField(blank=True)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["fecha"]


class Auditoria(models.Model):
	usuario = models.ForeignKey(User, on_delete=models.PROTECT)
	accion = models.CharField(max_length=80)
	entidad = models.CharField(max_length=120)
	identificador = models.CharField(max_length=80)
	valor_anterior = models.JSONField(null=True, blank=True)
	valor_nuevo = models.JSONField(null=True, blank=True)
	fecha = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-fecha"]
