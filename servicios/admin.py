from django.contrib import admin

from .models import (
	Actividad,
	Auditoria,
	Compromiso,
	Evidencia,
	HistorialCompromiso,
	ItemMedicion,
	Meta,
	Periodo,
	Servicio,
	Validacion,
)


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
	list_display = ("nombre", "categoria", "unidad", "activo")
	list_filter = ("categoria", "activo")
	search_fields = ("nombre", "categoria", "unidad")


@admin.register(ItemMedicion)
class ItemMedicionAdmin(admin.ModelAdmin):
	list_display = ("codigo", "nombre", "unidad", "activo")
	list_filter = ("activo", "unidad")
	search_fields = ("codigo", "nombre")


@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
	list_display = ("nombre", "fecha_inicio", "fecha_termino", "estado", "tope_cumplimiento")
	list_filter = ("estado",)
	search_fields = ("nombre",)


@admin.register(Meta)
class MetaAdmin(admin.ModelAdmin):
	list_display = ("item", "periodo", "cargo", "funcionario", "objetivo", "ponderador")
	list_filter = ("periodo", "item")
	search_fields = ("item__nombre", "item__codigo")


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
	list_display = ("codigo_evidencia", "fecha", "funcionario", "item", "estado")
	list_filter = ("estado", "periodo", "item")
	search_fields = ("codigo_evidencia", "descripcion", "funcionario__nombre_completo")
	readonly_fields = ("codigo_evidencia", "creada_en")


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
	list_display = ("actividad", "autor", "estado", "cargada_en")
	list_filter = ("estado", "cargada_en")
	search_fields = ("actividad__codigo_evidencia", "observacion")
	readonly_fields = ("cargada_en",)


@admin.register(Validacion)
class ValidacionAdmin(admin.ModelAdmin):
	list_display = ("evidencia", "verificador", "decision", "fecha")
	list_filter = ("decision", "fecha")
	search_fields = ("evidencia__actividad__codigo_evidencia", "observacion")
	readonly_fields = ("fecha",)


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
	list_display = ("solicitante", "responsable", "delegacion", "fecha_comprometida", "estado")
	list_filter = ("estado", "delegacion", "fecha_comprometida")
	search_fields = ("solicitante", "territorio", "descripcion")


@admin.register(HistorialCompromiso)
class HistorialCompromisoAdmin(admin.ModelAdmin):
	list_display = ("compromiso", "estado_anterior", "estado_nuevo", "autor", "fecha")
	list_filter = ("estado_nuevo", "fecha")
	search_fields = ("compromiso__solicitante", "observacion")
	readonly_fields = ("fecha",)


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
	list_display = ("fecha", "usuario", "accion", "entidad", "identificador")
	list_filter = ("accion", "entidad", "fecha")
	search_fields = ("identificador", "entidad", "accion")
	readonly_fields = ("usuario", "accion", "entidad", "identificador", "valor_anterior", "valor_nuevo", "fecha")
