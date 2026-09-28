from django.contrib import admin
from clientesApp.models import Cliente, Arriendo


class ArriendoInline(admin.TabularInline):
    model = Arriendo
    extra = 0
    fields = ("pelicula", "fecha_arriendo", "fecha_limite", "fecha_devolucion", "estado", "total")
    show_change_link = True


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("run", "nombre", "paterno", "materno", "email", "telefono", "fecha_registro", "activo")
    search_fields = ("run", "nombre", "paterno", "materno", "email")
    list_filter = ("activo", "fecha_registro")
    inlines = [ArriendoInline]


@admin.register(Arriendo)
class ArriendoAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "pelicula", "fecha_arriendo", "fecha_limite", "fecha_devolucion", "estado", "total")
    search_fields = ("cliente__nombre", "cliente__paterno", "cliente__run", "pelicula__titulo")
    list_filter = ("estado", "fecha_arriendo")
