import json
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from institucional.models import Autoridad, Cargo, Delegacion, Funcionario, Municipio
from servicios.models import Actividad, Compromiso, ItemMedicion, Meta, Periodo, Servicio


class Command(BaseCommand):
    help = "Carga datos ficticios iniciales para demostrar el SGR."

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[3]
        institucion_path = base_dir / "institucional" / "data" / "institucion.json"
        servicios_path = base_dir / "servicios" / "data" / "servicios.json"

        with institucion_path.open(encoding="utf-8") as archivo:
            institucion = json.load(archivo)
        with servicios_path.open(encoding="utf-8") as archivo:
            catalogo = json.load(archivo)

        municipio_data = institucion["municipio"]
        Municipio.objects.update_or_create(
            nombre=municipio_data["nombre"],
            defaults={
                "comuna": municipio_data["comuna"],
                "region": municipio_data["region"],
                "fundacion": municipio_data["fundacion"],
                "descripcion": municipio_data["descripcion"],
                "mision": institucion["mision"],
                "vision": institucion["vision"],
            },
        )

        for autoridad in institucion.get("autoridades", []):
            Autoridad.objects.update_or_create(
                nombre=autoridad["nombre"],
                defaults={
                    "cargo": autoridad["cargo"],
                    "periodo": autoridad["periodo"],
                    "resena": autoridad.get("resena", ""),
                },
            )

        delegaciones = [
            ("Avenida del Mar", "avenida-del-mar", "Borde costero, turismo y servicios", "Coordinación estacional, espacios públicos y seguridad."),
            ("Centro", "centro", "Centro histórico, administrativo y patrimonial", "Atención territorial y gestión del espacio público."),
            ("La Antena", "la-antena", "Sector urbano oriental", "Participación vecinal y canalización de requerimientos."),
            ("Las Compañías", "las-companias", "Sector urbano norte", "Gestión comunitaria y acceso a programas y servicios."),
            ("La Pampa", "la-pampa", "Sector urbano sur", "Asistencia social y gestión de requerimientos comunitarios."),
            ("Rural", "rural", "Localidades y comunidades rurales", "Acercamiento de servicios y coordinación intersectorial."),
        ]
        for nombre, slug, territorio, enfoque in delegaciones:
            Delegacion.objects.update_or_create(
                slug=slug,
                defaults={
                    "nombre": nombre,
                    "territorio": territorio,
                    "enfoque": enfoque,
                    "direccion": "Dirección ficticia para demostración",
                    "telefono": "+56 51 200 0000",
                    "correo": f"{slug.replace('-', '')}@demo.laserena.cl",
                    "responsable": "Responsable de demostración",
                },
            )

        for servicio in catalogo.get("servicios", []):
            Servicio.objects.update_or_create(
                slug=servicio["slug"],
                defaults={
                    "nombre": servicio["nombre"],
                    "categoria": servicio["categoria"],
                    "unidad": servicio["unidad"],
                    "descripcion": servicio["descripcion"],
                },
            )

        items = [
            ("ACT-001", "Actividades territoriales", "Registro de acciones realizadas en terreno"),
            ("ACT-002", "Atenciones y orientaciones", "Registro de atención o derivación"),
            ("ACT-003", "Gestión de requerimientos", "Seguimiento de problemas y solicitudes"),
        ]
        for codigo, nombre, descripcion in items:
            ItemMedicion.objects.update_or_create(
                codigo=codigo,
                defaults={"nombre": nombre, "descripcion": descripcion, "unidad": "cantidad"},
            )

        periodo, _ = Periodo.objects.get_or_create(
            nombre="Período demostración 2026",
            defaults={
                "fecha_inicio": date(2026, 1, 1),
                "fecha_termino": date(2026, 12, 31),
                "estado": "abierto",
            },
        )

        cargo, _ = Cargo.objects.get_or_create(nombre="Gestor territorial", defaults={"descripcion": "Cargo ficticio para demostración."})
        item = ItemMedicion.objects.get(codigo="ACT-001")
        cargo.funciones.add(item)
        delegacion = Delegacion.objects.get(slug="centro")
        usuario = get_user_model()
        gestor, creado = usuario.objects.get_or_create(
            username="gestor",
            defaults={
                "email": "gestor@demo.laserena.cl",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if creado:
            gestor.set_password("gestor-demo")
            gestor.save()
        elif not gestor.is_staff:
            gestor.is_staff = True
            gestor.is_superuser = True
            gestor.save()
        funcionario, _ = Funcionario.objects.update_or_create(
            identificador="DEMO-001",
            defaults={
                "nombre_completo": "Funcionario de demostración",
                "correo": "demo@ejemplo.cl",
                "delegacion": delegacion,
                "cargo": cargo,
                "usuario": gestor,
            },
        )
        Meta.objects.update_or_create(
            periodo=periodo,
            item=item,
            funcionario=funcionario,
            defaults={"objetivo": 10, "ponderador": 100},
        )
        Actividad.objects.get_or_create(
            funcionario=funcionario,
            periodo=periodo,
            item=item,
            descripcion="Operativo territorial de demostración",
            defaults={"accion": "Orientación y coordinación ficticia", "estado": "validada"},
        )
        Compromiso.objects.get_or_create(
            delegacion=delegacion,
            responsable=funcionario,
            solicitante="Organización vecinal ficticia",
            descripcion="Coordinar respuesta de demostración",
            defaults={
                "origen": "Solicitud de prueba",
                "territorio": "Centro",
                "fecha_comprometida": date(2026, 10, 15),
                "estado": "pendiente",
            },
        )

        self.stdout.write(self.style.SUCCESS("Datos demo SGR cargados correctamente."))
