from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from institucional.models import Cargo, Delegacion, Funcionario, UnidadMunicipal
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, asignar_grupo
from oficina.models import Reconocimiento

from .desempeno import alerta_rrhh, resumen_equipo, resumen_funcionario
from .management.commands.cargar_matriz import cargar_matriz
from .matriz import CARGOS, METAS_POR_CARGO, trimestre_de
from .models import CODIGO_VERIFICADOR, Actividad, Caso, Compromiso, ItemMedicion, Meta, Periodo

HOY = date(2026, 11, 16)


def cuenta(username, grupo):
	usuario = get_user_model().objects.create_user(username=username, password="x")
	asignar_grupo(usuario, grupo)
	return usuario


def aprobar(funcionario, periodo, item, cantidad, fecha=HOY):
	for numero in range(cantidad):
		Actividad.objects.create(funcionario=funcionario, periodo=periodo, item=item, fecha=fecha, descripcion=f"Registro {numero}", accion="Prueba", estado="validada")


class CargarMatrizTest(TestCase):
	def test_trimestre_y_carga_idempotente(self):
		self.assertEqual(trimestre_de(date(2026, 11, 14)), ("IV Trimestre 2026", date(2026, 10, 1), date(2026, 12, 31)))
		self.assertEqual(trimestre_de(date(2027, 2, 1))[0], "I Trimestre 2027")
		primera = cargar_matriz(date(2026, 11, 14))
		segunda = cargar_matriz(date(2026, 11, 14))
		self.assertGreater(primera["metas_nuevas"], 0)
		self.assertEqual(segunda["metas_nuevas"], 0)
		self.assertEqual(Cargo.objects.count(), len(CARGOS))
		self.assertEqual(Periodo.objects.get().nombre, "IV Trimestre 2026")
		self.assertEqual(Meta.objects.count(), sum(len(metas) for metas in METAS_POR_CARGO.values()))
		self.assertTrue(UnidadMunicipal.objects.filter(nombre="Dirección de Obras Municipales").exists())

	def test_ponderadores_por_cargo(self):
		cargar_matriz(date(2026, 11, 14))
		for nombre, metas in METAS_POR_CARGO.items():
			suma = sum(Meta.objects.filter(cargo__nombre=nombre).values_list("ponderador", flat=True))
			esperado = Decimal(85) if nombre == "Profesional de Planificación y Gestión" else Decimal(100)
			self.assertEqual(suma, esperado, nombre)
		self.assertEqual(Cargo.objects.get(nombre="Delegado").perfil, GRUPO_SUPERVISOR)
		self.assertEqual(Cargo.objects.get(nombre="Gestor Social").sigla, "SOC")
		self.assertTrue(Cargo.objects.get(nombre="Gestor Social").funciones.filter(codigo="EIN").exists())

	def test_actualizar_metas_sube_version(self):
		cargar_matriz(date(2026, 11, 14))
		meta = Meta.objects.get(cargo__nombre="Gestor Social", item__codigo="EIN")
		meta.objetivo = 1
		meta.save()
		cargar_matriz(date(2026, 11, 14), actualizar_metas=True)
		meta.refresh_from_db()
		self.assertEqual(meta.objetivo, 40)
		self.assertEqual(meta.version, 2)


