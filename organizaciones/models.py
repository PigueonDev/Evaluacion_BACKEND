from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

TERRITORIOS = [
	("ALFALFARES", "Alfalfares"),
	("ANTENA", "La Antena"),
	("AV DEL MAR", "Avenida del Mar"),
	("CENTRO", "Centro"),
	("CIAS", "Las Compañías"),
	("PAMPA", "La Pampa"),
	("RURAL", "Rural"),
	("SIN TERRITORIO", "Sin territorio"),
]


def normalizar_territorio(valor):
	texto = " ".join(str(valor or "").upper().split())
	codigos = {codigo for codigo, _ in TERRITORIOS}
	return texto if texto in codigos else "SIN TERRITORIO"


class OrganizacionComunitaria(models.Model):
	TIPOS = [("junta_vecinos", "Junta de vecinos"), ("funcional", "Organización funcional")]
	ESTADOS = [("sin_verificar", "Sin verificar"), ("verificada", "Verificada"), ("inactiva", "Inactiva")]

	nombre = models.CharField("nombre", max_length=200)
	tipo = models.CharField("tipo", max_length=20, choices=TIPOS, default="funcional")
	domicilio = models.CharField("domicilio legal", max_length=250, blank=True)
	territorio = models.CharField("territorio o delegación", max_length=20, choices=TERRITORIOS, default="SIN TERRITORIO")
	socios_activos = models.PositiveIntegerField("socios activos", null=True, blank=True)
	fecha_constitucion = models.DateField("fecha de constitución", null=True, blank=True)
	numero_registro_pj = models.PositiveIntegerField("N° registro personalidad jurídica", null=True, blank=True)
	fecha_inscripcion = models.DateField("fecha de inscripción en el registro", null=True, blank=True)
	registro_directiva = models.PositiveIntegerField("N° registro de directiva", null=True, blank=True)
	estado = models.CharField("estado", max_length=20, choices=ESTADOS, default="sin_verificar")
	verificada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="organizaciones_verificadas")
	verificada_en = models.DateTimeField(null=True, blank=True)
	archivo_origen = models.CharField(max_length=120, blank=True)
	fila_origen = models.PositiveIntegerField(null=True, blank=True)
	creada_en = models.DateTimeField(auto_now_add=True)
	actualizada_en = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["nombre"]
		verbose_name = "organización comunitaria"
		verbose_name_plural = "organizaciones comunitarias"
		permissions = [("verificar_organizacion", "Puede verificar organizaciones comunitarias")]
		constraints = [
			models.UniqueConstraint(fields=["archivo_origen", "fila_origen"], name="organizacion_fila_origen_unica"),
		]

	def __str__(self):
		return self.nombre

	def clean(self):
		if self.fecha_constitucion and self.fecha_inscripcion and self.fecha_inscripcion < self.fecha_constitucion:
			raise ValidationError({"fecha_inscripcion": "La inscripción no puede ser anterior a la constitución."})

	def cambiar_estado(self, estado, usuario):
		if estado not in dict(self.ESTADOS):
			raise ValidationError("Estado de verificación no válido.")
		self.estado = estado
		if estado == "sin_verificar":
			self.verificada_por = None
			self.verificada_en = None
		else:
			self.verificada_por = usuario
			self.verificada_en = timezone.now()
		self.save(update_fields=["estado", "verificada_por", "verificada_en", "actualizada_en"])
