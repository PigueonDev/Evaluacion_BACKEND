import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from institucional.models import Cargo, Delegacion, Funcionario

from .models import Actividad, Caso, Compromiso, Gestion, ItemMedicion, Meta, Periodo, Servicio


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
			estado="validada",
		)
		self.assertEqual(meta.avance_aprobado, 1)
		self.assertEqual(meta.cumplimiento, 50)


class PanelesPrivadosTest(TestCase):
	PANELES = (
		"servicios:dashboard",
		"servicios:actividades",
		"servicios:casos",
		"servicios:agenda",
		"servicios:consulta",
		"institucional:panel",
	)

	def setUp(self):
		modelo_usuario = get_user_model()
		self.staff = modelo_usuario.objects.create_user(username="staff-demo", password="demo", is_staff=True)
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
		for nombre in self.PANELES:
			self.assertNotContains(respuesta, f'href="{reverse(nombre)}"')
		self.client.force_login(self.staff)
		respuesta = self.client.get(reverse("institucional:inicio"))
		for nombre in self.PANELES:
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
		self.staff = get_user_model().objects.create_user(username="staff-demo", password="demo", is_staff=True)
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
		modelo = get_user_model()
		self.user = modelo.objects.create_user(username="func-centro", password="clave-demo-123", is_staff=True)
		self.otro = modelo.objects.create_user(username="func-norte", password="clave-demo-123", is_staff=True)
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
		self.delegado_user = modelo.objects.create_user(username="delegado-centro", password="clave-demo-123", is_staff=True)
		self.consulta_user = modelo.objects.create_user(username="consulta-centro", password="clave-demo-123", is_staff=True)
		Funcionario.objects.create(
			usuario=self.delegado_user, identificador="F-D", nombre_completo="Jefa Centro", delegacion=self.centro, cargo=self.cargo, rol="delegado",
		)
		Funcionario.objects.create(
			usuario=self.consulta_user, identificador="F-Q", nombre_completo="Consulta Centro", delegacion=self.centro, cargo=self.cargo, rol="consulta",
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
			"contacto": "Junta de vecinos",
			"telefono": "+56 9 1111 2222",
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
		self.assertContains(inicio, reverse("servicios:actividades"))
		self.assertNotContains(inicio, reverse("servicios:resumen_agenda"))
		self.assertNotContains(inicio, reverse("servicios:consulta"))
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
		self.assertNotContains(resumen, "Consulta operativa")
		detalle = self.client.get(reverse("servicios:compromiso_detalle", args=[compromiso.pk]))
		self.assertEqual(detalle.status_code, 200)
		self.assertContains(detalle, "Historial de estados")
		self.assertNotContains(detalle, "Editar")
		self.assertEqual(self.client.get(reverse("servicios:consulta")).status_code, 403)
		self.assertEqual(self.client.get(reverse("servicios:actividad_nueva")).status_code, 403)
		self.assertEqual(self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), self._datos_compromiso()).status_code, 403)
		menu = self.client.get(reverse("institucional:inicio"))
		self.assertContains(menu, reverse("servicios:resumen_agenda"))
		self.assertNotContains(menu, reverse("servicios:consulta"))
		self.assertNotContains(menu, reverse("servicios:actividades"))

		self.client.force_login(self.consulta_user)
		self.assertEqual(self.client.get(reverse("servicios:consulta")).status_code, 200)
		for nombre in (
			"servicios:actividades",
			"servicios:actividad_nueva",
			"servicios:casos",
			"servicios:caso_nuevo",
			"servicios:agenda",
			"servicios:compromiso_nuevo",
			"servicios:resumen_agenda",
			"servicios:dashboard",
			"institucional:panel",
		):
			self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, nombre)
		self.assertEqual(self.client.post(reverse("servicios:actividad_nueva"), self._datos_actividad()).status_code, 403)
		self.assertEqual(self.client.get("/admin/").status_code, 403)
		menu = self.client.get(reverse("institucional:inicio"))
		self.assertContains(menu, reverse("servicios:consulta"))
		self.assertNotContains(menu, reverse("servicios:actividades"))
		self.assertNotContains(menu, reverse("servicios:resumen_agenda"))
