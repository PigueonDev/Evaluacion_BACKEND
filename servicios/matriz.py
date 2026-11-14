"""Catálogos tomados de la matriz SGR trimestral de las Delegaciones y del descriptor de funciones 2026.

Los ponderadores están en porcentaje (0,20 en la planilla = 20). Las metas son trimestrales.
"""

PERFIL_ADMINISTRADOR = "Administrador"
PERFIL_SUPERVISOR = "Supervisor"
PERFIL_ADMINISTRATIVO = "Administrativo"

# (nombre, sigla, perfil, descripción resumida del descriptor de funciones)
CARGOS = [
	("Coordinación de Delegaciones", "CDD", PERFIL_ADMINISTRADOR,
		"Administración Municipal, Departamento de Delegaciones. Define períodos, metas, cargos y cuentas del SGR."),
	("Delegado", "DEL", PERFIL_SUPERVISOR,
		"Representante de la alcaldía en el territorio. Delega el trabajo al equipo, aprueba actividades, registra ausencias, felicitaciones y reclamos."),
	("Profesional de Planificación y Gestión", "PYG", PERFIL_SUPERVISOR,
		"Responsable del llenado de la matriz SGR: informa al delegado fortalezas y debilidades de cada colaborador y gestiona la reunión semanal."),
	("Apoyo Administrativo", "APA", PERFIL_ADMINISTRATIVO,
		"Agenda del delegado, atención de público, registro de atenciones y llamadas preventivas, inventario trimestral e informe a Comunicaciones."),
	("Territorial de Organizaciones Comunitarias", "COM", PERFIL_ADMINISTRATIVO,
		"Registro de Organizaciones (OROC): formación, legalización y asesoría de juntas de vecinos y organizaciones funcionales (leyes 19.418 y 20.500)."),
	("Gestor Social", "SOC", PERFIL_ADMINISTRATIVO,
		"Atención de casos sociales: recepción, visita en terreno, informe social, derivación y entrega de beneficios."),
	("Coordinador de Servicios Comunitarios", "COS", PERFIL_ADMINISTRATIVO,
		"Enlace con DISERCO: operativos de limpieza, desmalezado y recuperación de espacios; cuadrillas de empleabilidad y emergencia."),
	("Gestor de Seguridad", "SEG", PERFIL_ADMINISTRATIVO,
		"Seguridad ciudadana: comités de seguridad, incivilidades, mediación, recuperación de espacios públicos e infracciones."),
	("Atención de Público", "ATP", PERFIL_ADMINISTRATIVO,
		"Primera línea de atención presencial y telefónica según el protocolo de atención (Decreto N° 3096 de 2024)."),
	("Gestor de Compras y Proyectos", "GCP", PERFIL_ADMINISTRATIVO,
		"Tramita los requerimientos de adquisiciones de la dirección y controla el Plan Anual de Compras."),
]

# (código, nombre, tipo de medición)
ITEMS = [
	("ATU", "Atención de usuario telefónica y presencial", "conteo"),
	("LLP", "Llamadas preventivas a usuarios", "conteo"),
	("INV", "Informe de inventarios", "conteo"),
	("ICO", "Informe a Comunicaciones", "conteo"),
	("EME", "Emergencia", "emergencia"),
	("TUB", "Soluciones de ingresos al tubo", "tasa_tubo"),
	("OTG", "Otras gestiones", "sin_puntaje"),
	("IPE", "Informes de personal", "conteo"),
	("ITR", "Informe de trabajo semanal", "conteo"),
	("ODE", "Operativo delegación", "conteo"),
	("ODI", "Operativo DISERCO", "conteo"),
	("TAL", "Talleres", "conteo"),
	("TER", "Terreno", "conteo"),
	("ARU", "Atención de requerimiento de usuario", "conteo"),
	("VRO", "Visitas y reuniones con organizaciones", "conteo"),
	("COO", "Conformación de organizaciones", "conteo"),
	("GTA", "Gestión de talleres y actividades", "conteo"),
	("ASP", "Atención social a usuario presencial", "conteo"),
	("VIT", "Visita a terreno", "conteo"),
	("EIN", "Entrega de informe social", "conteo"),
	("EBE", "Entrega de beneficio", "conteo"),
	("RSE", "Reunión semanal con el equipo", "conteo"),
	("SPU", "Solución de problemas a usuarios particulares", "conteo"),
	("FCS", "Formación de comités de seguridad", "conteo"),
	("LIN", "Levantamiento de incivilidades", "conteo"),
	("GME", "Gestión de mediación", "conteo"),
	("REP", "Recuperación de espacios públicos", "conteo"),
	("INF", "Infracciones varias", "conteo"),
	("SAT", "Salidas a terreno", "conteo"),
]

