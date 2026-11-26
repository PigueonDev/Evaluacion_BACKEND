from django.db import migrations


def sembrar(apps, schema_editor):
	from servicios.models import FORMA_POR_SUBATENCION, SUBATENCIONES_POR_TIPO, SUBATENCIONES_SOCIALES, TIPOS_ATENCION_SOCIAL

	TipoAtencion = apps.get_model("servicios", "TipoAtencion")
	SubtipoAtencion = apps.get_model("servicios", "SubtipoAtencion")
	Compromiso = apps.get_model("servicios", "Compromiso")
	nombres = dict(SUBATENCIONES_SOCIALES)
	for codigo, nombre in TIPOS_ATENCION_SOCIAL:
		tipo, _ = TipoAtencion.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre, "activo": True})
		for subcodigo in SUBATENCIONES_POR_TIPO.get(codigo, ()):
			SubtipoAtencion.objects.get_or_create(
				tipo=tipo,
				codigo=subcodigo,
				defaults={"nombre": nombres.get(subcodigo, subcodigo), "forma": FORMA_POR_SUBATENCION.get(subcodigo, ""), "activo": True},
			)
	for compromiso in Compromiso.objects.filter(codigo__isnull=True).order_by("pk"):
		anio = compromiso.fecha_solicitud.year if compromiso.fecha_solicitud else compromiso.fecha_comprometida.year
		compromiso.codigo = f"TB-{anio}-{compromiso.pk:04d}"
		compromiso.save(update_fields=["codigo"])


def revertir(apps, schema_editor):
	apps.get_model("servicios", "SubtipoAtencion").objects.all().delete()
	apps.get_model("servicios", "TipoAtencion").objects.all().delete()
	apps.get_model("servicios", "Compromiso").objects.update(codigo=None)


class Migration(migrations.Migration):
	dependencies = [
		("servicios", "0010_alcance_actividad_1"),
	]

	operations = [
		migrations.RunPython(sembrar, revertir),
	]
