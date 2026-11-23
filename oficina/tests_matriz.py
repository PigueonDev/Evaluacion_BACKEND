from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from institucional.models import Cargo, Delegacion, Funcionario, UnidadMunicipal
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, asignar_grupo
from servicios.management.commands.cargar_matriz import cargar_matriz
from servicios.models import Meta, Periodo

from .models import Ausencia, Carta, Reconocimiento
from .transacciones import registrar_ausencia

HOY = date(2026, 11, 16)


def cuenta(username, grupo):
	usuario = get_user_model().objects.create_user(username=username, password="x")
	asignar_grupo(usuario, grupo)
	return usuario


class MatrizOficinaBase(TestCase):
	def setUp(self):
		patcher = mock.patch("django.utils.timezone.localdate", return_value=HOY)
		patcher.start()
		self.addCleanup(patcher.stop)
		cargar_matriz(HOY)
		self.periodo = Periodo.objects.get()
		self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="-", enfoque="-")
		self.norte = Delegacion.objects.create(nombre="Norte", slug="norte", territorio="-", enfoque="-")
		self.admin = cuenta("adm", GRUPO_ADMINISTRADOR)
		self.supervisor = cuenta("sup", GRUPO_SUPERVISOR)
		self.administrativo = cuenta("fun", GRUPO_ADMINISTRATIVO)
		self.delegado = Funcionario.objects.create(usuario=self.supervisor, identificador="S-1", nombre_completo="Delegada Centro", delegacion=self.centro, cargo=Cargo.objects.get(nombre="Delegado"))
		self.social = Funcionario.objects.create(usuario=self.administrativo, identificador="F-1", nombre_completo="Gestora Social", delegacion=self.centro, cargo=Cargo.objects.get(nombre="Gestor Social"))
		self.del_norte = Funcionario.objects.create(identificador="F-2", nombre_completo="Apoyo Norte", delegacion=self.norte, cargo=Cargo.objects.get(nombre="Apoyo Administrativo"))


class TuboDeCartasTest(MatrizOficinaBase):
	def datos(self, **extra):
		datos = {
			"fecha_ingreso": "2026-11-10", "numero_oficina_partes": "4512", "destinatario": "alcaldesa", "tipo": "invitacion",
			"remitente": "Club deportivo", "asunto": "Campeonato de baby fútbol", "fecha_actividad": "2026-12-05",
			"encargado_seguimiento": UnidadMunicipal.objects.get(nombre="Patrocinios").pk, "pronunciamiento": "alcaldesa",
			"estado": "ingresada", "resolucion": "en_proceso",
		}
		datos.update(extra)
		return datos

	def test_registra_campos_de_la_matriz_y_filtra_por_estado_matriz(self):
		self.client.force_login(self.supervisor)
		self.client.post(reverse("oficina:carta_crear"), self.datos())
		carta = Carta.objects.get()
		self.assertEqual((carta.numero_oficina_partes, carta.destinatario, carta.pronunciamiento), ("4512", "alcaldesa", "alcaldesa"))
		self.assertEqual(carta.encargado_seguimiento.nombre, "Patrocinios")
		self.assertContains(self.client.get(reverse("oficina:cartas"), {"q": "4512"}), carta.folio)
		self.assertContains(self.client.get(reverse("oficina:cartas"), {"resolucion": "en_proceso"}), carta.folio)
		self.assertNotContains(self.client.get(reverse("oficina:cartas"), {"resolucion": "aprobada"}), carta.folio)
		detalle = self.client.get(reverse("oficina:carta_detalle", args=[carta.pk]))
		self.assertContains(detalle, "Patrocinios")
		self.assertContains(detalle, "N° Oficina de Partes 4512")

	def test_derivar_a_una_unidad_y_cerrar_pasa_a_finalizada(self):
		self.client.force_login(self.supervisor)
		self.client.post(reverse("oficina:carta_crear"), self.datos())
		carta = Carta.objects.get()
		unidad = UnidadMunicipal.objects.get(nombre="Dirección de Obras Municipales")
		self.client.post(reverse("oficina:carta_editar", args=[carta.pk]), self.datos(estado="derivada", derivada_a_unidad=unidad.pk))
		carta.refresh_from_db()
		self.assertEqual((carta.estado, carta.derivada_a_unidad), ("derivada", unidad))
		self.client.post(reverse("oficina:carta_editar", args=[carta.pk]), self.datos(
			estado="respondida", derivada_a_unidad=unidad.pk, respuesta="Se patrocina.", fecha_respuesta="2026-11-12",
		))
		carta.refresh_from_db()
		self.assertEqual((carta.estado, carta.resolucion), ("respondida", "finalizada"))


