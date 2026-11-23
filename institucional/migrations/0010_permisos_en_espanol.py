from django.db import migrations
from django.utils import translation

APPS_SGR = ("institucional", "servicios", "oficina", "organizaciones")
MODELOS_AUTH = ("user", "group")
ACCIONES = {"view": "ver", "add": "agregar", "change": "modificar", "delete": "eliminar"}


def _permisos_estandar(apps):
    """Permisos ver/agregar/modificar/eliminar del SGR con el modelo histórico al que pertenecen."""
    Permission = apps.get_model("auth", "Permission")
    for permiso in Permission.objects.select_related("content_type"):
        tipo = permiso.content_type
        if tipo.app_label not in APPS_SGR and not (tipo.app_label == "auth" and tipo.model in MODELOS_AUTH):
            continue
        prefijo, _, modelo = permiso.codename.partition("_")
        if prefijo not in ACCIONES or modelo != tipo.model:
            continue
        try:
            opciones = apps.get_model(tipo.app_label, tipo.model)._meta
        except LookupError:
            continue
        yield permiso, prefijo, opciones


def a_espanol(apps, schema_editor):
    with translation.override("es"):
        for permiso, prefijo, opciones in _permisos_estandar(apps):
            permiso.name = f"Puede {ACCIONES[prefijo]} {opciones.verbose_name}"
            permiso.save(update_fields=["name"])


def a_ingles(apps, schema_editor):
    for permiso, prefijo, opciones in _permisos_estandar(apps):
        permiso.name = f"Can {prefijo} {opciones.verbose_name_raw}"
        permiso.save(update_fields=["name"])


class Migration(migrations.Migration):
    """Los permisos que Django crea solos se llaman «Can add …»; el SGR los muestra en español.

    En una base nueva los permisos aún no existen aquí: los traduce la señal post_migrate (laserena.permisos).
    """

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("institucional", "0009_nombres_en_espanol"),
        ("servicios", "0006_nombres_en_espanol"),
        ("oficina", "0003_nombres_en_espanol"),
        ("organizaciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(a_espanol, a_ingles),
    ]
