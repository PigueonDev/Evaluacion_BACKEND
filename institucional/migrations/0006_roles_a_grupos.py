from django.db import migrations

EQUIVALENCIAS = {
    "administrador": "Administrador",
    "delegado": "Supervisor",
    "consulta": "Supervisor",
    "funcionario": "Administrativo",
}


def roles_a_grupos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Funcionario = apps.get_model("institucional", "Funcionario")
    grupos = {nombre: Group.objects.get_or_create(name=nombre)[0] for nombre in set(EQUIVALENCIAS.values())}
    for funcionario in Funcionario.objects.exclude(usuario=None).select_related("usuario"):
        grupo = grupos.get(EQUIVALENCIAS.get(funcionario.rol, "Administrativo"))
        funcionario.usuario.groups.add(grupo)


def grupos_a_roles(apps, schema_editor):
    Funcionario = apps.get_model("institucional", "Funcionario")
    inverso = {"Administrador": "administrador", "Supervisor": "delegado", "Administrativo": "funcionario"}
    for funcionario in Funcionario.objects.exclude(usuario=None).select_related("usuario"):
        nombres = list(funcionario.usuario.groups.values_list("name", flat=True))
        for nombre, rol in inverso.items():
            if nombre in nombres:
                funcionario.rol = rol
                funcionario.save(update_fields=["rol"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("institucional", "0005_funcionario_rol_administrador"),
    ]

    operations = [
        migrations.RunPython(roles_a_grupos, grupos_a_roles),
    ]
