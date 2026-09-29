from django.db import models


class Municipio(models.Model):
	nombre = models.CharField(max_length=160, unique=True)
	comuna = models.CharField(max_length=100)
	region = models.CharField(max_length=100)
	fundacion = models.PositiveIntegerField()
	descripcion = models.TextField()
	mision = models.TextField()
	vision = models.TextField()

	def __str__(self):
		return self.nombre


class Delegacion(models.Model):
	nombre = models.CharField(max_length=120, unique=True)
	slug = models.SlugField(max_length=120, unique=True)
	territorio = models.CharField(max_length=180)
	enfoque = models.TextField()
	direccion = models.CharField(max_length=200, blank=True)
	telefono = models.CharField(max_length=30, blank=True)
	correo = models.EmailField(blank=True)
	responsable = models.CharField(max_length=120, blank=True)
	activa = models.BooleanField(default=True)

	class Meta:
		ordering = ["nombre"]

	def __str__(self):
		return self.nombre


class Cargo(models.Model):
	nombre = models.CharField(max_length=120, unique=True)
	descripcion = models.TextField(blank=True)
	activo = models.BooleanField(default=True)
	funciones = models.ManyToManyField("servicios.ItemMedicion", blank=True, related_name="cargos")

	class Meta:
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
	activo = models.BooleanField(default=True)

	class Meta:
		ordering = ["nombre_completo"]

	def __str__(self):
		return f"{self.nombre_completo} ({self.identificador})"


class Autoridad(models.Model):
	nombre = models.CharField(max_length=160)
	cargo = models.CharField(max_length=120)
	periodo = models.CharField(max_length=30)
	resena = models.TextField(blank=True)
	activa = models.BooleanField(default=True)

	class Meta:
		ordering = ["cargo", "nombre"]

	def __str__(self):
		return f"{self.nombre} - {self.cargo}"
