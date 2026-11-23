import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from django.utils import timezone

from institucional.models import Autoridad, Cargo, Delegacion, Funcionario, Municipio, UnidadMunicipal
from laserena.rut import normalizar_rut
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, asegurar_grupos, asignar_grupo
from oficina.models import Ausencia, BeneficioNino, Carta, Reconocimiento
from oficina.transacciones import registrar_ausencia
from servicios.desempeno import metas_vigentes
from servicios.models import Actividad, Caso, Compromiso, Gestion, ItemMedicion, Meta, Periodo, Servicio, TareaPreparatoria

from .cargar_matriz import cargar_matriz

CLAVE_DEMO = "Serena-demo-2026"
PERIODO_DEMO_ANTERIOR = "Período demostración 2026"
CARGOS_DEMO_ANTERIORES = ("Gestor territorial", "Delegado territorial", "Consulta operativa", "Administración municipal")
ACCION_DEMO = "Registro de demostración de la matriz SGR"
ORIGEN_TUBO_DEMO = "Tubo de demostración"

# usuario, nombre, grupo, identificador, nombre en la ficha, cargo de la matriz, código de área, factor de avance.
# El factor deja a cada colaborador en un color distinto del semáforo; 0 = sin actividades demo.
CUENTAS_DEMO = [
    ("admin.demo", "Administrador", GRUPO_ADMINISTRADOR, "DEMO-ADM", "Administrador de demostración", "Coordinación de Delegaciones", "", 0),
    ("delegado.demo", "Delegado", GRUPO_SUPERVISOR, "DEMO-DEL", "Delegado de demostración", "Delegado", "", 0),
    ("consulta.demo", "Consulta", GRUPO_SUPERVISOR, "DEMO-CON", "Profesional PyG de demostración", "Profesional de Planificación y Gestión", "", 1.0),
    ("funcionario.demo", "Funcionario", GRUPO_ADMINISTRATIVO, "DEMO-001", "Territorial de demostración", "Territorial de Organizaciones Comunitarias", "COM1", 0.95),
    ("apoyo.demo", "Apoyo", GRUPO_ADMINISTRATIVO, "DEMO-APA", "Apoyo administrativo de demostración", "Apoyo Administrativo", "", 1.1),
    ("social.demo", "Gestor social", GRUPO_ADMINISTRATIVO, "DEMO-SOC", "Gestor social de demostración", "Gestor Social", "", 0.75),
    ("coserco.demo", "Coordinador", GRUPO_ADMINISTRATIVO, "DEMO-COS", "Coordinador de servicios de demostración", "Coordinador de Servicios Comunitarios", "", 0.45),
    ("seguridad.demo", "Gestor seguridad", GRUPO_ADMINISTRATIVO, "DEMO-SEG", "Gestor de seguridad de demostración", "Gestor de Seguridad", "", 0.9),
]


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

        resultado = cargar_matriz()
        periodo = resultado["periodo"]
        # Instalaciones anteriores usaban un período anual de demostración; queda como historial.
        Periodo.objects.filter(nombre=PERIODO_DEMO_ANTERIOR, estado="abierto").exclude(pk=periodo.pk).update(estado="cerrado")
        Cargo.objects.filter(nombre__in=CARGOS_DEMO_ANTERIORES).exclude(funcionarios__activo=True).update(activo=False)

        delegacion = Delegacion.objects.get(slug="centro")
        hoy = timezone.localdate()
        equipo = {}
        for username, nombre, grupo, identificador, nombre_completo, cargo, codigo_area, _ in CUENTAS_DEMO:
            usuario = _usuario_demo(username, nombre, "Demostración", grupo)
            funcionario, _ = Funcionario.objects.update_or_create(
                identificador=identificador,
                defaults={
                    "nombre_completo": nombre_completo,
                    "correo": usuario.email,
                    "delegacion": delegacion,
                    "cargo": Cargo.objects.get(nombre=cargo),
                    "codigo_area": codigo_area,
                    "usuario": usuario,
                    "activo": True,
                },
            )
            equipo[username] = funcionario
        usuario_admin = equipo["admin.demo"].usuario
        usuario_delegado = equipo["delegado.demo"].usuario
        funcionario = equipo["funcionario.demo"]

        for username, *_, factor in CUENTAS_DEMO:
            if factor:
                _actividades_matriz(equipo[username], periodo, hoy, factor, usuario_delegado)
                _tubo_demo(equipo[username], periodo, hoy, factor)

        item_atencion = ItemMedicion.objects.get(codigo="ATU")
        if hoy.weekday() < 5:
            pendiente, creada = Actividad.objects.get_or_create(
                funcionario=funcionario,
                periodo=periodo,
                item=item_atencion,
                descripcion="Celebración Día del Adulto Mayor en sede vecinal",
                defaults={"accion": "Coordinación con club de adulto mayor", "fecha": hoy, "contacto": "Presidenta del club", "telefono": "+56 9 3333 4444"},
            )
            if creada:
                TareaPreparatoria.objects.create(actividad=pendiente, tipo="sillas", descripcion="40 sillas y 6 mesas", realizada=True, realizada_en=timezone.now())
                TareaPreparatoria.objects.create(actividad=pendiente, tipo="colacion", descripcion="Colación para 40 personas")
                TareaPreparatoria.objects.create(actividad=pendiente, tipo="animacion", descripcion="Grupo folclórico")

        ingreso = max(periodo.fecha_inicio, hoy - timedelta(days=20))
        caso, _ = Caso.objects.get_or_create(
            identificacion="CASO-DEMO-001",
            defaults={
                "nombre": "Persona usuaria de demostración",
                "delegacion": delegacion,
                "tipo_atencion": "informes_sociales",
                "sub_atencion": "informe_aporte_material",
                "requiere_visita": True,
                "fecha_ingreso": ingreso,
                "fecha_programada_visita": ingreso + timedelta(days=5),
                "fecha_visita": ingreso + timedelta(days=5),
                "telefono": "+56 9 5555 6666",
                "observacion": "Caso ficticio: solicitud de materiales tras anegamiento de vivienda.",
            },
        )
        Gestion.objects.get_or_create(
            caso=caso,
            numero=1,
            defaults={"fecha": ingreso, "descripcion": "Primera atención en la delegación y agenda de visita."},
        )

        _cartas_demo(delegacion, funcionario, usuario_admin)
        _beneficios_demo(delegacion, usuario_delegado)
        _reconocimientos_demo(equipo, periodo, hoy, usuario_delegado)
        social = equipo["social.demo"]
        inicio_ausencia = periodo.fecha_inicio + timedelta(days=14)
        if not Ausencia.objects.filter(funcionario=social, periodo=periodo).exists():
            registrar_ausencia(
                Ausencia(
                    funcionario=social, periodo=periodo, fecha_inicio=inicio_ausencia, fecha_termino=inicio_ausencia + timedelta(days=1),
                    motivo="compensatorio", observacion="Días compensatorios de demostración",
                ),
                usuario_admin,
            )

        Actividad.asignar_codigos_pendientes()
        self.stdout.write(self.style.SUCCESS(
            f"Datos demo SGR cargados en {periodo.nombre}. Cuentas: "
            + ", ".join(f"{c[0]} ({c[5]})" for c in CUENTAS_DEMO)
            + f". Clave: {CLAVE_DEMO}."
        ))