class DesempenoMatrizTest(TestCase):
	def setUp(self):
		patcher = mock.patch("django.utils.timezone.localdate", return_value=HOY)
		patcher.start()
		self.addCleanup(patcher.stop)
		cargar_matriz(HOY)
		self.periodo = Periodo.objects.get(nombre="IV Trimestre 2026")
		self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="-", enfoque="-")
		self.apoyo = Funcionario.objects.create(identificador="A-1", nombre_completo="Apoyo", delegacion=self.centro, cargo=Cargo.objects.get(nombre="Apoyo Administrativo"))
		self.territorial = Funcionario.objects.create(
			identificador="T-1", nombre_completo="Territorial", delegacion=self.centro,
			cargo=Cargo.objects.get(nombre="Territorial de Organizaciones Comunitarias"), codigo_area="com1",
		)
		self.items = {item.codigo: item for item in ItemMedicion.objects.all()}
		self.registra = cuenta("registra", GRUPO_SUPERVISOR)

	def test_cumplimiento_ponderado_con_tope_por_item(self):
		aprobar(self.apoyo, self.periodo, self.items["LLP"], 45)
		aprobar(self.apoyo, self.periodo, self.items["INV"], 3)
		resumen = resumen_funcionario(self.apoyo, self.periodo, HOY)
		por_item = {fila["meta"].item.codigo: fila for fila in resumen["filas"]}
		self.assertAlmostEqual(por_item["LLP"]["cumplimiento"], 50)
		self.assertAlmostEqual(por_item["INV"]["cumplimiento"], 120)
		self.assertAlmostEqual(resumen["gestion"], 30 * 0.5 + 25 * 1.2)
		self.assertEqual(resumen["suma_ponderadores"], 100)
		self.assertEqual(resumen["ingresos"], 48)
		self.assertEqual(resumen["ultimo_ingreso"], HOY)

	def test_emergencia_y_tasa_del_tubo(self):
		aprobar(self.territorial, self.periodo, self.items["EME"], 1)
		for numero, estado in enumerate(("realizado", "realizado", "realizado", "pendiente")):
			Compromiso.objects.create(
				delegacion=self.centro, responsable=self.territorial, origen="Tubo", solicitante=f"S{numero}", territorio="Centro",
				descripcion="-", fecha_comprometida=date(2026, 11, 20), estado=estado,
			)
		Compromiso.objects.create(
			delegacion=self.centro, responsable=self.territorial, origen="Tubo", solicitante="Otro trimestre", territorio="Centro",
			descripcion="-", fecha_comprometida=date(2027, 1, 20), estado="pendiente",
		)
		filas = {fila["meta"].item.codigo: fila for fila in resumen_funcionario(self.territorial, self.periodo, HOY)["filas"]}
		self.assertEqual(filas["EME"]["cumplimiento"], 100)
		self.assertEqual(filas["TUB"]["avance"], 75)
		self.assertAlmostEqual(filas["TUB"]["cumplimiento"], 75 / 80 * 100)

	def test_felicitaciones_con_maximo_reclamos_y_piso(self):
		for numero in range(4):
			Reconocimiento.objects.create(tipo="felicitacion", funcionario=self.apoyo, periodo=self.periodo, fecha=HOY, registrado_por=self.registra, usuario_nombre="V", situacion=f"Buena atención {numero}")
		resumen = resumen_funcionario(self.apoyo, self.periodo, HOY)
		self.assertEqual(resumen["felicitaciones"], 4)
		self.assertEqual(resumen["bono"], 30)
		self.assertEqual(resumen["total"], 30)
		Reconocimiento.objects.create(tipo="reclamo", funcionario=self.territorial, periodo=self.periodo, fecha=HOY, registrado_por=self.registra, usuario_nombre="V", situacion="Mala atención")
		resumen = resumen_funcionario(self.territorial, self.periodo, HOY)
		self.assertEqual(resumen["descuento"], 20)
		self.assertEqual(resumen["total"], 0)
		Reconocimiento.objects.update(estado="anulado")
		self.assertEqual(resumen_funcionario(self.apoyo, self.periodo, HOY)["bono"], 0)

	def test_tope_total_y_semaforo(self):
		self.periodo.tope_cumplimiento = 100
		self.periodo.save()
		for codigo, cantidad in (("LLP", 200), ("INV", 5), ("ATU", 400), ("ICO", 20), ("EME", 1)):
			aprobar(self.apoyo, self.periodo, self.items[codigo], cantidad)
		resumen = resumen_funcionario(self.apoyo, self.periodo, HOY)
		self.assertEqual(resumen["total"], 100)
		self.assertEqual(resumen["semaforo"], "verde")
		self.assertTrue(resumen["cumple_minimo"])
		self.assertEqual(resumen_funcionario(self.territorial, self.periodo, HOY)["semaforo"], "rojo")

	def test_ranking_deja_fuera_a_quien_no_tiene_metas(self):
		delegado = Funcionario.objects.create(identificador="D-1", nombre_completo="Delegado", delegacion=self.centro, cargo=Cargo.objects.get(nombre="Delegado"))
		aprobar(self.territorial, self.periodo, self.items["ATU"], 30)
		equipo = resumen_equipo([delegado, self.apoyo, self.territorial], self.periodo, HOY)
		self.assertEqual([fila["funcionario"] for fila in equipo["filas"]], [self.territorial, self.apoyo, delegado])
		self.assertEqual([fila["ranking"] for fila in equipo["filas"]], [1, 2, None])
		self.assertAlmostEqual(equipo["promedio"], (15 * 30 / 60) / 2)

	def test_alerta_rrhh_con_reclamos_en_dos_trimestres_seguidos(self):
		anterior = Periodo.objects.create(nombre="III Trimestre 2026", fecha_inicio=date(2026, 7, 1), fecha_termino=date(2026, 9, 30), estado="cerrado")
		Reconocimiento.objects.create(tipo="reclamo", funcionario=self.apoyo, periodo=self.periodo, fecha=HOY, registrado_por=self.registra, usuario_nombre="V", situacion="Uno")
		self.assertFalse(alerta_rrhh(self.apoyo, self.periodo))
		Reconocimiento.objects.create(tipo="reclamo", funcionario=self.apoyo, periodo=anterior, fecha=date(2026, 8, 3), registrado_por=self.registra, usuario_nombre="V", situacion="Dos")
		self.assertTrue(alerta_rrhh(self.apoyo, self.periodo))

	def test_codigo_verificador_por_area_y_busqueda(self):
		aprobar(self.territorial, self.periodo, self.items["ATU"], 2, fecha=date(2026, 10, 6))
		aprobar(self.apoyo, self.periodo, self.items["ATU"], 1, fecha=date(2026, 10, 6))
		codigos = list(Actividad.objects.order_by("pk").values_list("codigo_verificador", flat=True))
		self.assertEqual(codigos, ["COM1-1006-001", "COM1-1006-002", "APA-1006-001"])
		self.assertTrue(all(CODIGO_VERIFICADOR.match(codigo) for codigo in codigos))
		usuario = cuenta("territorial", GRUPO_ADMINISTRATIVO)
		self.territorial.usuario = usuario
		self.territorial.save()
		self.client.force_login(usuario)
		respuesta = self.client.get(reverse("servicios:actividad_codigo"), {"codigo": "com1-1006-002"})
		self.assertEqual(respuesta.context["actividad"], Actividad.objects.get(codigo_verificador="COM1-1006-002"))
		inexistente = self.client.get(reverse("servicios:actividad_codigo"), {"codigo": "SEG-1006-001"})
		self.assertContains(inexistente, "No hay una actividad con ese código")

	def test_codigos_pendientes_de_actividades_anteriores(self):
		sin_sigla = Funcionario.objects.create(identificador="X-1", nombre_completo="Sin sigla", delegacion=self.centro, cargo=Cargo.objects.create(nombre="Cargo antiguo"))
		aprobar(sin_sigla, self.periodo, self.items["ATU"], 1)
		self.assertIsNone(Actividad.objects.get().codigo_verificador)
		sin_sigla.codigo_area = "PYG"
		sin_sigla.save()
		self.assertEqual(Actividad.asignar_codigos_pendientes(), 1)
		self.assertEqual(Actividad.objects.get().codigo_verificador, f"PYG-{HOY:%m%d}-001")

	def test_resumen_matriz_solo_para_supervision_y_en_su_ambito(self):
		norte = Delegacion.objects.create(nombre="Norte", slug="norte", territorio="-", enfoque="-")
		Funcionario.objects.create(identificador="N-1", nombre_completo="Colaborador del norte", delegacion=norte, cargo=self.apoyo.cargo)
		supervisor = cuenta("sup", GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=supervisor, identificador="S-1", nombre_completo="Delegada", delegacion=self.centro, cargo=Cargo.objects.get(nombre="Delegado"))
		administrativo = cuenta("adm-op", GRUPO_ADMINISTRATIVO)
		self.apoyo.usuario = administrativo
		self.apoyo.save()
		self.client.force_login(administrativo)
		self.assertEqual(self.client.get(reverse("servicios:resumen_matriz")).status_code, 403)
		self.client.force_login(supervisor)
		respuesta = self.client.get(reverse("servicios:resumen_matriz"), {"delegacion": norte.pk})
		self.assertContains(respuesta, "Territorial")
		self.assertNotContains(respuesta, "Colaborador del norte")
		self.client.force_login(cuenta("admin", GRUPO_ADMINISTRADOR))
		self.assertContains(self.client.get(reverse("servicios:resumen_matriz"), {"delegacion": norte.pk}), "Colaborador del norte")


