import json
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from django.utils import timezone

from institucional.cuentas import asegurar_grupos, asignar_grupo
from institucional.models import Autoridad, Cargo, Delegacion, Funcionario, Municipio
from laserena.rut import normalizar_rut
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR
from oficina.models import Ausencia, BeneficioNino, Carta
from oficina.transacciones import registrar_ausencia
from servicios.models import Actividad, Caso, Compromiso, Gestion, ItemMedicion, Meta, Periodo, Servicio, TareaPreparatoria

CLAVE_DEMO = "Serena-demo-2026"


class Command(BaseCommand):
    help = "Carga datos ficticios iniciales para demostrar el SGR."

    def handle(self, *args, **options):
        asegurar_grupos()
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
        usuario_funcionario = _usuario_demo("funcionario.demo", "Funcionario", "Demostración", GRUPO_ADMINISTRATIVO)
        funcionario, _ = Funcionario.objects.update_or_create(
            identificador="DEMO-001",
            defaults={
                "nombre_completo": "Funcionario de demostración",
                "correo": "demo@ejemplo.cl",
                "delegacion": delegacion,
                "cargo": cargo,
                "usuario": usuario_funcionario,
            },
        )
        funcionario.usuario = usuario_funcionario
        funcionario.save()
        cargo_delegado, _ = Cargo.objects.get_or_create(nombre="Delegado territorial", defaults={"descripcion": "Jefatura de la delegación."})
        usuario_delegado = _usuario_demo("delegado.demo", "Delegado", "Demostración", GRUPO_SUPERVISOR)
        delegado, _ = Funcionario.objects.update_or_create(
            identificador="DEMO-DEL",
            defaults={
                "nombre_completo": "Delegado de demostración",
                "correo": "delegado@ejemplo.cl",
                "delegacion": delegacion,
                "cargo": cargo_delegado,
                "usuario": usuario_delegado,
            },
        )
        cargo_consulta, _ = Cargo.objects.get_or_create(nombre="Consulta operativa", defaults={"descripcion": "Lectura de informes dentro del ámbito."})
        usuario_consulta = _usuario_demo("consulta.demo", "Consulta", "Demostración", GRUPO_SUPERVISOR)
        Funcionario.objects.update_or_create(
            identificador="DEMO-CON",
            defaults={
                "nombre_completo": "Supervisor de consulta",
                "correo": "consulta@ejemplo.cl",
                "delegacion": delegacion,
                "cargo": cargo_consulta,
                "usuario": usuario_consulta,
            },
        )
        cargo_admin, _ = Cargo.objects.get_or_create(
            nombre="Administración municipal",
            defaults={"descripcion": "Parámetros, catálogos, metas y cuentas del SGR."},
        )
        usuario_admin = _usuario_demo("admin.demo", "Administrador", "Demostración", GRUPO_ADMINISTRADOR)
        Funcionario.objects.update_or_create(
            identificador="DEMO-ADM",
            defaults={
                "nombre_completo": "Administrador de demostración",
                "correo": "admin@ejemplo.cl",
                "delegacion": delegacion,
                "cargo": cargo_admin,
                "usuario": usuario_admin,
            },
        )
        Meta.objects.update_or_create(
            periodo=periodo,
            item=item,
            funcionario=funcionario,
            defaults={"objetivo": 10, "ponderador": 100},
        )
        hoy = timezone.localdate()
        actividad_aprobada, creada = Actividad.objects.get_or_create(
            funcionario=funcionario,
            periodo=periodo,
            item=item,
            descripcion="Operativo territorial de demostración",
            defaults={"accion": "Orientación y coordinación ficticia", "estado": "validada", "fecha": hoy, "contacto": "Junta de vecinos demo", "telefono": "+56 9 1111 2222"},
        )
        if creada:
            TareaPreparatoria.objects.create(actividad=actividad_aprobada, tipo="local", descripcion="Sede vecinal reservada", realizada=True, realizada_en=timezone.now())
        if hoy.weekday() < 5:
            pendiente, creada = Actividad.objects.get_or_create(
                funcionario=funcionario,
                periodo=periodo,
                item=item,
                descripcion="Celebración Día del Adulto Mayor en sede vecinal",
                defaults={"accion": "Coordinación con club de adulto mayor", "fecha": hoy, "contacto": "Presidenta del club", "telefono": "+56 9 3333 4444"},
            )
            if creada:
                TareaPreparatoria.objects.create(actividad=pendiente, tipo="sillas", descripcion="40 sillas y 6 mesas", realizada=True, realizada_en=timezone.now())
                TareaPreparatoria.objects.create(actividad=pendiente, tipo="colacion", descripcion="Colación para 40 personas")
                TareaPreparatoria.objects.create(actividad=pendiente, tipo="animacion", descripcion="Grupo folclórico")
        caso, _ = Caso.objects.get_or_create(
            identificacion="CASO-DEMO-001",
            defaults={
                "nombre": "Persona usuaria de demostración",
                "delegacion": delegacion,
                "observacion": "Caso ficticio para mostrar hasta tres gestiones.",
            },
        )
        actividad_demo = Actividad.objects.filter(funcionario=funcionario, descripcion="Operativo territorial de demostración").first()
        Gestion.objects.get_or_create(
            caso=caso,
            numero=1,
            defaults={
                "fecha": date(2026, 3, 12),
                "descripcion": "Primera orientación de demostración",
                "actividad": actividad_demo,
            },
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

        Meta.objects.get_or_create(
            periodo=periodo,
            item=item,
            funcionario=delegado,
            defaults={"objetivo": 12, "ponderador": 100},
        )
        _cartas_demo(delegacion, funcionario, usuario_admin)
        _beneficios_demo(delegacion, usuario_delegado)
        if not Ausencia.objects.filter(funcionario=delegado).exists():
            registrar_ausencia(
                Ausencia(funcionario=delegado, periodo=periodo, fecha_inicio=date(2026, 2, 2), fecha_termino=date(2026, 2, 13), motivo="feriado", observacion="Feriado legal de demostración"),
                usuario_admin,
            )

        self.stdout.write(self.style.SUCCESS(
            "Datos demo SGR cargados. Cuentas: admin.demo (Administrador), delegado.demo y consulta.demo (Supervisor), "
            "funcionario.demo (Administrativo). Clave: Serena-demo-2026."
        ))


def _usuario_demo(username, nombre, apellido, grupo):
    usuario, _ = get_user_model().objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@ejemplo.cl", "first_name": nombre, "last_name": apellido},
    )
    usuario.first_name = nombre
    usuario.last_name = apellido
    usuario.email = usuario.email or f"{username}@ejemplo.cl"
    usuario.is_staff = False
    usuario.is_superuser = False
    usuario.set_password(CLAVE_DEMO)
    usuario.save()
    asignar_grupo(usuario, grupo)
    return usuario