def _dias_habiles(desde, hasta):
    dias = []
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def _actividades_matriz(funcionario, periodo, hoy, factor, revisor):
    """Actividades aprobadas en proporción al avance esperado: factor 1 deja al colaborador justo al día."""
    dias = _dias_habiles(periodo.fecha_inicio, min(hoy, periodo.fecha_termino)) or [periodo.fecha_inicio]
    avance = Decimal(str(periodo.avance_esperado(hoy))) / 100
    indice = Actividad.objects.filter(funcionario=funcionario, periodo=periodo).count()
    for meta in metas_vigentes(funcionario, periodo):
        item = meta.item
        if item.tipo_medicion == "conteo":
            esperadas = int((meta.objetivo * avance * Decimal(str(factor))).to_integral_value())
        elif item.tipo_medicion == "emergencia":
            esperadas = 1 if factor >= 0.9 else 0
        else:
            continue
        existentes = Actividad.objects.filter(funcionario=funcionario, periodo=periodo, item=item, accion=ACCION_DEMO).count()
        for numero in range(existentes, esperadas):
            Actividad.objects.create(
                funcionario=funcionario, periodo=periodo, item=item, fecha=dias[indice % len(dias)],
                descripcion=f"{item.nombre} · registro {numero + 1}", accion=ACCION_DEMO, estado="validada",
                revisada_por=revisor, revisada_en=timezone.now(),
            )
            indice += 1