class CasoSocialTest(TestCase):
	def setUp(self):
		self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="-", enfoque="-")

	def caso(self, **extra):
		datos = {"identificacion": "C-1", "nombre": "Persona", "delegacion": self.centro, "fecha_ingreso": date(2026, 10, 1)}
		datos.update(extra)
		return Caso(**datos)

	def test_subatencion_debe_corresponder_al_tipo(self):
		with self.assertRaises(ValidationError) as error:
			self.caso(tipo_atencion="gestion_subsidios", sub_atencion="informe_aporte_material").full_clean()
		self.assertIn("sub_atencion", error.exception.message_dict)
		caso = self.caso(tipo_atencion="gestion_subsidios", sub_atencion="pgu", rut="14.235.165-k")
		caso.full_clean()
		self.assertEqual(caso.rut, "14235165-K")

	def test_fechas_en_orden_y_visita_marcada(self):
		with self.assertRaises(ValidationError) as error:
			self.caso(requiere_visita=True, fecha_programada_visita=date(2026, 9, 30)).full_clean()
		self.assertIn("fecha_programada_visita", error.exception.message_dict)
		with self.assertRaises(ValidationError) as error:
			self.caso(fecha_visita=date(2026, 10, 3)).full_clean()
		self.assertIn("requiere_visita", error.exception.message_dict)

	def test_plazos_de_la_gestion_social(self):
		caso = self.caso(
			requiere_visita=True, fecha_programada_visita=date(2026, 10, 15), fecha_visita=date(2026, 10, 15),
			fecha_entrega_informe=date(2026, 10, 17), fecha_entrega_beneficio=date(2026, 10, 28),
		)
		excedidos = {tramo["etiqueta"] for tramo in caso.plazos_excedidos}
		self.assertEqual(excedidos, {"Ingreso a visita programada", "Informe a entrega del beneficio", "Ingreso a entrega del beneficio"})
