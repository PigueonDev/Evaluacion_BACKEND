from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("institucional", "0006_roles_a_grupos"),
    ]

    operations = [
        migrations.RemoveField(model_name="funcionario", name="rol"),
    ]
