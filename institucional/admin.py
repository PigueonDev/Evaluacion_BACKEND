from django.contrib import admin

from .models import Autoridad, Cargo, Delegacion, Funcionario, Municipio


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
	list_display = ("nombre", "comuna", "region")
	search_fields = ("nombre", "comuna", "region")


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
	list_display = ("nombre", "territorio", "responsable", "activa")
	list_filter = ("activa",)
	search_fields = ("nombre", "territorio", "responsable")


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
	list_display = ("nombre", "activo")
	list_filter = ("activo",)
	search_fields = ("nombre",)
	filter_horizontal = ("funciones",)


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
	list_display = ("nombre_completo", "identificador", "delegacion", "cargo", "activo")
	list_filter = ("activo", "delegacion", "cargo")
	search_fields = ("nombre_completo", "identificador", "correo")


@admin.register(Autoridad)
class AutoridadAdmin(admin.ModelAdmin):
	list_display = ("nombre", "cargo", "periodo", "activa")
	list_filter = ("activa",)
	search_fields = ("nombre", "cargo")
