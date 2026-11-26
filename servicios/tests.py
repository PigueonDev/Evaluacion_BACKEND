import shutil
import tempfile
import uuid
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from institucional.models import Cargo, Delegacion, Funcionario
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, asignar_grupo

from .models import Actividad, Caso, Compromiso, Gestion, ItemMedicion, Meta, Periodo, Servicio

HOY_PRUEBAS = date(2026, 6, 17)
_localdate_real = timezone.localdate


def fijar_hoy(test, hoy=HOY_PRUEBAS):
	"""Fija la fecha local para probar las reglas de semana laboral sin depender del reloj."""
	patcher = mock.patch("django.utils.timezone.localdate", side_effect=lambda *a, **k: hoy if not a and not k else _localdate_real(*a, **k))
	patcher.start()
	test.addCleanup(patcher.stop)


def con_grupo(usuario, grupo):
	asignar_grupo(usuario, grupo)
	return usuario


class ReglasSgrTest(TestCase):
	def setUp(self):
		usuario = get_user_model().objects.create_user(username="funcionario-demo", password="demo")
		delegacion = Delegacion.objects.create(
			nombre="Delegación de prueba",
			slug="delegacion-prueba",
			territorio="Territorio ficticio",
			enfoque="Demostración académica",
		)
		cargo = Cargo.objects.create(nombre="Cargo de prueba")
		self.funcionario = Funcionario.objects.create(
			usuario=usuario,
			identificador="F-001",
			nombre_completo="Funcionario de prueba",
			delegacion=delegacion,
			cargo=cargo,
		)
		self.item = ItemMedicion.objects.create(codigo="TEST-001", nombre="Ítem de prueba")
		self.periodo = Periodo.objects.create(
			nombre="Período de prueba",
			fecha_inicio=date(2026, 1, 1),
			fecha_termino=date(2026, 12, 31),
		)

	def test_periodo_rechaza_termino_anterior(self):
		self.periodo.fecha_termino = date(2025, 12, 31)
		with self.assertRaises(ValidationError):
			self.periodo.full_clean()

	def test_meta_requiere_objetivo_positivo(self):
		meta = Meta(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=0, ponderador=100)
		with self.assertRaises(ValidationError):
			meta.full_clean()

	def test_solo_actividad_validada_aporta_al_avance(self):
		meta = Meta(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=2, ponderador=100)
		Actividad.objects.create(
			funcionario=self.funcionario,
			periodo=self.periodo,
			item=self.item,
			descripcion="Actividad pendiente",
			accion="Acción de prueba",
			estado="pendiente",
		)
		Actividad.objects.create(
			funcionario=self.funcionario,
			periodo=self.periodo,
			item=self.item,
			descripcion="Actividad validada",
			accion="Acción de prueba",
			solicitante="Vecino solicitante",
			telefono="+56 9 1111 2222",
			estado="validada",
		)
		self.assertEqual(meta.avance_aprobado, 1)
		self.assertEqual(meta.cumplimiento, 50)


class PanelesPrivadosTest(TestCase):
	PANELES = (
		"servicios:panel_municipal",
		"servicios:actividades",
		"servicios:casos",
		"servicios:agenda",
		"servicios:consulta",
		"servicios:aprobaciones",
		"servicios:evidencias",
		"institucional:panel",
	)
	MENU = ("servicios:actividades", "servicios:consulta", "servicios:aprobaciones", "organizaciones:listado", "institucional:usuarios", "institucional:grupos")

	def setUp(self):
		modelo_usuario = get_user_model()
		self.staff = con_grupo(modelo_usuario.objects.create_user(username="staff-demo", password="demo"), GRUPO_ADMINISTRADOR)
		self.vecino = modelo_usuario.objects.create_user(username="vecino-demo", password="demo")

	def test_visitante_es_enviado_al_login(self):
		for nombre in self.PANELES:
			url = reverse(nombre)
			respuesta = self.client.get(url)
			self.assertRedirects(respuesta, f"{reverse('institucional:acceso')}?next={url}", msg_prefix=nombre)

	def test_usuario_sin_permiso_staff_no_entra(self):
		self.client.force_login(self.vecino)
		for nombre in self.PANELES:
			self.assertEqual(self.client.get(reverse(nombre)).status_code, 302, nombre)

	def test_personal_ve_los_paneles(self):
		self.client.force_login(self.staff)
		for nombre in self.PANELES:
			self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

	def test_menu_oculta_paneles_a_visitantes(self):
		respuesta = self.client.get(reverse("institucional:inicio"))
		for nombre in self.MENU:
			self.assertNotContains(respuesta, f'href="{reverse(nombre)}"')
		self.client.force_login(self.staff)
		respuesta = self.client.get(reverse("institucional:inicio"))
		for nombre in self.MENU:
			self.assertContains(respuesta, f'href="{reverse(nombre)}"')


class InyeccionSqlTest(TestCase):
	ATAQUES = [
		"' OR '1'='1",
		"'; DROP TABLE servicios_servicio; --",
		"\" OR 1=1 --",
		"1 UNION SELECT username, password FROM auth_user --",
		"%' AND SLEEP(5) AND '%'='",
	]

	def setUp(self):
		self.staff = con_grupo(get_user_model().objects.create_user(username="staff-demo", password="demo"), GRUPO_ADMINISTRADOR)
		Servicio.objects.create(slug="licencia", nombre="Licencia de conducir", categoria="Tránsito", unidad="Tránsito", descripcion="Demo")

	def test_busquedas_no_ejecutan_sql_inyectado(self):
		self.client.force_login(self.staff)
		for ataque in self.ATAQUES:
			for nombre in ("servicios:catalogo", "servicios:actividades", "servicios:agenda", "servicios:casos", "servicios:consulta"):
				respuesta = self.client.get(reverse(nombre), {"q": ataque, "estado": ataque, "categoria": ataque})
				self.assertEqual(respuesta.status_code, 200, f"{nombre}: {ataque}")
				self.assertNotContains(respuesta, "pbkdf2_sha256")
			respuesta = self.client.get(reverse("servicios:catalogo"), {"q": ataque})
			self.assertEqual(respuesta.context["total"], 0, ataque)
		self.assertEqual(Servicio.objects.count(), 1)

	def test_filtros_fuera_de_lista_blanca_se_ignoran(self):
		self.client.force_login(self.staff)
		respuesta = self.client.get(reverse("servicios:actividades"), {"estado": "' OR 1=1 --"})
		self.assertEqual(respuesta.context["estado_activo"], "")
		respuesta = self.client.get(reverse("servicios:catalogo"), {"categoria": "' OR 1=1 --"})
		self.assertEqual(respuesta.context["categoria_activa"], "todos")

	def test_busqueda_se_recorta(self):
		respuesta = self.client.get(reverse("servicios:catalogo"), {"q": "a" * 5000})
		self.assertEqual(len(respuesta.context["busqueda"]), 100)


