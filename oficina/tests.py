from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from institucional.cuentas import asignar_grupo
from institucional.models import Cargo, Delegacion, Funcionario
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR
from laserena.rut import normalizar_rut
from servicios.models import Auditoria, ItemMedicion, Meta, Periodo

from .models import AjusteMeta, Ausencia, BeneficioNino, Carta
from .transacciones import anular_ausencia, registrar_ausencia

HOY = date(2026, 6, 17)


def cuenta(username, grupo):
	usuario = get_user_model().objects.create_user(username=username, password="x")
	asignar_grupo(usuario, grupo)
	return usuario


class Base(TestCase):
	def setUp(self):
		self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="Centro", enfoque="-")
		self.norte = Delegacion.objects.create(nombre="Norte", slug="norte", territorio="Norte", enfoque="-")
		self.cargo = Cargo.objects.create(nombre="Gestor")
		self.admin = cuenta("adm", GRUPO_ADMINISTRADOR)
		self.supervisor = cuenta("sup", GRUPO_SUPERVISOR)
		self.supervisor_norte = cuenta("sup-norte", GRUPO_SUPERVISOR)
		self.administrativo = cuenta("fun", GRUPO_ADMINISTRATIVO)
		self.delegado = Funcionario.objects.create(usuario=self.supervisor, identificador="S-1", nombre_completo="Delegada Centro", delegacion=self.centro, cargo=self.cargo)
		Funcionario.objects.create(usuario=self.supervisor_norte, identificador="S-2", nombre_completo="Delegado Norte", delegacion=self.norte, cargo=self.cargo)
		self.funcionario = Funcionario.objects.create(usuario=self.administrativo, identificador="F-1", nombre_completo="Ana Funcionaria", delegacion=self.centro, cargo=self.cargo)


class RutTest(TestCase):
	def test_valida_digito_verificador(self):
		self.assertEqual(normalizar_rut("24.567.891-6"), "24567891-6")
		self.assertEqual(normalizar_rut("14.235.165-k"), "14235165-K")
		for invalido in ("24.567.891-5", "abc", "123-4", ""):
			with self.assertRaises(ValidationError):
				normalizar_rut(invalido)


class CartasTest(Base):
	def _datos(self, **extra):
		datos = {"fecha_ingreso": "2026-06-10", "tipo": "solicitud", "remitente": "JJVV Las Rosas", "asunto": "Poda de árboles", "estado": "ingresada"}
		datos.update(extra)
		return datos

	def test_crud_supervisor_con_folio_y_ambito(self):
		self.client.force_login(self.supervisor)
		self.client.post(reverse("oficina:carta_crear"), self._datos())
		carta = Carta.objects.get()
		self.assertEqual(carta.folio, "OP-2026-0001")
		self.assertEqual(carta.delegacion, self.centro)
		self.assertContains(self.client.get(reverse("oficina:cartas"), {"q": "poda"}), "OP-2026-0001")
		respuesta = self.client.post(reverse("oficina:carta_editar", args=[carta.pk]), self._datos(estado="derivada"))
		self.assertContains(respuesta, "Indica a quién se deriva")
		self.client.post(reverse("oficina:carta_editar", args=[carta.pk]), self._datos(estado="derivada", derivada_a=self.funcionario.pk))
		carta.refresh_from_db()
		self.assertEqual(carta.estado, "derivada")
		self.client.force_login(self.supervisor_norte)
		self.assertEqual(self.client.get(reverse("oficina:carta_detalle", args=[carta.pk])).status_code, 404)
		self.client.force_login(self.supervisor)
		self.client.post(reverse("oficina:carta_eliminar", args=[carta.pk]))
		self.assertFalse(Carta.objects.exists())

	def test_administrativo_solo_responde_las_derivadas(self):
		propia = Carta.objects.create(fecha_ingreso=date(2026, 6, 10), remitente="A", asunto="Uno", delegacion=self.centro, estado="derivada", derivada_a=self.funcionario, registrada_por=self.admin)
		ajena = Carta.objects.create(remitente="B", asunto="Dos", delegacion=self.centro, registrada_por=self.admin)
		self.client.force_login(self.administrativo)
		listado = self.client.get(reverse("oficina:cartas"))
		self.assertContains(listado, propia.folio)
		self.assertNotContains(listado, ajena.folio)
		self.assertEqual(self.client.get(reverse("oficina:carta_crear")).status_code, 403)
		self.assertEqual(self.client.post(reverse("oficina:carta_eliminar", args=[propia.pk])).status_code, 403)
		sin_respuesta = self.client.post(reverse("oficina:carta_editar", args=[propia.pk]), {"estado": "respondida", "respuesta": "", "fecha_respuesta": "2026-06-12"})
		self.assertContains(sin_respuesta, "debe registrar la respuesta")
		self.client.post(reverse("oficina:carta_editar", args=[propia.pk]), {"estado": "respondida", "respuesta": "Se agenda visita.", "fecha_respuesta": "2026-06-12"})
		propia.refresh_from_db()
		self.assertEqual(propia.estado, "respondida")
		self.assertEqual(propia.asunto, "Uno")


