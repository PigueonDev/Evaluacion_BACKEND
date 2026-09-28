from django.db import models
from catalogoApp.choices import clasificaciones


class Genero(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Género")
    descripcion = models.CharField(max_length=200, blank=True, default="", verbose_name="Descripción")

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = "generos"
        verbose_name = "Género"
        verbose_name_plural = "Géneros"
        ordering = ["nombre"]


class Director(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Nombre del Director")
    nacionalidad = models.CharField(max_length=80, blank=True, default="", verbose_name="Nacionalidad")

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = "directores"
        verbose_name = "Director"
        verbose_name_plural = "Directores"
        ordering = ["nombre"]


class Pelicula(models.Model):
    titulo = models.CharField(max_length=200, verbose_name="Título")
    anio = models.PositiveSmallIntegerField(verbose_name="Año de estreno")
    duracion = models.PositiveSmallIntegerField(default=90, verbose_name="Duración (minutos)")
    clasificacion = models.CharField(max_length=3, choices=clasificaciones, default='TE', verbose_name="Clasificación")
    precio_arriendo = models.PositiveIntegerField(default=2500, verbose_name="Precio de arriendo")
    stock = models.PositiveSmallIntegerField(default=1, verbose_name="Copias disponibles")
    sinopsis = models.TextField(blank=True, default="", verbose_name="Sinopsis")
    genero = models.ForeignKey(Genero, on_delete=models.RESTRICT, verbose_name="Género")
    director = models.ForeignKey(Director, on_delete=models.RESTRICT, null=True, blank=True, verbose_name="Director")

    def __str__(self):
        return f"{self.titulo} ({self.anio})"

    class Meta:
        db_table = "peliculas"
        verbose_name = "Película"
        verbose_name_plural = "Películas"
        ordering = ["titulo"]