class MantenedoresCristhopherTest(TestCase):
	"""SCRUM-10, SCRUM-12, SCRUM-15, SCRUM-16, SCRUM-17, SCRUM-18 y SCRUM-21."""

	def setUp(self):
		fijar_hoy(self)
		modelo = get_user_model()
		self.user = con_grupo(modelo.objects.create_user(username="func-centro", password="clave-demo-123"), GRUPO_ADMINISTRATIVO)
		self.otro = con_grupo(modelo.objects.create_user(username="func-norte", password="clave-demo-123"), GRUPO_ADMINISTRATIVO)
		self.centro = Delegacion.objects.create(nombre="Centro sprint", slug="centro-sprint", territorio="Centro", enfoque="Demo")
		self.norte = Delegacion.objects.create(nombre="Norte sprint", slug="norte-sprint", territorio="Norte", enfoque="Demo")
		self.cargo = Cargo.objects.create(nombre="Gestor sprint")
		self.funcionario = Funcionario.objects.create(
			usuario=self.user, identificador="F-C", nombre_completo="Ana Centro", delegacion=self.centro, cargo=self.cargo,
		)
		self.companero = Funcionario.objects.create(
			identificador="F-C2", nombre_completo="Bruno Centro", delegacion=self.centro, cargo=self.cargo,
		)
		self.ajeno = Funcionario.objects.create(
			usuario=self.otro, identificador="F-N", nombre_completo="Luis Norte", delegacion=self.norte, cargo=self.cargo,
		)
		self.delegado_user = con_grupo(modelo.objects.create_user(username="delegado-centro", password="clave-demo-123"), GRUPO_SUPERVISOR)
		self.consulta_user = con_grupo(modelo.objects.create_user(username="consulta-centro", password="clave-demo-123"), GRUPO_SUPERVISOR)
		Funcionario.objects.create(
			usuario=self.delegado_user, identificador="F-D", nombre_completo="Jefa Centro", delegacion=self.centro, cargo=self.cargo,
		)
		Funcionario.objects.create(
			usuario=self.consulta_user, identificador="F-Q", nombre_completo="Consulta Centro", delegacion=self.centro, cargo=self.cargo,
		)
		self.item = ItemMedicion.objects.create(codigo="SPR-001", nombre="Ítem sprint")
		self.periodo = Periodo.objects.create(nombre="Sprint 2026", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))
		self.cerrado = Periodo.objects.create(
			nombre="Cerrado 2025", fecha_inicio=date(2025, 1, 1), fecha_termino=date(2025, 12, 31), estado="cerrado",
		)
		self.client.force_login(self.user)

	def _datos_actividad(self, **extra):
		datos = {
			"fecha": "2026-06-15",
			"periodo": str(self.periodo.pk),
			"item": str(self.item.pk),
			"descripcion": "Visita territorial de demostración",
			"accion": "Orientación a la junta de vecinos",
			"solicitante": "Junta de vecinos Los Aromos",
			"contacto": "Junta de vecinos",
			"telefono": "+56 9 1111 2222",
			"tareas-TOTAL_FORMS": "4",
			"tareas-INITIAL_FORMS": "0",
			"tareas-MIN_NUM_FORMS": "0",
			"tareas-MAX_NUM_FORMS": "1000",
			"tareas-0-descripcion": "Gestión de sillas",
		}
		datos.update(extra)
		return datos

	def _datos_compromiso(self, **extra):
		datos = {
			"delegacion": str(self.centro.pk),
			"responsable": str(self.funcionario.pk),
			"origen": "Solicitud vecinal",
			"solicitante": "Junta Los Aromos",
			"territorio": "Centro histórico",
			"descripcion": "Reparar la luminaria de la plaza",
			"fecha_comprometida": "2026-11-20",
			"observacion": "",
		}
		datos.update(extra)
		return datos

	def test_scrum10_rechaza_actividad_incompleta_periodo_cerrado_y_telefono(self):
		respuesta = self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad(descripcion=""))
		self.assertEqual(respuesta.status_code, 200)
		self.assertContains(respuesta, "Este campo es obligatorio.")
		self.assertEqual(Actividad.objects.count(), 0)

		respuesta = self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad(periodo=str(self.cerrado.pk)))
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(Actividad.objects.count(), 0)

		respuesta = self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad(fecha="2027-01-02"))
		self.assertEqual(respuesta.status_code, 200)
		self.assertContains(respuesta, "dentro del período seleccionado")
		self.assertEqual(Actividad.objects.count(), 0)

		respuesta = self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad(telefono="no-es-telefono"))
		self.assertEqual(respuesta.status_code, 200)
		self.assertContains(respuesta, "dígitos")
		self.assertEqual(Actividad.objects.count(), 0)

	def test_scrum10_confirma_el_identificador_al_guardar(self):
		respuesta = self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad(), follow=True)
		actividad = Actividad.objects.get()
		self.assertContains(respuesta, str(actividad.codigo_evidencia))
		self.assertContains(respuesta, "Identificador")
		self.assertEqual(actividad.estado, "pendiente")
		self.assertEqual(actividad.funcionario, self.funcionario)

	def test_scrum12_limita_tres_gestiones_y_cuenta_una_vez(self):
		caso = Caso.objects.create(identificacion="P-100", nombre="Persona usuaria", delegacion=self.centro)
		actividad = Actividad.objects.create(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item,
			descripcion="Atención uno", accion="Orientar",
		)
		Gestion.objects.create(caso=caso, numero=1, descripcion="Primera", fecha=date(2026, 2, 1), actividad=actividad)
		for numero in (2, 3):
			Gestion.objects.create(caso=caso, numero=numero, descripcion=f"Gestión {numero}", fecha=date(2026, 2, numero))
		self.assertEqual(caso.atenciones_contadas(), 3)
		respuesta = self.client.get(reverse("servicios:gestion_nueva", args=[caso.pk]), follow=True)
		self.assertContains(respuesta, "tres gestiones")
		self.assertEqual(caso.gestiones.count(), 3)
		cuarta = Gestion(caso=caso, numero=1, descripcion="Cuarta", fecha=date(2026, 3, 1))
		with self.assertRaises(ValidationError):
			cuarta.full_clean()

		otra = Actividad.objects.create(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item,
			descripcion="Atención repetida", accion="Orientar",
		)
		caso_nuevo = Caso.objects.create(identificacion="P-200", nombre="Otra persona", delegacion=self.centro)
		Gestion.objects.create(caso=caso_nuevo, numero=1, descripcion="Usa la actividad", fecha=date(2026, 4, 1), actividad=otra)
		respuesta = self.client.post(reverse("servicios:gestion_nueva", args=[caso_nuevo.pk]), {
			"numero": "2",
			"fecha": "2026-04-02",
			"descripcion": "Intento duplicado",
			"actividad": str(otra.pk),
		})
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(caso_nuevo.gestiones.count(), 1)
		Gestion.objects.filter(caso=caso).update(activa=False)
		caso.refresh_from_db()
		self.assertEqual(caso.atenciones_contadas(), 0)
		detalle = self.client.get(reverse("servicios:caso_detalle", args=[caso.pk]))
		self.assertContains(detalle, "Identificación principal")
		self.assertNotIn("P-100", detalle.content.decode().split("<tbody>", 1)[-1])

	def test_scrum12_oculta_caso_de_otra_delegacion(self):
		ajeno = Caso.objects.create(identificacion="P-NORTE", nombre="Caso norte", delegacion=self.norte)
		self.assertEqual(self.client.get(reverse("servicios:caso_detalle", args=[ajeno.pk])).status_code, 404)

	def test_scrum15_codigo_inmutable_sin_reutilizacion_y_segun_ambito(self):
		self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad())
		propia = Actividad.objects.get()
		codigo_publicado = uuid.uuid4()
		self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad(descripcion="Segunda actividad", codigo_evidencia=str(codigo_publicado)))
		segunda = Actividad.objects.exclude(pk=propia.pk).get()
		self.assertNotEqual(propia.codigo_evidencia, segunda.codigo_evidencia)
		self.assertNotEqual(segunda.codigo_evidencia, codigo_publicado)

		original = propia.codigo_evidencia
		propia.codigo_evidencia = uuid.uuid4()
		with self.assertRaises(ValidationError):
			propia.save()
		propia.refresh_from_db()
		self.assertEqual(propia.codigo_evidencia, original)

		self.client.post(reverse("servicios:actividad_anular", args=[propia.pk]))
		propia.refresh_from_db()
		self.assertEqual(propia.estado, "anulada")
		self.assertEqual(propia.codigo_evidencia, original)
		duplicada = Actividad(
			codigo_evidencia=original, funcionario=self.funcionario, periodo=self.periodo, item=self.item,
			descripcion="Reutilizada", accion="No debe guardarse",
		)
		with self.assertRaises(IntegrityError):
			with transaction.atomic():
				duplicada.save()

		ajena = Actividad.objects.create(
			funcionario=self.ajeno, periodo=self.periodo, item=self.item,
			descripcion="Actividad del norte", accion="Fuera de ámbito",
		)
		encontrada = self.client.get(reverse("servicios:actividad_codigo"), {"codigo": str(original)})
		self.assertContains(encontrada, str(original))
		oculta = self.client.get(reverse("servicios:actividad_codigo"), {"codigo": str(ajena.codigo_evidencia)})
		self.assertContains(oculta, "No hay una actividad con ese código")
		self.assertNotContains(oculta, "Actividad del norte")
		self.assertEqual(self.client.get(reverse("servicios:actividad_detalle", args=[ajena.pk])).status_code, 404)

	def test_scrum16_publica_ordena_y_filtra_en_el_ambito(self):
		respuesta = self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(solicitante=""))
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(Compromiso.objects.count(), 0)

		respuesta = self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(delegacion=str(self.norte.pk), responsable=str(self.ajeno.pk)))
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(Compromiso.objects.count(), 0)

		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(fecha_comprometida="2026-12-01", solicitante="Tarde"))
		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(
			fecha_comprometida="2026-10-05", solicitante="Temprano", responsable=str(self.companero.pk),
		))
		fechas = list(self.client.get(reverse("servicios:agenda")).context["compromisos"].values_list("fecha_comprometida", flat=True))
		self.assertEqual(fechas, sorted(fechas))
		self.assertEqual(fechas[0], date(2026, 10, 5))

		filtrada = self.client.get(reverse("servicios:agenda"), {"responsable": str(self.companero.pk), "estado": "ingresado"})
		solicitantes = list(filtrada.context["compromisos"].values_list("solicitante", flat=True))
		self.assertEqual(solicitantes, ["Temprano"])
		self.client.force_login(self.otro)
		self.assertNotContains(self.client.get(reverse("servicios:agenda")), "Junta Los Aromos")
		self.assertNotContains(self.client.get(reverse("servicios:agenda")), "Temprano")

	def test_scrum17_limita_transiciones_guarda_historial_y_cierra_realizado(self):
		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso())
		compromiso = Compromiso.objects.get()
		self.assertEqual(compromiso.historial.count(), 1)
		datos = self._datos_compromiso(estado="realizado", observacion_cambio="Cierre indebido")
		self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), datos)
		compromiso.refresh_from_db()
		self.assertEqual(compromiso.estado, "ingresado")

		for estado in ("pendiente", "proceso", "realizado"):
			datos["estado"] = estado
			datos["observacion_cambio"] = f"Pasa a {estado}"
			self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), datos)
		compromiso.refresh_from_db()
		self.assertEqual(compromiso.estado, "realizado")
		self.assertEqual(compromiso.historial.count(), 4)
		self.assertEqual(list(compromiso.historial.values_list("estado_nuevo", flat=True)), ["ingresado", "pendiente", "proceso", "realizado"])
		detalle = self.client.get(reverse("servicios:compromiso_detalle", args=[compromiso.pk]))
		self.assertContains(detalle, "Cierre: Realizado")
		with self.assertRaises(ValidationError):
			compromiso.aplicar_estado("pendiente", self.user, "Reabrir")

	def test_scrum18_resume_pendientes_proximos_vencidos_y_conserva_historial(self):
		hoy = timezone.localdate()
		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(
			solicitante="Vencido demo", fecha_comprometida=(hoy - timedelta(days=3)).isoformat(),
		))
		vencido = Compromiso.objects.get(solicitante="Vencido demo")
		datos = self._datos_compromiso(solicitante="Vencido demo", fecha_comprometida=vencido.fecha_comprometida.isoformat(), estado="pendiente", observacion_cambio="Queda pendiente")
		self.client.post(reverse("servicios:compromiso_editar", args=[vencido.pk]), datos)
		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(
			solicitante="Pronto demo", fecha_comprometida=(hoy + timedelta(days=2)).isoformat(),
		))
		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(
			solicitante="Hecho demo", fecha_comprometida=(hoy + timedelta(days=30)).isoformat(),
		))
		hecho = Compromiso.objects.get(solicitante="Hecho demo")
		datos = self._datos_compromiso(solicitante="Hecho demo", fecha_comprometida=hecho.fecha_comprometida.isoformat(), observacion_cambio="avanza")
		for estado in ("pendiente", "proceso", "realizado"):
			datos["estado"] = estado
			self.client.post(reverse("servicios:compromiso_editar", args=[hecho.pk]), datos)
		Compromiso.objects.create(
			delegacion=self.norte, responsable=self.ajeno, origen="Externo", solicitante="Ajeno norte",
			territorio="Norte", descripcion="No debe verse", fecha_comprometida=hoy - timedelta(days=1), estado="pendiente",
		)
		self.client.force_login(self.delegado_user)
		resumen = self.client.get(reverse("servicios:resumen_agenda"))
		self.assertEqual(resumen.context["pendientes"], 2)
		self.assertEqual(resumen.context["realizados"], 1)
		self.assertContains(resumen, "Vencido demo")
		self.assertContains(resumen, "Pronto demo")
		self.assertContains(resumen, "ingresado → pendiente")
		self.assertNotContains(resumen, "Ajeno norte")
		self.assertEqual(vencido.historial.count(), 2)

	def test_scrum21_conserva_filtro_y_oculta_lo_no_autorizado(self):
		visible = Actividad.objects.create(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item,
			descripcion="Actividad visible del centro", accion="Registrar", estado="pendiente", fecha=date(2026, 5, 2),
		)
		Actividad.objects.create(
			funcionario=self.ajeno, periodo=self.periodo, item=self.item,
			descripcion="Actividad secreta del norte", accion="Ocultar", estado="pendiente", fecha=date(2026, 5, 2),
		)
		self.client.force_login(self.consulta_user)
		consulta = self.client.get(reverse("servicios:consulta"), {"estado": "pendiente", "item": str(self.item.pk), "desde": "2026-05-01"})
		self.assertContains(consulta, "Actividad visible del centro")
		self.assertNotContains(consulta, "Actividad secreta del norte")
		detalle_url = reverse("servicios:consulta_actividad", args=[visible.pk])
		self.assertContains(consulta, f"{detalle_url}?")
		self.assertContains(consulta, "estado=pendiente")
		self.assertContains(consulta, f"item={self.item.pk}")
		detalle = self.client.get(detalle_url, {"estado": "pendiente", "item": str(self.item.pk)})
		self.assertContains(detalle, "estado=pendiente")
		self.assertNotContains(detalle, reverse("servicios:actividad_editar", args=[visible.pk]))
		ajena = Actividad.objects.get(descripcion="Actividad secreta del norte")
		self.assertEqual(self.client.get(reverse("servicios:consulta_actividad", args=[ajena.pk])).status_code, 404)

	def test_cada_rol_abre_solo_sus_pantallas(self):
		inicio = self.client.get(reverse("institucional:inicio"))
		self.assertContains(inicio, "Cerrar sesión")
		self.assertContains(inicio, reverse("institucional:salir"))
		self.assertContains(inicio, reverse("servicios:actividades"))
		self.assertNotContains(inicio, reverse("servicios:resumen_agenda"))
		self.assertNotContains(inicio, reverse("servicios:consulta"))
		self.assertNotContains(inicio, reverse("servicios:evidencias"))
		self.assertEqual(self.client.get(reverse("servicios:resumen_agenda")).status_code, 403)
		self.assertEqual(self.client.get(reverse("servicios:consulta")).status_code, 403)
		self.assertEqual(self.client.get(reverse("institucional:panel")).status_code, 403)

		self.client.post(reverse("servicios:compromiso_nuevo"), self._datos_compromiso(solicitante="Para el delegado"))
		compromiso = Compromiso.objects.get(solicitante="Para el delegado")
		self.client.force_login(self.delegado_user)
		resumen = self.client.get(reverse("servicios:resumen_agenda"))
		self.assertEqual(resumen.status_code, 200)
		self.assertGreaterEqual(resumen.context["pendientes"], 1)
		self.assertContains(resumen, "Ana Centro")
		detalle = self.client.get(reverse("servicios:compromiso_detalle", args=[compromiso.pk]))
		self.assertEqual(detalle.status_code, 200)
		self.assertContains(detalle, "Historial de estados")
		self.assertNotContains(detalle, "Editar")
		self.assertEqual(self.client.get(reverse("servicios:consulta")).status_code, 200)
		self.assertEqual(self.client.get(reverse("servicios:aprobaciones")).status_code, 200)
		self.assertEqual(self.client.get(reverse("servicios:actividad_nueva")).status_code, 403)
		self.assertEqual(self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), self._datos_compromiso()).status_code, 403)
		menu = self.client.get(reverse("institucional:inicio"))
		self.assertContains(menu, "Cerrar sesión")
		self.assertContains(menu, reverse("institucional:salir"))
		self.assertContains(menu, reverse("servicios:aprobaciones"))
		self.assertContains(menu, reverse("servicios:evidencias"))
		self.assertContains(menu, reverse("servicios:consulta"))
		self.assertNotContains(menu, reverse("servicios:actividades"))
		salida = self.client.post(reverse("institucional:salir"))
		self.assertRedirects(salida, reverse("institucional:acceso"))
		self.assertRedirects(
			self.client.get(reverse("servicios:resumen_agenda")),
			f"{reverse('institucional:acceso')}?next={reverse('servicios:resumen_agenda')}",
		)

		self.client.force_login(self.consulta_user)
		self.assertEqual(self.client.get(reverse("servicios:consulta")).status_code, 200)
		for nombre in (
			"servicios:actividades",
			"servicios:actividad_nueva",
			"servicios:casos",
			"servicios:caso_nuevo",
			"servicios:compromiso_nuevo",
			"servicios:panel_municipal",
			"institucional:panel",
		):
			self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, nombre)
		self.assertEqual(self.client.get(reverse("servicios:agenda")).status_code, 200)
		self.assertEqual(self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad()).status_code, 403)
		self.assertEqual(self.client.get("/admin/").status_code, 404)
		menu = self.client.get(reverse("institucional:inicio"))
		self.assertContains(menu, "Cerrar sesión")
		self.assertContains(menu, reverse("institucional:salir"))
		self.assertContains(menu, reverse("servicios:consulta"))
		self.assertNotContains(menu, reverse("servicios:actividades"))