# Por cargo: (código de ítem, ponderador %, meta trimestral). En «emergencia» la meta es 1: cumple si atendió alguna.
# En «tasa_tubo» la meta es el % de ingresos al tubo realizados (0,8 en la planilla = 80).
METAS_POR_CARGO = {
	"Apoyo Administrativo": [("LLP", 30, 90), ("INV", 25, 1), ("ATU", 20, 240), ("ICO", 20, 12), ("EME", 5, 1)],
	"Coordinador de Servicios Comunitarios": [
		("ODE", 15, 24), ("ARU", 15, 24), ("TUB", 15, 80), ("IPE", 10, 3), ("ITR", 10, 12),
		("ODI", 10, 12), ("TAL", 10, 12), ("TER", 10, 24), ("EME", 5, 1),
	],
	"Territorial de Organizaciones Comunitarias": [
		("COO", 25, 1), ("TUB", 25, 80), ("ATU", 15, 60), ("VRO", 15, 24), ("GTA", 15, 6), ("EME", 5, 1),
	],
	"Gestor Social": [("EIN", 25, 40), ("ASP", 20, 90), ("VIT", 20, 12), ("EBE", 20, 8), ("TUB", 10, 80), ("EME", 5, 1)],
	"Profesional de Planificación y Gestión": [("TUB", 35, 80), ("SPU", 30, 8), ("RSE", 15, 12), ("EME", 5, 1)],
	"Gestor de Seguridad": [
		("FCS", 20, 36), ("LIN", 20, 40), ("INF", 15, 45), ("TUB", 15, 80), ("GME", 10, 50), ("REP", 10, 50), ("SAT", 10, 45),
	],
}

# (nombre, sigla, tipo, descripción). Áreas de apoyo, derivaciones y encargados de seguimiento que aparecen en los tubos.
UNIDADES = [
	("Dirección de Servicios a la Comunidad", "DISERCO", "interna", "Aseo, áreas verdes, alumbrado, maquinarias y cuadrillas."),
	("Sección Aseo", "ASEO", "interna", "Sección de DISERCO."),
	("Sección Áreas Verdes", "AAVV", "interna", "Poda y mantención de áreas verdes."),
	("Sección Alumbrado Público", "ALUMBRADO", "interna", "Luminarias y evaluación en terreno."),
	("Maquinarias", "MAQ", "interna", "Maquinaria pesada municipal."),
	("Cuadrilla de la delegación", "CUADRILLA", "interna", "Cuadrillas de empleabilidad y de emergencia."),
	("Dirección de Tránsito", "TRANSITO", "interna", "Señalética, estacionamiento y tránsito."),
	("Seguridad Ciudadana", "SEGURIDAD", "interna", "Prevención y coordinación de seguridad."),
	("Coordinación de Servicios Comunitarios", "COSERCO", "interna", "Coordinación territorial con DISERCO."),
	("Departamento Social", "SOCIAL", "interna", "Desarrollo social, subsidios y Registro Social de Hogares."),
	("Sección Adulto Mayor", "AM", "interna", "Programas para personas mayores."),
	("Área Mujeres", "MUJERES", "interna", "Programas de género."),
	("Sección Infancia y Juventud", "INFANCIA", "interna", "Programas de niñez y juventud."),
	("Registro de Organizaciones Comunitarias", "OROC", "interna", "Constitución y vigencia de organizaciones (leyes 19.418 y 20.500)."),
	("Departamento de Gestión Comunitaria", "GESTION COM", "interna", "Organizaciones comunitarias territoriales y funcionales."),
	("Departamento de Cultura", "CULTURA", "interna", "Actividades culturales."),
	("Patentes", "PATENTES", "interna", "Permisos y patentes comerciales."),
	("Patrocinios", "PATROCINIOS", "interna", "Patrocinio municipal de eventos."),
	("Fomento Productivo", "FOMENTO", "interna", "Emprendimiento y ferias."),
	("Turismo", "TURISMO", "interna", "Promoción turística."),
	("Dirección de Obras Municipales", "DOM", "interna", "Permisos de edificación y espacio público."),
	("Asesoría Jurídica", "JURIDICA", "interna", "Asesoría legal municipal."),
	("Alcaldía y Gabinete", "GABINETE", "interna", "Pronunciamiento de la alcaldesa y su gabinete."),
	("Administración y Finanzas", "DAF", "interna", "Administración, adquisiciones y control interno."),
	("Secretaría Comunal de Planificación", "SECPLAN", "interna", "Proyectos y postulaciones."),
	("Delegación municipal", "DELEGACION", "interna", "Equipo de la propia delegación."),
	("Aguas del Valle", "", "externa", "Empresa sanitaria."),
	("CGE", "", "externa", "Empresa eléctrica."),
	("Registro Civil", "", "externa", "Servicio de Registro Civil e Identificación."),
	("BancoEstado", "", "externa", "Trámites bancarios de organizaciones."),
	("Gobierno Regional", "GORE", "externa", "Fondos y proyectos regionales."),
]

# Sectores que aparecen en la columna TERRITORIO de los tubos de cada delegación.
SECTORES_POR_DELEGACION = {
	"las-companias": ["Latorre", "Rukalaf", "Toqui", "Zorrilla"],
	"la-antena": ["Alfalfares", "Ceres", "La Antena", "La Florida"],
}

NUMERO_ROMANO = {1: "I", 2: "II", 3: "III", 4: "IV"}


def trimestre_de(fecha):
	"""(nombre, inicio, término) del trimestre calendario que contiene `fecha`."""
	from datetime import date, timedelta

	numero = (fecha.month - 1) // 3 + 1
	inicio = date(fecha.year, 3 * numero - 2, 1)
	siguiente = date(fecha.year + 1, 1, 1) if numero == 4 else date(fecha.year, 3 * numero + 1, 1)
	return f"{NUMERO_ROMANO[numero]} Trimestre {fecha.year}", inicio, siguiente - timedelta(days=1)
