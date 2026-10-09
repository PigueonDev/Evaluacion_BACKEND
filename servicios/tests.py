from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from institucional.models import Cargo, Delegacion, Funcionario

from .models import Actividad, ItemMedicion, Meta, Periodo


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


class AccesoAdministrativoTest(TestCase):
    def test_el_sitio_ciudadano_no_muestra_el_menu_interno(self):
        respuesta = self.client.get("/")
        self.assertContains(respuesta, "Servicios ciudadanos")
        self.assertContains(respuesta, "Área administrativa")
        self.assertNotContains(respuesta, "Panel SGR")
        self.assertNotContains(respuesta, ">Actividades<")
        self.assertNotContains(respuesta, ">Agenda<")
        self.assertNotContains(respuesta, ">Administración<")

    def test_las_ventanas_internas_piden_ingreso(self):
        for ruta in ("/servicios/dashboard/", "/servicios/actividades/", "/servicios/agenda/"):
            respuesta = self.client.get(ruta)
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn("/servicios/ingreso/", respuesta.url)

    def test_el_personal_ve_el_menu_administrativo(self):
        get_user_model().objects.create_user(username="gestor", password="clave-demo", is_staff=True)
        ingreso = self.client.post("/servicios/ingreso/", {"username": "gestor", "password": "clave-demo"})
        self.assertRedirects(ingreso, "/servicios/dashboard/")
        panel = self.client.get("/servicios/dashboard/")
        self.assertContains(panel, "Panel SGR")
        self.assertContains(panel, "Actividades")
        self.assertContains(panel, "Agenda")
        self.assertContains(panel, "Administración")
        self.assertNotContains(panel, "Servicios ciudadanos")
        self.assertNotContains(panel, "Consulta por WhatsApp")

    def test_una_cuenta_ciudadana_no_entra(self):
        get_user_model().objects.create_user(username="vecino", password="clave-demo")
        respuesta = self.client.post("/servicios/ingreso/", {"username": "vecino", "password": "clave-demo"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no tiene acceso al área administrativa")
        panel = self.client.get("/servicios/dashboard/")
        self.assertEqual(panel.status_code, 302)