class FelicitacionesYReclamosTest(MatrizOficinaBase):
	def datos(self, **extra):
		datos = {
			"tipo": "felicitacion", "funcionario": self.social.pk, "periodo": self.periodo.pk, "fecha": "2026-11-12",
			"usuario_nombre": "Vecina", "situacion": "Agradece la visita.", "medio": "correo",
		}
		datos.update(extra)
		return datos

	def test_administrativo_solo_ve_lo_suyo_y_no_registra(self):
		Reconocimiento.objects.create(tipo="reclamo", funcionario=self.del_norte, periodo=self.periodo, fecha=HOY, usuario_nombre="X", situacion="Ajeno", registrado_por=self.admin)
		propio = Reconocimiento.objects.create(tipo="felicitacion", funcionario=self.social, periodo=self.periodo, fecha=HOY, usuario_nombre="Y", situacion="Propio", registrado_por=self.supervisor)
		self.client.force_login(self.administrativo)
		listado = self.client.get(reverse("oficina:reconocimientos"))
		self.assertEqual(list(listado.context["pagina"]), [propio])
		self.assertEqual(self.client.get(reverse("oficina:reconocimiento_crear")).status_code, 403)
		self.assertEqual(self.client.post(reverse("oficina:reconocimiento_anular", args=[propio.pk])).status_code, 403)

	def test_supervisor_registra_en_su_delegacion_y_anula(self):
		self.client.force_login(self.supervisor)
		formulario = self.client.get(reverse("oficina:reconocimiento_crear")).context["form"]
		self.assertEqual(list(formulario.fields["funcionario"].queryset), [self.social])
		ajeno = self.client.post(reverse("oficina:reconocimiento_crear"), self.datos(funcionario=self.del_norte.pk))
		self.assertEqual(ajeno.status_code, 200)
		futuro = self.client.post(reverse("oficina:reconocimiento_crear"), self.datos(fecha="2026-11-30"))
		self.assertContains(futuro, "no puede ser futura")
		self.client.post(reverse("oficina:reconocimiento_crear"), self.datos())
		registro = Reconocimiento.objects.get()
		self.assertEqual((registro.registrado_por, registro.estado), (self.supervisor, "vigente"))
		self.client.post(reverse("oficina:reconocimiento_anular", args=[registro.pk]))
		registro.refresh_from_db()
		self.assertEqual(registro.estado, "anulado")
		otro_supervisor = cuenta("sup-norte", GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=otro_supervisor, identificador="S-2", nombre_completo="Delegado Norte", delegacion=self.norte, cargo=self.delegado.cargo)
		self.client.force_login(otro_supervisor)
		self.assertEqual(self.client.post(reverse("oficina:reconocimiento_anular", args=[registro.pk])).status_code, 404)


class AusenciaMetasMatrizTest(MatrizOficinaBase):
	def test_ausencia_solo_reduce_metas_de_conteo(self):
		registrar_ausencia(
			Ausencia(funcionario=self.social, periodo=self.periodo, fecha_inicio=date(2026, 11, 2), fecha_termino=date(2026, 11, 3), motivo="compensatorio"),
			self.admin,
		)
		personales = dict(Meta.objects.filter(funcionario=self.social).values_list("item__codigo", "objetivo"))
		self.assertNotIn("TUB", personales)
		self.assertNotIn("EME", personales)
		self.assertLess(personales["EIN"], 40)
