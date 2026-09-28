from django.contrib import admin
from catalogoApp.models import Genero, Director, Pelicula


class PeliculaInline(admin.TabularInline):
    model = Pelicula
    extra = 0
    fields = ("titulo", "anio", "clasificacion", "precio_arriendo", "stock")
    show_change_link = True


@admin.register(Genero)
class GeneroAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "descripcion")
    search_fields = ("nombre", "descripcion")
    inlines = [PeliculaInline]


@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "nacionalidad")
    search_fields = ("nombre", "nacionalidad")
    inlines = [PeliculaInline]


@admin.register(Pelicula)
class PeliculaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "anio", "genero", "director", "clasificacion", "precio_arriendo", "stock")
    search_fields = ("titulo", "genero__nombre", "director__nombre")
    list_filter = ("genero", "clasificacion", "anio")
    ordering = ("titulo",)
