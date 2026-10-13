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
	codigo = models.CharField(max_length=30, unique=True)
	nombre = models.CharField(max_length=160)
	descripcion = models.TextField(blank=True)
	unidad = models.CharField(max_length=40, default="cantidad")
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
	umbral_colectivo = models.DecimalField(max_digits=5, decimal_places=2, default=80)
	umbral_ambar = models.DecimalField(max_digits=5, decimal_places=2, default=60)

	def clean(self):
		if self.fecha_termino < self.fecha_inicio:
			raise ValidationError("La fecha de término no puede ser anterior al inicio.")

	@property
	def dias_totales(self):
		return (self.fecha_termino - self.fecha_inicio).days + 1

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

	@property
	def avance_aprobado(self):
		actividades = Actividad.objects.filter(periodo=self.periodo, item=self.item, estado="validada")
		if self.funcionario_id:
			actividades = actividades.filter(funcionario=self.funcionario)
		elif self.cargo_id:
			actividades = actividades.filter(funcionario__cargo=self.cargo)
		return actividades.count()

	@property
	def cumplimiento(self):
		return min((self.avance_aprobado / float(self.objetivo)) * 100, float(self.periodo.tope_cumplimiento))

	@property
	def resultado_ponderado(self):
		return float(self.ponderador) * self.cumplimiento / 100

	def semaforo(self, fecha=None):
		fecha = fecha or timezone.localdate()
		if fecha <= self.periodo.fecha_inicio:
			esperado = 0
		elif fecha >= self.periodo.fecha_termino:
			esperado = 100
		else:
			transcurridos = (fecha - self.periodo.fecha_inicio).days + 1
			esperado = transcurridos / self.periodo.dias_totales * 100
		if self.cumplimiento >= esperado:
			return "verde"
		if self.cumplimiento >= esperado * float(self.periodo.umbral_ambar) / 100:
			return "ambar"
		return "rojo"


class Actividad(models.Model):
	ESTADOS = [("pendiente", "Pendiente"), ("validada", "Validada"), ("rechazada", "Rechazada"), ("anulada", "Anulada")]
	codigo_evidencia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
	funcionario = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="actividades")
	periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="actividades")
	item = models.ForeignKey(ItemMedicion, on_delete=models.PROTECT, related_name="actividades")
	servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, null=True, blank=True, related_name="actividades")
	compromiso = models.ForeignKey("Compromiso", on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades")
	fecha = models.DateField(default=timezone.now)
	descripcion = models.TextField()
	accion = models.TextField()
	contacto = models.CharField(max_length=160, blank=True)
	telefono = models.CharField(max_length=30, blank=True)
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	creada_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-fecha", "-creada_en"]

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
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.codigo_evidencia} - {self.funcionario.nombre_completo}"


class Caso(models.Model):
	identificacion = models.CharField(max_length=30, unique=True)
	nombre = models.CharField(max_length=160)
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="casos")
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
	ESTADOS = [("ingresado", "Ingresado"), ("pendiente", "Pendiente"), ("proceso", "En proceso"), ("realizado", "Realizado")]
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="compromisos")
	responsable = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="compromisos")
	origen = models.CharField(max_length=160)
	solicitante = models.CharField(max_length=160)
	territorio = models.CharField(max_length=160)
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
