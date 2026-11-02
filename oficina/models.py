from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from laserena.rut import formatear_rut, normalizar_rut

EDAD_MAXIMA_BENEFICIO = 14


class Carta(models.Model):
	ESTADOS = [
		("ingresada", "Ingresada"),
		("derivada", "Derivada"),
		("en_respuesta", "En respuesta"),
		("respondida", "Respondida"),
		("archivada", "Archivada"),
	]
	TIPOS = [("solicitud", "Solicitud"), ("reclamo", "Reclamo"), ("invitacion", "Invitación"), ("informativa", "Informativa")]

	folio = models.CharField("folio", max_length=20, unique=True, editable=False)
	fecha_ingreso = models.DateField("fecha de ingreso", default=timezone.localdate)
	tipo = models.CharField("tipo", max_length=20, choices=TIPOS, default="solicitud")
	remitente = models.CharField("remitente", max_length=160)
	contacto_remitente = models.CharField("teléfono o correo del remitente", max_length=120, blank=True)
	asunto = models.CharField("asunto", max_length=200)
	detalle = models.TextField("detalle", blank=True)
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="cartas", verbose_name="delegación")
	organizacion = models.ForeignKey("organizaciones.OrganizacionComunitaria", on_delete=models.SET_NULL, null=True, blank=True, related_name="cartas", verbose_name="organización comunitaria")
	derivada_a = models.ForeignKey("institucional.Funcionario", on_delete=models.SET_NULL, null=True, blank=True, related_name="cartas_derivadas", verbose_name="derivada a")
	estado = models.CharField("estado", max_length=20, choices=ESTADOS, default="ingresada")
	plazo_respuesta = models.DateField("plazo de respuesta", null=True, blank=True)
	respuesta = models.TextField("respuesta", blank=True)
	fecha_respuesta = models.DateField("fecha de respuesta", null=True, blank=True)
	registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cartas_registradas")
	creada_en = models.DateTimeField(auto_now_add=True)
	actualizada_en = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-fecha_ingreso", "-id"]
		verbose_name = "carta de Oficina de Partes"
		verbose_name_plural = "cartas de Oficina de Partes"

	def __str__(self):
		return f"{self.folio} · {self.asunto}"

	@property
	def vencida(self):
		return bool(self.plazo_respuesta and self.estado not in ("respondida", "archivada") and self.plazo_respuesta < timezone.localdate())

	def clean(self):
		errores = {}
		if self.estado in ("derivada", "en_respuesta") and not self.derivada_a_id:
			errores["derivada_a"] = "Indica a quién se deriva la carta."
		if self.derivada_a_id and self.delegacion_id and self.derivada_a.delegacion_id != self.delegacion_id:
			errores["derivada_a"] = "La carta solo se deriva a personal de la misma delegación."
		if self.estado == "respondida":
			if not self.respuesta.strip():
				errores["respuesta"] = "Una carta respondida debe registrar la respuesta."
			if not self.fecha_respuesta:
				errores["fecha_respuesta"] = "Indica la fecha de respuesta."
		if self.fecha_respuesta and self.fecha_ingreso and self.fecha_respuesta < self.fecha_ingreso:
			errores["fecha_respuesta"] = "La respuesta no puede ser anterior al ingreso."
		if self.plazo_respuesta and self.fecha_ingreso and self.plazo_respuesta < self.fecha_ingreso:
			errores["plazo_respuesta"] = "El plazo no puede ser anterior al ingreso."
		if errores:
			raise ValidationError(errores)

	def save(self, *args, **kwargs):
		if not self.folio:
			anio = (self.fecha_ingreso or timezone.localdate()).year
			ultimo = Carta.objects.filter(folio__startswith=f"OP-{anio}-").order_by("-folio").values_list("folio", flat=True).first()
			correlativo = int(ultimo.rsplit("-", 1)[1]) + 1 if ultimo else 1
			self.folio = f"OP-{anio}-{correlativo:04d}"
		super().save(*args, **kwargs)