class TransaccionRegistrarActividadTest(TestCase):
	"""Reglas de la transacción: tareas, aprobación, tope 120 %, 7 por día y cierre semanal."""

	def setUp(self):
		fijar_hoy(self)
		modelo = get_user_model()
		self.centro = Delegacion.objects.create(nombre="Centro tx", slug="centro-tx", territorio="Centro", enfoque="Demo")
		self.norte = Delegacion.objects.create(nombre="Norte tx", slug="norte-tx", territorio="Norte", enfoque="Demo")
		self.cargo = Cargo.objects.create(nombre="Gestor tx")
		self.user = con_grupo(modelo.objects.create_user(username="fun-tx", password="x"), GRUPO_ADMINISTRATIVO)
		self.funcionario = Funcionario.objects.create(usuario=self.user, identificador="TX-1", nombre_completo="Ana Tx", delegacion=self.centro, cargo=self.cargo)
		self.supervisor = con_grupo(modelo.objects.create_user(username="sup-tx", password="x"), GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=self.supervisor, identificador="TX-S", nombre_completo="Jefa Tx", delegacion=self.centro, cargo=self.cargo)
		self.supervisor_norte = con_grupo(modelo.objects.create_user(username="sup-norte", password="x"), GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=self.supervisor_norte, identificador="TX-N", nombre_completo="Jefe Norte", delegacion=self.norte, cargo=self.cargo)
		self.item = ItemMedicion.objects.create(codigo="TX-001", nombre="Ítem tx")
		self.periodo = Periodo.objects.create(nombre="Período tx", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))

	def _actividad(self, fecha=HOY_PRUEBAS, tareas=("Gestión de sillas", "Gestión de colación")):
		from .models import TareaPreparatoria
		from .transacciones import registrar_actividad

		actividad = Actividad(periodo=self.periodo, item=self.item, fecha=fecha, descripcion="Celebración vecinal", accion="Coordinar", solicitante="Vecino solicitante", telefono="+56 9 1111 2222")
		return registrar_actividad(actividad, [TareaPreparatoria(tipo="otra", descripcion=texto) for texto in tareas], self.funcionario, self.user)

	def _datos(self, fecha="2026-06-17", **extra):
		datos = {
			"fecha": fecha, "periodo": str(self.periodo.pk), "item": str(self.item.pk),
			"descripcion": "Día del niño", "accion": "Coordinación", "solicitante": "Vecino solicitante", "contacto": "JJVV", "telefono": "+56 9 1234 5678",
			"tareas-TOTAL_FORMS": "4", "tareas-INITIAL_FORMS": "0", "tareas-MIN_NUM_FORMS": "0", "tareas-MAX_NUM_FORMS": "1000",
			"tareas-0-descripcion": "Gestión de regalos",
			"tareas-1-descripcion": "Reserva de la sede vecinal",
		}
		datos.update(extra)
		return datos

	def test_registra_actividad_y_tareas_en_una_sola_transaccion(self):
		self.client.force_login(self.user)
		respuesta = self.client.post(reverse("servicios:actividad_nueva"), self._datos(), follow=True)
		actividad = Actividad.objects.get()
		self.assertContains(respuesta, "2 tareas preparatorias")
		self.assertEqual(actividad.tareas.count(), 2)
		self.assertEqual(
			set(actividad.tareas.values_list("tipo", "descripcion")),
			{("otra", "Gestión de regalos"), ("otra", "Reserva de la sede vecinal")},
		)
		self.assertEqual(actividad.estado, "pendiente")
		from .models import Auditoria
		self.assertTrue(Auditoria.objects.filter(accion="registrar_actividad", identificador=str(actividad.codigo_evidencia)).exists())

	def test_sin_tareas_no_se_guarda_nada(self):
		self.client.force_login(self.user)
		datos = self._datos(**{"tareas-0-descripcion": "", "tareas-1-descripcion": ""})
		respuesta = self.client.post(reverse("servicios:actividad_nueva"), datos)
		self.assertContains(respuesta, "al menos una tarea")
		self.assertEqual(Actividad.objects.count(), 0)

	def test_la_tarea_es_solo_texto_sin_desplegable(self):
		self.client.force_login(self.user)
		pagina = self.client.get(reverse("servicios:actividad_nueva"))
		self.assertContains(pagina, "Gestión de sillas")
		self.assertNotContains(pagina, "tareas-0-tipo")
		self.assertNotContains(pagina, "Otra gestión")
		self.assertNotContains(pagina, "Solicitar sillas y mesas")
		self.assertNotContains(pagina, "Solicitar colación")

		sin_texto = self.client.post(reverse("servicios:actividad_nueva"), self._datos(**{
			"tareas-0-descripcion": "   ",
			"tareas-1-descripcion": "",
		}))
		self.assertContains(sin_texto, "Escribe la tarea")
		self.assertEqual(Actividad.objects.count(), 0)

	def test_el_catalogo_antiguo_queda_en_el_texto(self):
		import importlib

		from django.apps import apps

		from .models import TareaPreparatoria

		migracion = importlib.import_module("servicios.migrations.0007_tarea_texto_libre")
		pasar_catalogo_a_texto = migracion.pasar_catalogo_a_texto
		texto_libre_desde_catalogo = migracion.texto_libre_desde_catalogo

		self.assertEqual(texto_libre_desde_catalogo("sillas", "20 sillas"), "Solicitar sillas y mesas: 20 sillas")
		self.assertEqual(texto_libre_desde_catalogo("sillas", ""), "Solicitar sillas y mesas")
		self.assertEqual(texto_libre_desde_catalogo("sillas", "Solicitar sillas y mesas"), "Solicitar sillas y mesas")
		self.assertEqual(texto_libre_desde_catalogo("difusion", "Afiches"), "Difusión e invitaciones: Afiches")
		self.assertEqual(texto_libre_desde_catalogo("otra", "Gestión de sillas"), "Gestión de sillas")
		self.assertEqual(texto_libre_desde_catalogo("otra", ""), "Otra gestión")

		actividad = self._actividad(tareas=("Gestión de sillas",))
		TareaPreparatoria.objects.create(actividad=actividad, tipo="colacion", descripcion="Colación para 40 personas")
		TareaPreparatoria.objects.create(actividad=actividad, tipo="local", descripcion="")
		TareaPreparatoria.objects.create(actividad=actividad, tipo="animacion", descripcion="Grupo folclórico")
		pasar_catalogo_a_texto(apps, None)
		self.assertEqual(Actividad.objects.count(), 1)
		self.assertEqual(
			set(actividad.tareas.values_list("tipo", "descripcion")),
			{
				("otra", "Gestión de sillas"),
				("otra", "Solicitar colación: Colación para 40 personas"),
				("otra", "Reservar local o espacio"),
				("otra", "Contratar animadores o artistas: Grupo folclórico"),
			},
		)

	def test_solicitante_se_comparte_con_el_tubo_y_el_caso(self):
		from .models import Caso, Compromiso, Gestion

		self.client.force_login(self.user)
		compromiso = Compromiso.objects.create(
			delegacion=self.centro, responsable=self.funcionario, origen="Vecinal", solicitante="Junta Los Aromos",
			territorio="Centro", descripcion="Luminaria", fecha_comprometida=HOY_PRUEBAS,
		)
		respuesta = self.client.post(
			reverse("servicios:actividad_nueva"),
			self._datos(compromiso=str(compromiso.pk), solicitante=""),
			follow=True,
		)
		actividad = Actividad.objects.get()
		self.assertEqual(actividad.solicitante, "Junta Los Aromos")
		self.assertContains(respuesta, "Junta Los Aromos")
		self.assertContains(self.client.get(reverse("servicios:actividades")), "Junta Los Aromos")
		detalle_tubo = self.client.get(reverse("servicios:compromiso_detalle", args=[compromiso.pk]))
		self.assertContains(detalle_tubo, "Solicitante")
		self.assertContains(detalle_tubo, "Junta Los Aromos")

		distinto = self.client.post(
			reverse("servicios:actividad_nueva"),
			self._datos(descripcion="Otra actividad", compromiso=str(compromiso.pk), solicitante="Otra persona"),
		)
		self.assertContains(distinto, "ingreso al tubo")
		self.assertEqual(Actividad.objects.count(), 1)

		caso = Caso.objects.create(identificacion="C-SOL", nombre="Persona atendida", delegacion=self.centro)
		Gestion.objects.create(caso=caso, numero=1, descripcion="Primera gestión", actividad=actividad)
		caso.refresh_from_db()
		self.assertEqual(caso.solicitante, "Junta Los Aromos")
		self.assertContains(self.client.get(reverse("servicios:caso_detalle", args=[caso.pk])), "Junta Los Aromos")
		self.assertContains(self.client.get(reverse("servicios:casos")), "Junta Los Aromos")

		compromiso.solicitante = "Junta Nueva"
		compromiso.save()
		actividad.refresh_from_db()
		caso.refresh_from_db()
		self.assertEqual(actividad.solicitante, "Junta Nueva")
		self.assertEqual(caso.solicitante, "Junta Nueva")

	def test_error_en_una_tarea_revierte_toda_la_transaccion(self):
		from .models import TareaPreparatoria
		from .transacciones import registrar_actividad

		actividad = Actividad(periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS, descripcion="X", accion="Y", solicitante="Vecino solicitante")
		with self.assertRaises(ValidationError):
			registrar_actividad(
				actividad,
				[TareaPreparatoria(tipo="otra", descripcion="Gestión de sillas"), TareaPreparatoria(tipo="no-existe", descripcion="Texto")],
				self.funcionario,
				self.user,
			)
		self.assertEqual(Actividad.objects.count(), 0)
		self.assertEqual(TareaPreparatoria.objects.count(), 0)

	def test_tareas_no_suman_hasta_completar_y_aprobar(self):
		from .transacciones import marcar_tarea, revisar_actividad

		meta = Meta.objects.create(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=1, ponderador=100)
		actividad = self._actividad()
		tareas = list(actividad.tareas.all())
		marcar_tarea(tareas[0], True, self.user)
		self.assertEqual(meta.cumplimiento, 0)
		with self.assertRaises(ValidationError):
			revisar_actividad(actividad, "aprobar", self.supervisor)
		marcar_tarea(tareas[1], True, self.user)
		self.assertEqual(meta.cumplimiento, 0)
		revisar_actividad(actividad, "aprobar", self.supervisor)
		actividad.refresh_from_db()
		self.assertTrue(actividad.puntua)
		self.assertEqual(meta.cumplimiento, 100)
		with self.assertRaises(ValidationError):
			marcar_tarea(tareas[1], False, self.user)

	def test_rechazo_exige_motivo_y_no_suma(self):
		from .transacciones import revisar_actividad

		meta = Meta.objects.create(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=1, ponderador=100)
		actividad = self._actividad(tareas=("Gestión de sillas",))
		with self.assertRaises(ValidationError):
			revisar_actividad(actividad, "rechazar", self.supervisor, "")
		revisar_actividad(actividad, "rechazar", self.supervisor, "Sin respaldo")
		self.assertEqual(meta.cumplimiento, 0)

	def test_tope_de_120_por_item(self):
		meta = Meta.objects.create(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=2, ponderador=100)
		for dia in (15, 16, 17):
			actividad = self._actividad(fecha=date(2026, 6, dia), tareas=("Gestión de sillas",))
			actividad.tareas.update(realizada=True)
			Actividad.objects.filter(pk=actividad.pk).update(estado="validada")
		self.assertEqual(meta.avance_aprobado, 3)
		self.assertEqual(meta.cumplimiento, 120)

	def test_maximo_siete_actividades_por_dia(self):
		for _ in range(7):
			self._actividad(tareas=("Gestión de sillas",))
		with self.assertRaisesMessage(ValidationError, "máximo diario"):
			self._actividad(tareas=("Gestión de sillas",))
		Actividad.objects.filter(pk=Actividad.objects.first().pk).update(estado="anulada")
		self._actividad(tareas=("Gestión de sillas",))
		self.assertEqual(Actividad.objects.exclude(estado="anulada").filter(fecha=HOY_PRUEBAS).count(), 7)

	def test_solo_dias_habiles_de_la_semana_en_curso(self):
		for fecha, mensaje in (
			(date(2026, 6, 18), "fecha futura"),
			(date(2026, 6, 12), "ya cerró"),
			(date(2026, 6, 13), "lunes a viernes"),
		):
			with self.assertRaisesMessage(ValidationError, mensaje):
				self._actividad(fecha=fecha)
		self._actividad(fecha=date(2026, 6, 15))
		self.assertEqual(Actividad.objects.count(), 1)

	def test_fin_de_semana_no_se_ingresa_ni_lo_de_la_semana_que_cerro(self):
		fijar_hoy(self, date(2026, 6, 20))
		with self.assertRaisesMessage(ValidationError, "ya cerró"):
			self._actividad(fecha=date(2026, 6, 19))

	def test_semana_cerrada_bloquea_tareas_edicion_y_aprobacion(self):
		from .transacciones import marcar_tarea, revisar_actividad

		actividad = self._actividad(tareas=("Gestión de sillas",))
		fijar_hoy(self, date(2026, 6, 22))
		with self.assertRaisesMessage(ValidationError, "bloqueada"):
			marcar_tarea(actividad.tareas.first(), True, self.user)
		with self.assertRaisesMessage(ValidationError, "bloqueada"):
			revisar_actividad(actividad, "aprobar", self.supervisor)
		self.client.force_login(self.user)
		self.client.post(reverse("servicios:actividad_anular", args=[actividad.pk]))
		actividad.refresh_from_db()
		self.assertEqual(actividad.estado, "pendiente")
		self.assertRedirects(self.client.get(reverse("servicios:actividad_editar", args=[actividad.pk])), reverse("servicios:actividad_detalle", args=[actividad.pk]))

	def test_supervisor_aprueba_solo_su_delegacion_y_administrativo_no_aprueba(self):
		actividad = self._actividad(tareas=("Gestión de sillas",))
		actividad.tareas.update(realizada=True)
		self.client.force_login(self.user)
		self.assertEqual(self.client.post(reverse("servicios:actividad_revisar", args=[actividad.pk]), {"decision": "aprobar"}).status_code, 403)
		self.client.force_login(self.supervisor_norte)
		self.assertEqual(self.client.post(reverse("servicios:actividad_revisar", args=[actividad.pk]), {"decision": "aprobar"}).status_code, 404)
		self.client.force_login(self.supervisor)
		self.assertContains(self.client.get(reverse("servicios:aprobaciones")), "Celebración vecinal")
		self.client.post(reverse("servicios:actividad_revisar", args=[actividad.pk]), {"decision": "aprobar"})
		actividad.refresh_from_db()
		self.assertEqual(actividad.estado, "validada")
		self.assertEqual(actividad.revisada_por, self.supervisor)