def _cartas_demo(delegacion, funcionario, usuario):
    cartas = [
        ("Junta de Vecinos Villa El Faro", "Solicitud de luminarias en pasaje Los Aromos", "derivada", None),
        ("Club de Adulto Mayor Renacer", "Invitación a aniversario del club", "respondida", "Se confirma asistencia del delegado y apoyo con sillas."),
        ("Vecina del sector centro", "Reclamo por microbasural en calle Cordovez", "ingresada", None),
    ]
    for remitente, asunto, estado, respuesta in cartas:
        if Carta.objects.filter(asunto=asunto).exists():
            continue
        hoy = timezone.localdate()
        Carta.objects.create(
            remitente=remitente, asunto=asunto, estado=estado, delegacion=delegacion, registrada_por=usuario,
            tipo="invitacion" if "Invitación" in asunto else ("reclamo" if "Reclamo" in asunto else "solicitud"),
            derivada_a=funcionario if estado != "ingresada" else None,
            plazo_respuesta=hoy + timedelta(days=10), respuesta=respuesta or "", fecha_respuesta=hoy if respuesta else None,
        )


def _beneficios_demo(delegacion, usuario):
    ninos = [
        ("24.567.891-6", "Martina Rojas Pizarro", date(2017, 5, 14), "F", "Constanza Pizarro", "entregado"),
        ("25.123.456-6", "Benjamín Castillo Araya", date(2018, 9, 2), "M", "Rodrigo Castillo", "registrado"),
        ("23.987.654-4", "Josefa Tapia Molina", date(2016, 12, 20), "F", "Paola Molina", "registrado"),
    ]
    for rut, nombre, nacimiento, sexo, apoderado, estado in ninos:
        beneficio = BeneficioNino(
            rut_nino=rut, nombre_nino=nombre, fecha_nacimiento=nacimiento, sexo=sexo, apoderado=apoderado,
            tipo="regalo_navidad", descripcion="Juguete según edad", delegacion=delegacion, estado=estado,
            fecha_entrega=timezone.localdate() if estado == "entregado" else None, registrado_por=usuario,
        )
        beneficio.full_clean(exclude=["rut_nino"])
        beneficio.rut_nino = normalizar_rut(rut)
        BeneficioNino.objects.get_or_create(rut_nino=beneficio.rut_nino, defaults={
            campo.name: getattr(beneficio, campo.name) for campo in BeneficioNino._meta.concrete_fields if campo.name not in ("id", "rut_nino", "creado_en", "actualizado_en")
        })
