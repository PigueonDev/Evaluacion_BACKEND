from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("institucional", "0004_funcionario_rol"),
    ]

    operations = [
        migrations.AlterField(
            model_name="funcionario",
            name="rol",
            field=models.CharField(
                choices=[
                    ("funcionario", "Funcionario"),
                    ("delegado", "Delegado o jefatura"),
                    ("consulta", "Usuario de consulta"),
                    ("administrador", "Administrador"),
                ],
                default="funcionario",
                max_length=20,
            ),
        ),
    ]