def imagen_prueba(nombre="captura.png", formato="PNG"):
	from io import BytesIO

	from PIL import Image
	from django.core.files.uploadedfile import SimpleUploadedFile

	buffer = BytesIO()
	Image.new("RGB", (12, 8), (30, 90, 160)).save(buffer, format=formato)
	tipos = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
	return SimpleUploadedFile(nombre, buffer.getvalue(), content_type=tipos[formato])


class EvidenciasTest(TestCase):
	"""El funcionario adjunta la captura de una tarea hecha y el delegado la aprueba o la rechaza."""

	def setUp(self):
		fijar_hoy(self)
		directorio = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, directorio, True)
		ajuste = override_settings(MEDIA_ROOT=directorio, MEDIA_X_ACCEL=False)
		ajuste.enable()
		self.addCleanup(ajuste.disable)
		modelo = get_user_model()
		self.centro = Delegacion.objects.create(nombre="Centro ev", slug="centro-ev", territorio="Centro", enfoque="Demo")
		self.norte = Delegacion.objects.create(nombre="Norte ev", slug="norte-ev", territorio="Norte", enfoque="Demo")
		self.cargo = Cargo.objects.create(nombre="Gestor ev")
		self.user = con_grupo(modelo.objects.create_user(username="fun-ev", password="x"), GRUPO_ADMINISTRATIVO)
		self.funcionario = Funcionario.objects.create(usuario=self.user, identificador="EV-1", nombre_completo="Ana Evidencia", delegacion=self.centro, cargo=self.cargo)
		self.companero_user = con_grupo(modelo.objects.create_user(username="fun-ev-2", password="x"), GRUPO_ADMINISTRATIVO)
		Funcionario.objects.create(usuario=self.companero_user, identificador="EV-2", nombre_completo="Bruno Evidencia", delegacion=self.centro, cargo=self.cargo)
		self.supervisor = con_grupo(modelo.objects.create_user(username="sup-ev", password="x"), GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=self.supervisor, identificador="EV-S", nombre_completo="Delegada Centro", delegacion=self.centro, cargo=self.cargo)
		self.supervisor_norte = con_grupo(modelo.objects.create_user(username="sup-ev-n", password="x"), GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=self.supervisor_norte, identificador="EV-N", nombre_completo="Delegado Norte", delegacion=self.norte, cargo=self.cargo)
		self.admin = con_grupo(modelo.objects.create_user(username="admin-ev", password="x"), GRUPO_ADMINISTRADOR)
		self.item = ItemMedicion.objects.create(codigo="EV-001", nombre="Ítem evidencia")
		self.periodo = Periodo.objects.create(nombre="Período evidencia", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))

	def _actividad(self, tareas=("Gestión de sillas",)):
		from .models import TareaPreparatoria
		from .transacciones import registrar_actividad

		actividad = Actividad(
			periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS, descripcion="Celebración vecinal",
			accion="Coordinar", solicitante="Junta Los Aromos", telefono="+56 9 1111 2222",
		)
		return registrar_actividad(actividad, [TareaPreparatoria(tipo="otra", descripcion=texto) for texto in tareas], self.funcionario, self.user)

	def _tarea_lista(self, actividad, texto="Gestión de sillas"):
		tarea = actividad.tareas.get(descripcion=texto)
		tarea.realizada = True
		tarea.save(update_fields=["realizada"])
		return tarea

	def _cargar(self, actividad, tarea, archivo=None, usuario=None):
		cliente = self.client
		if usuario is not None:
			cliente = self.client_class()
			cliente.force_login(usuario)
		else:
			cliente.force_login(self.user)
		return cliente.post(
			reverse("servicios:actividad_detalle", args=[actividad.pk]),
			{"tarea": str(tarea.pk), "archivo": archivo or imagen_prueba()},
		)

	def test_funcionario_adjunta_la_captura_de_la_tarea_hecha(self):
		actividad = self._actividad()
		tarea = self._tarea_lista(actividad)
		self.client.force_login(self.user)
		detalle = self.client.get(reverse("servicios:actividad_detalle", args=[actividad.pk]))
		self.assertContains(detalle, "Adjuntar captura")
		self.assertContains(detalle, "Junta Los Aromos")
		self.assertContains(detalle, "Gestión de sillas")
		for nombre, formato in (("captura.png", "PNG"), ("captura.jpg", "JPEG"), ("captura.webp", "WEBP")):
			if formato != "PNG":
				actividad = self._actividad(tareas=(f"Tarea {formato}",))
				tarea = self._tarea_lista(actividad, f"Tarea {formato}")
			respuesta = self._cargar(actividad, tarea, imagen_prueba(nombre, formato))
			self.assertRedirects(respuesta, reverse("servicios:actividad_detalle", args=[actividad.pk]))
			evidencia = actividad.evidencias.get()
			self.assertEqual(evidencia.estado, "pendiente")
			self.assertEqual(evidencia.texto_tarea, tarea.descripcion)
			self.assertEqual(evidencia.actividad_id, actividad.pk)
			self.assertEqual(evidencia.autor, self.user)
			pagina = self.client.get(reverse("servicios:actividad_detalle", args=[actividad.pk]))
			self.assertContains(pagina, tarea.descripcion)
			self.assertContains(pagina, "Pendiente")
			self.assertContains(pagina, evidencia.archivo.url)

	def test_rechaza_pdf_imagen_falsa_y_mas_de_5_mb(self):
		from django.core.files.uploadedfile import SimpleUploadedFile

		from .models import validar_imagen_evidencia

		actividad = self._actividad()
		tarea = self._tarea_lista(actividad)
		self.client.force_login(self.user)
		url = reverse("servicios:actividad_detalle", args=[actividad.pk])
		for archivo in (
			SimpleUploadedFile("acta.pdf", b"%PDF-1.4"),
			SimpleUploadedFile("falso.png", b"esto no es una imagen"),
			imagen_prueba("captura.png", "GIF"),
		):
			respuesta = self.client.post(url, {"tarea": str(tarea.pk), "archivo": archivo})
			self.assertEqual(respuesta.status_code, 200, archivo.name)
			self.assertEqual(actividad.evidencias.count(), 0)
		grande = SimpleUploadedFile("grande.png", b"x")
		grande.size = 5 * 1024 * 1024 + 1
		with self.assertRaisesMessage(ValidationError, "5 MB"):
			validar_imagen_evidencia(grande)

	def test_solo_la_tarea_realizada_y_una_pendiente(self):
		actividad = self._actividad(tareas=("Gestión de sillas", "Gestión de colación"))
		pendiente = actividad.tareas.get(descripcion="Gestión de colación")
		hecha = self._tarea_lista(actividad)
		self.client.force_login(self.user)
		respuesta = self.client.post(
			reverse("servicios:actividad_detalle", args=[actividad.pk]),
			{"tarea": str(pendiente.pk), "archivo": imagen_prueba()},
		)
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(actividad.evidencias.count(), 0)
		self._cargar(actividad, hecha)
		otra = self._cargar(actividad, hecha, imagen_prueba("otra.png"))
		self.assertEqual(otra.status_code, 200)
		self.assertContains(otra, "pendiente de revisión")
		self.assertEqual(actividad.evidencias.count(), 1)

	def test_no_carga_la_actividad_de_otro_ni_una_anulada(self):
		actividad = self._actividad()
		tarea = self._tarea_lista(actividad)
		companero = self._cargar(actividad, tarea, usuario=self.companero_user)
		self.assertEqual(companero.status_code, 403)
		self.client.force_login(self.companero_user)
		vista = self.client.get(reverse("servicios:actividad_detalle", args=[actividad.pk]))
		self.assertEqual(vista.status_code, 200)
		self.assertNotContains(vista, "Enviar captura")
		self.client.force_login(self.supervisor)
		self.assertEqual(self.client.post(reverse("servicios:actividad_detalle", args=[actividad.pk]), {"tarea": tarea.pk}).status_code, 403)
		actividad.estado = "anulada"
		actividad.save(update_fields=["estado"])
		self.assertEqual(self._cargar(actividad, tarea).status_code, 403)
		self.assertEqual(actividad.evidencias.count(), 0)

	def test_delegado_aprueba_y_el_rechazo_muestra_el_motivo(self):
		from .models import Evidencia, Validacion

		actividad = self._actividad()
		tarea = self._tarea_lista(actividad)
		self._cargar(actividad, tarea)
		evidencia = Evidencia.objects.get()
		tarea.descripcion = "Texto cambiado después"
		tarea.save(update_fields=["descripcion"])
		evidencia.refresh_from_db()
		self.assertEqual(evidencia.texto_tarea, "Gestión de sillas")

		self.client.force_login(self.user)
		self.assertEqual(self.client.get(reverse("servicios:evidencias")).status_code, 403)
		self.assertEqual(self.client.post(reverse("servicios:evidencia_revisar", args=[evidencia.pk]), {"decision": "aprobar"}).status_code, 403)

		self.client.force_login(self.supervisor_norte)
		self.assertEqual(self.client.get(reverse("servicios:evidencias")).status_code, 200)
		self.assertNotContains(self.client.get(reverse("servicios:evidencias")), "Gestión de sillas")
		self.assertEqual(self.client.post(reverse("servicios:evidencia_revisar", args=[evidencia.pk]), {"decision": "aprobar"}).status_code, 404)

		self.client.force_login(self.supervisor)
		listado = self.client.get(reverse("servicios:evidencias"))
		self.assertContains(listado, "Gestión de sillas")
		self.assertContains(listado, "Celebración vecinal")
		self.assertContains(listado, "Junta Los Aromos")
		self.assertContains(listado, evidencia.archivo.url)
		self.assertContains(self.client.get(reverse("institucional:mi_panel")), "Revisar evidencias")
		sin_motivo = self.client.post(reverse("servicios:evidencia_revisar", args=[evidencia.pk]), {"decision": "rechazar", "motivo": "   "}, follow=True)
		self.assertContains(sin_motivo, "motivo breve")
		evidencia.refresh_from_db()
		self.assertEqual(evidencia.estado, "pendiente")

		self.client.post(reverse("servicios:evidencia_revisar", args=[evidencia.pk]), {"decision": "rechazar", "motivo": "La captura no muestra las sillas."})
		evidencia.refresh_from_db()
		self.assertEqual(evidencia.estado, "rechazada")
		self.assertEqual(evidencia.observacion, "La captura no muestra las sillas.")
		self.assertEqual(Validacion.objects.get().decision, "rechazada")
		self.assertEqual(Validacion.objects.get().verificador, self.supervisor)

		self.client.force_login(self.user)
		detalle = self.client.get(reverse("servicios:actividad_detalle", args=[actividad.pk]))
		self.assertContains(detalle, "La captura no muestra las sillas.")
		self.assertContains(detalle, "Rechazada")
		self.assertContains(detalle, "Junta Los Aromos")
		self._cargar(actividad, tarea, imagen_prueba("nueva.png"))
		self.assertEqual(actividad.evidencias.filter(estado="pendiente").count(), 1)

		nueva = actividad.evidencias.get(estado="pendiente")
		self.client.force_login(self.supervisor)
		self.client.post(reverse("servicios:evidencia_revisar", args=[nueva.pk]), {"decision": "aprobar"})
		nueva.refresh_from_db()
		self.assertEqual(nueva.estado, "aprobada")
		self.assertEqual(Validacion.objects.filter(decision="aprobada").count(), 1)
		consulta = self.client.get(reverse("servicios:consulta_actividad", args=[actividad.pk]))
		self.assertContains(consulta, "Gestión de sillas")
		self.assertContains(consulta, nueva.archivo.url)
		self.assertContains(consulta, "La captura no muestra las sillas.")
		actividad.refresh_from_db()
		self.assertEqual(actividad.estado, "pendiente")
		self.assertEqual(actividad.solicitante, "Junta Los Aromos")

	def test_la_captura_se_ve_desde_media_y_el_administrador_tambien_actua(self):
		from .models import Evidencia

		actividad = self._actividad()
		tarea = self._tarea_lista(actividad)
		self.client.force_login(self.admin)
		self.assertEqual(self._cargar(actividad, tarea, usuario=self.admin).status_code, 302)
		evidencia = Evidencia.objects.get()
		self.assertEqual(self.client_class().get(evidencia.archivo.url).status_code, 302)
		self.client.force_login(self.user)
		with self.settings(MEDIA_X_ACCEL=False):
			respuesta = self.client.get(evidencia.archivo.url)
		self.assertEqual(respuesta.status_code, 200)
		self.assertIn("inline", respuesta["Content-Disposition"])
		self.assertEqual(respuesta["Content-Type"], "image/png")
		self.assertTrue(b"".join(respuesta.streaming_content).startswith(b"\x89PNG"))
		self.client.force_login(self.admin)
		self.client.post(reverse("servicios:evidencia_revisar", args=[evidencia.pk]), {"decision": "aprobar"})
		evidencia.refresh_from_db()
		self.assertEqual(evidencia.estado, "aprobada")