class BeneficiosTest(Base):
	def _datos(self, **extra):
		datos = {"rut_nino": "24.567.891-6", "nombre_nino": "Martina Rojas", "fecha_nacimiento": "2017-05-14", "sexo": "F", "tipo": "regalo_navidad", "apoderado": "Constanza Pizarro", "estado": "registrado"}
		datos.update(extra)
		return datos

	def test_crud_y_rut_unico_entre_delegaciones(self):
		self.client.force_login(self.supervisor)
		self.client.post(reverse("oficina:beneficio_crear"), self._datos())
		beneficio = BeneficioNino.objects.get()
		self.assertEqual((beneficio.rut_nino, beneficio.delegacion), ("24567891-6", self.centro))
		self.assertContains(self.client.get(reverse("oficina:beneficios"), {"q": "24.567.891-6"}), "Martina Rojas")
		self.client.force_login(self.supervisor_norte)
		repetido = self.client.post(reverse("oficina:beneficio_crear"), self._datos(rut_nino="24567891-6", nombre_nino="Otra"))
		self.assertContains(repetido, "ya tiene un beneficio registrado en la delegación Centro")
		self.assertContains(self.client.post(reverse("oficina:beneficio_crear"), self._datos(rut_nino="24.567.891-5")), "dígito verificador")
		self.assertContains(self.client.post(reverse("oficina:beneficio_crear"), self._datos(rut_nino="25.123.456-6", fecha_nacimiento="2005-01-01")), "hasta 14 años")
		self.assertEqual(BeneficioNino.objects.count(), 1)
		self.client.force_login(self.supervisor)
		self.client.post(reverse("oficina:beneficio_editar", args=[beneficio.pk]), self._datos(estado="entregado", fecha_entrega="2026-06-15"))
		beneficio.refresh_from_db()
		self.assertEqual(beneficio.estado, "entregado")
		self.client.post(reverse("oficina:beneficio_eliminar", args=[beneficio.pk]))
		self.assertFalse(BeneficioNino.objects.exists())

	def test_administrativo_registra_pero_no_elimina(self):
		self.client.force_login(self.administrativo)
		self.client.post(reverse("oficina:beneficio_crear"), self._datos())
		beneficio = BeneficioNino.objects.get()
		self.assertEqual(self.client.post(reverse("oficina:beneficio_eliminar", args=[beneficio.pk])).status_code, 403)