def _tubo_demo(funcionario, periodo, hoy, factor):
    """Ingresos al tubo de quienes tienen la meta TUB; la proporción realizada sigue al factor."""
    if not Meta.objects.filter(periodo=periodo, cargo=funcionario.cargo, item__codigo="TUB").exists():
        return
    if Compromiso.objects.filter(responsable=funcionario, origen=ORIGEN_TUBO_DEMO, fecha_comprometida__range=(periodo.fecha_inicio, periodo.fecha_termino)).exists():
        return
    unidades = list(UnidadMunicipal.objects.filter(activa=True, tipo="interna")[:5])
    total = 5
    realizados = min(total, round(total * factor * 0.8))
    for numero in range(total):
        solicitud = min(hoy, periodo.fecha_inicio + timedelta(days=7 * numero))
        estado = "realizado" if numero < realizados else ("proceso" if numero == realizados else "pendiente")
        Compromiso.objects.create(
            delegacion=funcionario.delegacion, responsable=funcionario, origen=ORIGEN_TUBO_DEMO,
            solicitante=f"Junta de vecinos demostración {numero + 1}", territorio=funcionario.delegacion.nombre,
            descripcion=f"Requerimiento de demostración {numero + 1}: limpieza, poda o luminaria del sector.",
            fecha_solicitud=solicitud, fecha_comprometida=min(periodo.fecha_termino, solicitud + timedelta(days=14)),
            ambito="externo" if numero % 2 == 0 else "interno",
            area_apoyo=unidades[numero % len(unidades)] if unidades else None, estado=estado,
        )


def _reconocimientos_demo(equipo, periodo, hoy, usuario):
    registros = [
        ("apoyo.demo", "felicitacion", "Vecina del sector", "Felicita la atención amable y rápida en mesón.", "libro"),
        ("apoyo.demo", "felicitacion", "Presidente JJVV demostración", "Agradece la orientación para postular a fondos.", "correo"),
        ("coserco.demo", "reclamo", "Vecino del pasaje", "Operativo de limpieza comprometido no se realizó en la fecha.", "whatsapp"),
    ]
    for username, tipo, persona, situacion, medio in registros:
        Reconocimiento.objects.get_or_create(
            funcionario=equipo[username], periodo=periodo, situacion=situacion,
            defaults={"tipo": tipo, "fecha": max(periodo.fecha_inicio, hoy - timedelta(days=3)), "usuario_nombre": persona, "medio": medio, "registrado_por": usuario},
        )


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
        ("Junta de Vecinos Villa El Faro", "Solicitud de luminarias en pasaje Los Aromos", "derivada", None, "Sección Alumbrado Público", "delegado"),
        ("Club de Adulto Mayor Renacer", "Invitación a aniversario del club", "respondida", "Se confirma asistencia del delegado y apoyo con sillas.", "Patrocinios", "alcaldesa"),
        ("Vecina del sector centro", "Reclamo por microbasural en calle Cordovez", "ingresada", None, "Sección Aseo", "delegado"),
    ]
    for numero, (remitente, asunto, estado, respuesta, unidad, destinatario) in enumerate(cartas, start=1):
        if Carta.objects.filter(asunto=asunto).exists():
            continue
        hoy = timezone.localdate()
        Carta.objects.create(
            remitente=remitente, asunto=asunto, estado=estado, delegacion=delegacion, registrada_por=usuario,
            tipo="invitacion" if "Invitación" in asunto else ("reclamo" if "Reclamo" in asunto else "solicitud"),
            numero_oficina_partes=f"DEMO-{numero:03d}", destinatario=destinatario,
            encargado_seguimiento=UnidadMunicipal.objects.filter(nombre=unidad).first(),
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
