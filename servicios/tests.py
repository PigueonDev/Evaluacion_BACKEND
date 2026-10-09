from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from institucional.models import Cargo, Delegacion, Funcionario

from .models import Actividad, ItemMedicion, Meta, Periodo, Servicio


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
	PANELES = ("servicios:dashboard", "servicios:actividades", "servicios:agenda", "institucional:panel")

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
			for nombre in ("servicios:catalogo", "servicios:actividades", "servicios:agenda"):
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
