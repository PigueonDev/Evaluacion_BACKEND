from django.db import migrations
from django.utils.text import slugify


def sembrar(apps, schema_editor):
	Territorio = apps.get_model("institucional", "Territorio")
	Delegacion = apps.get_model("institucional", "Delegacion")
	from organizaciones.models import TERRITORIOS

	for codigo, nombre in TERRITORIOS:
		Territorio.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre, "activo": True})
	nombres = set(Territorio.objects.values_list("nombre", flat=True))
	codigos = set(Territorio.objects.values_list("codigo", flat=True))
	for texto in Delegacion.objects.exclude(territorio="").values_list("territorio", flat=True).distinct():
		if texto in nombres:
			continue
		base = (slugify(texto) or "territorio").upper().replace("-", " ")[:40]
		codigo = base
		numero = 2
		while codigo in codigos:
			sufijo = f" {numero}"
			codigo = f"{base[:40 - len(sufijo)]}{sufijo}"
			numero += 1
		Territorio.objects.create(codigo=codigo, nombre=texto[:180], activo=True)
		codigos.add(codigo)
		nombres.add(texto)


def revertir(apps, schema_editor):
	apps.get_model("institucional", "Territorio").objects.all().delete()


class Migration(migrations.Migration):
	dependencies = [
		("institucional", "0011_alcance_actividad_1"),
		("organizaciones", "0001_initial"),
	]

	operations = [
		migrations.RunPython(sembrar, revertir),
	]