@mock.patch("django.utils.timezone.localdate", return_value=HOY)
class RegistrarAusenciaTest(Base):
	def setUp(self):
		super().setUp()
		self.item = ItemMedicion.objects.create(codigo="A-1", nombre="Operativos")
		self.item_cargo = ItemMedicion.objects.create(codigo="A-2", nombre="Reuniones")
		self.periodo = Periodo.objects.create(nombre="2026", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))
		self.meta = Meta.objects.create(periodo=self.periodo, item=self.item, funcionario=self.delegado, objetivo=Decimal("73"), ponderador=60)
		Meta.objects.create(periodo=self.periodo, item=self.item_cargo, cargo=self.cargo, objetivo=Decimal("36.5"), ponderador=40)

	def _ausencia(self, inicio=date(2026, 7, 1), termino=date(2026, 8, 12), **extra):
		return Ausencia(funcionario=self.delegado, periodo=self.periodo, fecha_inicio=inicio, fecha_termino=termino, motivo="licencia", **extra)

	def test_ajusta_metas_y_semaforo_en_una_unidad(self, _hoy):
		ausencia = registrar_ausencia(self._ausencia(), self.admin)
		self.assertEqual(ausencia.dias, 43)
		self.meta.refresh_from_db()
		self.assertEqual(self.meta.objetivo, Decimal("64.40"))
		self.assertEqual(self.meta.version, 2)
		personal = Meta.objects.get(item=self.item_cargo, funcionario=self.delegado)
		self.assertEqual(personal.objetivo, Decimal("32.20"))
		self.assertEqual(ausencia.ajustes.count(), 2)
		self.assertTrue(AjusteMeta.objects.get(meta=personal).meta_creada)
		self.assertTrue(Auditoria.objects.filter(accion="registrar_ausencia").exists())

	def test_semaforo_mejora_al_bajar_la_meta(self, _hoy):
		self.meta.objetivo = Decimal("10")
		self.meta.save()
		with mock.patch.object(Meta, "avance_aprobado", new_callable=mock.PropertyMock, return_value=4):
			antes = self.meta.semaforo(HOY)
			registrar_ausencia(self._ausencia(inicio=date(2026, 6, 18), termino=date(2026, 12, 20)), self.admin)
			ajuste = AjusteMeta.objects.get(meta=self.meta)
		self.assertEqual((antes, ajuste.semaforo_anterior), ("ambar", "ambar"))
		self.assertEqual(ajuste.semaforo_nuevo, "verde")

	def test_error_a_mitad_no_deja_nada(self, _hoy):
		with mock.patch("oficina.transacciones.Auditoria.objects.create", side_effect=RuntimeError("falla")):
			with self.assertRaises(RuntimeError):
				registrar_ausencia(self._ausencia(), self.admin)
		self.meta.refresh_from_db()
		self.assertEqual(self.meta.objetivo, Decimal("73"))
		self.assertFalse(Ausencia.objects.exists())
		self.assertFalse(Meta.objects.filter(item=self.item_cargo, funcionario=self.delegado).exists())

	def test_validaciones(self, _hoy):
		with self.assertRaisesMessage(ValidationError, "todos los días"):
			registrar_ausencia(self._ausencia(inicio=date(2026, 1, 1), termino=date(2026, 12, 31)), self.admin)
		registrar_ausencia(self._ausencia(), self.admin)
		with self.assertRaisesMessage(ValidationError, "se cruza"):
			registrar_ausencia(self._ausencia(inicio=date(2026, 8, 1), termino=date(2026, 8, 20)), self.admin)
		with self.assertRaisesMessage(ValidationError, "dentro del período"):
			registrar_ausencia(self._ausencia(inicio=date(2025, 12, 20), termino=date(2026, 1, 5)), self.admin)
		self.assertEqual(Ausencia.objects.count(), 1)

	def test_anular_restituye(self, _hoy):
		ausencia = registrar_ausencia(self._ausencia(), self.admin)
		anular_ausencia(ausencia, self.supervisor)
		self.meta.refresh_from_db()
		self.assertEqual(self.meta.objetivo, Decimal("73.00"))
		ausencia.refresh_from_db()
		self.assertEqual(ausencia.estado, "anulada")

	def test_vista_supervisor_y_ambito(self, _hoy):
		self.client.force_login(self.supervisor)
		respuesta = self.client.post(reverse("oficina:ausencia_registrar"), {
			"funcionario": self.delegado.pk, "periodo": self.periodo.pk, "fecha_inicio": "2026-07-01", "fecha_termino": "2026-08-12", "motivo": "feriado",
		})
		ausencia = Ausencia.objects.get()
		self.assertRedirects(respuesta, reverse("oficina:ausencia_detalle", args=[ausencia.pk]))
		self.assertContains(self.client.get(respuesta.url), "64,40")
		self.client.force_login(self.supervisor_norte)
		formulario = self.client.get(reverse("oficina:ausencia_registrar"))
		self.assertNotContains(formulario, "Delegada Centro")
		self.assertEqual(self.client.get(reverse("oficina:ausencia_detalle", args=[ausencia.pk])).status_code, 404)
		self.client.force_login(self.administrativo)
		self.assertEqual(self.client.get(reverse("oficina:ausencia_registrar")).status_code, 403)
