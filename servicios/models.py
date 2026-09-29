from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid


User = get_user_model()


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
	fecha = models.DateField(default=timezone.now)
	descripcion = models.TextField()
	accion = models.TextField()
	contacto = models.CharField(max_length=160, blank=True)
	telefono = models.CharField(max_length=30, blank=True)
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	creada_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-fecha", "-creada_en"]

	def __str__(self):
		return f"{self.codigo_evidencia} - {self.funcionario.nombre_completo}"


class Evidencia(models.Model):
	ESTADOS = [("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada"), ("correccion", "Solicita corrección")]
	actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="evidencias")
	archivo = models.FileField(upload_to="evidencias/%Y/%m/")
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
	creado_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["fecha_comprometida"]

	@property
	def vencido(self):
		return self.estado != "realizado" and self.fecha_comprometida < timezone.localdate()

	def __str__(self):
		return f"{self.solicitante} - {self.fecha_comprometida}"


class HistorialCompromiso(models.Model):
	compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name="historial")
	estado_anterior = models.CharField(max_length=20, blank=True)
	estado_nuevo = models.CharField(max_length=20)
	autor = models.ForeignKey(User, on_delete=models.PROTECT)
	observacion = models.TextField(blank=True)
	fecha = models.DateTimeField(auto_now_add=True)


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
