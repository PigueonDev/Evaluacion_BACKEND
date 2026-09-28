from django.db import models
from django.utils import timezone
from clientesApp.choices import estados


class Cliente(models.Model):
    run = models.CharField(max_length=12, unique=True, verbose_name="RUN")
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    paterno = models.CharField(max_length=100, verbose_name="Apellido Paterno")
    materno = models.CharField(max_length=100, blank=True, default="", verbose_name="Apellido Materno")
    email = models.EmailField(blank=True, default="", verbose_name="Correo electrónico")
    telefono = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono")
    fecha_registro = models.DateField(default=timezone.localdate, verbose_name="Fecha de registro")
    activo = models.BooleanField(default=True, verbose_name="Cliente activo")

    def __str__(self):
        return f"{self.nombre} {self.paterno}"

    class Meta:
        db_table = "clientes"
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["paterno", "nombre"]


class Arriendo(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.RESTRICT, verbose_name="Cliente")
    pelicula = models.ForeignKey('catalogoApp.Pelicula', on_delete=models.RESTRICT, verbose_name="Película")
    fecha_arriendo = models.DateField(default=timezone.localdate, verbose_name="Fecha de arriendo")
    fecha_limite = models.DateField(default=timezone.localdate, verbose_name="Fecha límite de devolución")
    fecha_devolucion = models.DateField(null=True, blank=True, verbose_name="Fecha de devolución")
    estado = models.CharField(max_length=1, choices=estados, default='A', verbose_name="Estado")
    total = models.PositiveIntegerField(default=0, verbose_name="Total a pagar")

    def __str__(self):
        return f"Arriendo #{self.pk}: {self.pelicula.titulo} - {self.cliente}"

    class Meta:
        db_table = "arriendos"
        verbose_name = "Arriendo"
        verbose_name_plural = "Arriendos"
        ordering = ["-fecha_arriendo", "-id"]
