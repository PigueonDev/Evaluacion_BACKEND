from django.db import models


class Municipio(models.Model):
	nombre = models.CharField(max_length=160, unique=True)
	comuna = models.CharField(max_length=100)
	region = models.CharField("región", max_length=100)
	fundacion = models.PositiveIntegerField("año de fundación")
	descripcion = models.TextField("descripción")
	mision = models.TextField("misión")
	vision = models.TextField("visión")

	class Meta:
		verbose_name = "municipio"
		verbose_name_plural = "municipios"

	def __str__(self):
		return self.nombre


class Delegacion(models.Model):
	nombre = models.CharField(max_length=120, unique=True)
	slug = models.SlugField(max_length=120, unique=True)
	territorio = models.CharField(max_length=180)
	enfoque = models.TextField()
	direccion = models.CharField("dirección", max_length=200, blank=True)
	telefono = models.CharField("teléfono", max_length=30, blank=True)
	correo = models.EmailField(blank=True)
	responsable = models.CharField(max_length=120, blank=True)
	activa = models.BooleanField(default=True)

	class Meta:
		verbose_name = "delegación"
		verbose_name_plural = "delegaciones"
		ordering = ["nombre"]

	def __str__(self):
		return self.nombre


class UnidadMunicipal(models.Model):
	"""Departamento, sección o institución que apoya, recibe derivaciones o sigue cartas."""

	TIPOS = [("interna", "Unidad municipal"), ("externa", "Institución externa")]
	nombre = models.CharField("nombre", max_length=120, unique=True)
	sigla = models.CharField("sigla", max_length=20, blank=True)
	tipo = models.CharField("tipo", max_length=10, choices=TIPOS, default="interna")
	descripcion = models.CharField("descripción", max_length=250, blank=True)
	activa = models.BooleanField("activa", default=True)

	class Meta:
		ordering = ["tipo", "nombre"]
		verbose_name = "unidad municipal"
		verbose_name_plural = "unidades municipales"

	def __str__(self):
		return f"{self.nombre} ({self.sigla})" if self.sigla else self.nombre


class Cargo(models.Model):
	PERFILES = [("Administrador", "Administrador"), ("Supervisor", "Supervisor"), ("Administrativo", "Administrativo")]
	nombre = models.CharField(max_length=120, unique=True)
	sigla = models.CharField("sigla de área", max_length=10, blank=True, help_text="Prefijo del código verificador de la matriz (APA, COM, SOC, COS, PYG, SEG…).")
	perfil = models.CharField("perfil del sistema", max_length=20, choices=PERFILES, blank=True, help_text="Grupo que corresponde al cargo. Vacío: cualquier perfil.")
	descripcion = models.TextField("descripción", blank=True)
	activo = models.BooleanField(default=True)
	funciones = models.ManyToManyField("servicios.ItemMedicion", blank=True, related_name="cargos")

	class Meta:
		verbose_name = "cargo"
		verbose_name_plural = "cargos"
		ordering = ["nombre"]

	def __str__(self):
		return self.nombre


class Funcionario(models.Model):
	usuario = models.OneToOneField("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="perfil_sgr")
	identificador = models.CharField(max_length=30, unique=True)
	nombre_completo = models.CharField(max_length=160)
	correo = models.EmailField(blank=True)
	delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name="funcionarios")
	cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="funcionarios")
	codigo_area = models.CharField("código de área", max_length=10, blank=True, help_text="Código del colaborador en la matriz (COM1, SOC2…). Vacío: se usa la sigla del cargo.")
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "funcionario"
		verbose_name_plural = "funcionarios"
		ordering = ["nombre_completo"]

	def __str__(self):
		return f"{self.nombre_completo} ({self.identificador})"

	@property
	def prefijo_codigo(self):
		return (self.codigo_area or self.cargo.sigla or "").upper().replace(" ", "")

	@property
	def grupo(self):
		from laserena.permisos import grupo_usuario

		return grupo_usuario(self.usuario) if self.usuario_id else None


class Territorio(models.Model):
	"""Catálogo de territorios. Las delegaciones y las organizaciones lo usan en vez de una lista fija."""

	codigo = models.CharField("código", max_length=40, unique=True)
	nombre = models.CharField(max_length=180, unique=True)
	descripcion = models.TextField("descripción", blank=True)
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "territorio"
		verbose_name_plural = "territorios"
		ordering = ["nombre"]

	def __str__(self):
		return self.nombre


class Vecino(models.Model):
	"""Persona usuaria ya registrada. Sirve para autocompletar nombre, RUT y teléfono."""

	delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name="vecinos")
	nombre = models.CharField(max_length=160)
	rut = models.CharField("RUT", max_length=12, blank=True)
	telefono = models.CharField("teléfono", max_length=30, blank=True)
	correo = models.EmailField(blank=True)
	direccion = models.CharField("dirección", max_length=200, blank=True)
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "vecino"
		verbose_name_plural = "vecinos"
		ordering = ["nombre"]
		constraints = [
			models.UniqueConstraint(fields=["delegacion", "rut"], condition=~models.Q(rut=""), name="vecino_rut_unico_por_delegacion"),
		]

	def __str__(self):
		return self.nombre


class Hito(models.Model):
	"""Hito territorial con un funcionario responsable."""

	ESTADOS = [
		("pendiente", "Pendiente"),
		("en_curso", "En curso"),
		("cumplido", "Cumplido"),
		("anulado", "Anulado"),
	]
	nombre = models.CharField(max_length=160)
	descripcion = models.TextField("descripción", blank=True)
	fecha = models.DateField()
	delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name="hitos")
	responsable = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="hitos")
	estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
	activo = models.BooleanField(default=True)

	class Meta:
		verbose_name = "hito"
		verbose_name_plural = "hitos"
		ordering = ["-fecha", "nombre"]

	def __str__(self):
		return self.nombre


class EstadoClave(models.Model):
	"""La contraseña entregada al crear la cuenta es temporal hasta el primer cambio."""

	usuario = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="estado_clave")
	debe_cambiar_clave = models.BooleanField("debe cambiar la contraseña", default=False)

	class Meta:
		verbose_name = "estado de la contraseña"
		verbose_name_plural = "estados de la contraseña"

	def __str__(self):
		return self.usuario.get_username()


class Autoridad(models.Model):
	nombre = models.CharField(max_length=160)
	cargo = models.CharField(max_length=120)
	periodo = models.CharField("período", max_length=30)
	resena = models.TextField("reseña", blank=True)
	activa = models.BooleanField(default=True)

	class Meta:
		verbose_name = "autoridad"
		verbose_name_plural = "autoridades"
		ordering = ["cargo", "nombre"]

	def __str__(self):
		return f"{self.nombre} - {self.cargo}"