class BeneficioNino(models.Model):
	TIPOS = [("regalo_navidad", "Regalo de Navidad"), ("dia_nino", "Día del Niño"), ("utiles", "Útiles escolares"), ("otro", "Otro")]
	ESTADOS = [("registrado", "Registrado"), ("entregado", "Entregado"), ("anulado", "Anulado")]
	SEXOS = [("F", "Femenino"), ("M", "Masculino"), ("O", "Otro / no informa")]

	rut_nino = models.CharField("RUT del niño o niña", max_length=12, unique=True, error_messages={"unique": "Ese RUT ya tiene un beneficio registrado (en esta u otra delegación)."})
	nombre_nino = models.CharField("nombre del niño o niña", max_length=160)
	fecha_nacimiento = models.DateField("fecha de nacimiento")
	sexo = models.CharField("sexo", max_length=1, choices=SEXOS, default="O")
	tipo = models.CharField("tipo de beneficio", max_length=20, choices=TIPOS, default="regalo_navidad")
	descripcion = models.CharField("detalle del regalo", max_length=200, blank=True)
	apoderado = models.CharField("nombre del apoderado", max_length=160)
	telefono_apoderado = models.CharField("teléfono del apoderado", max_length=20, blank=True)
	delegacion = models.ForeignKey("institucional.Delegacion", on_delete=models.PROTECT, related_name="beneficios", verbose_name="delegación")
	organizacion = models.ForeignKey("organizaciones.OrganizacionComunitaria", on_delete=models.SET_NULL, null=True, blank=True, related_name="beneficios", verbose_name="organización que postula")
	estado = models.CharField("estado", max_length=20, choices=ESTADOS, default="registrado")
	fecha_entrega = models.DateField("fecha de entrega", null=True, blank=True)
	registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="beneficios_registrados")
	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["nombre_nino"]
		verbose_name = "beneficio para niños"
		verbose_name_plural = "beneficios para niños"

	def __str__(self):
		return f"{self.nombre_nino} ({self.rut_formateado})"

	@property
	def rut_formateado(self):
		return formatear_rut(self.rut_nino) if self.rut_nino else ""

	@property
	def edad(self):
		hoy = timezone.localdate()
		nacimiento = self.fecha_nacimiento
		return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))

	def clean(self):
		errores = {}
		if self.rut_nino:
			try:
				self.rut_nino = normalizar_rut(self.rut_nino)
			except ValidationError as error:
				errores["rut_nino"] = error.messages
		if self.fecha_nacimiento:
			if self.fecha_nacimiento > timezone.localdate():
				errores["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
			elif self.edad > EDAD_MAXIMA_BENEFICIO:
				errores["fecha_nacimiento"] = f"El beneficio es para menores de hasta {EDAD_MAXIMA_BENEFICIO} años."
		if self.estado == "entregado" and not self.fecha_entrega:
			errores["fecha_entrega"] = "Indica la fecha de entrega."
		if errores:
			raise ValidationError(errores)


class Ausencia(models.Model):
	MOTIVOS = [("licencia", "Licencia médica"), ("feriado", "Feriado legal"), ("permiso", "Permiso administrativo"), ("capacitacion", "Capacitación"), ("otro", "Otro")]
	ESTADOS = [("vigente", "Vigente"), ("anulada", "Anulada")]

	funcionario = models.ForeignKey("institucional.Funcionario", on_delete=models.PROTECT, related_name="ausencias")
	periodo = models.ForeignKey("servicios.Periodo", on_delete=models.PROTECT, related_name="ausencias")
	fecha_inicio = models.DateField("desde")
	fecha_termino = models.DateField("hasta")
	motivo = models.CharField("motivo", max_length=20, choices=MOTIVOS)
	observacion = models.CharField("observación", max_length=250, blank=True)
	estado = models.CharField(max_length=20, choices=ESTADOS, default="vigente")
	registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ausencias_registradas")
	registrada_en = models.DateTimeField(auto_now_add=True)
	anulada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ausencias_anuladas")
	anulada_en = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-fecha_inicio"]
		permissions = [("anular_ausencia", "Puede anular una ausencia y restituir las metas")]

	def __str__(self):
		return f"{self.funcionario.nombre_completo}: {self.fecha_inicio:%d-%m-%Y} a {self.fecha_termino:%d-%m-%Y}"

	@property
	def dias(self):
		return (self.fecha_termino - self.fecha_inicio).days + 1


class AjusteMeta(models.Model):
	"""Rastro de cada meta modificada por una ausencia, para mostrarla y poder restituirla."""

	ausencia = models.ForeignKey(Ausencia, on_delete=models.CASCADE, related_name="ajustes")
	meta = models.ForeignKey("servicios.Meta", on_delete=models.PROTECT, related_name="ajustes_ausencia")
	meta_creada = models.BooleanField(default=False, help_text="La meta personal se creó a partir de la meta del cargo.")
	objetivo_anterior = models.DecimalField(max_digits=10, decimal_places=2)
	objetivo_nuevo = models.DecimalField(max_digits=10, decimal_places=2)
	semaforo_anterior = models.CharField(max_length=10)
	semaforo_nuevo = models.CharField(max_length=10)

	class Meta:
		ordering = ["meta__item__nombre"]
