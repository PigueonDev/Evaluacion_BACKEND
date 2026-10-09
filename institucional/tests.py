from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Delegacion


class AccesoFuncionariosTest(TestCase):
	def setUp(self):
		cache.clear()
		modelo_usuario = get_user_model()
		self.staff = modelo_usuario.objects.create_user(username="admin-demo", password="clave-demo-123", is_staff=True)
		self.vecino = modelo_usuario.objects.create_user(username="vecino-demo", password="clave-demo-123")
		Delegacion.objects.create(nombre="Centro", slug="centro", territorio="Centro histórico", enfoque="Demo")

	def test_paginas_publicas_muestran_boton_de_acceso(self):
		for nombre in ("institucional:inicio", "institucional:autoridades", "servicios:catalogo"):
			respuesta = self.client.get(reverse(nombre))
			self.assertContains(respuesta, reverse("institucional:acceso"))

	def test_login_staff_redirige_al_panel(self):
		respuesta = self.client.post(reverse("institucional:acceso"), {"username": "admin-demo", "password": "clave-demo-123"})
		self.assertRedirects(respuesta, reverse("institucional:panel"))

	def test_login_rechaza_usuario_sin_permiso_staff(self):
		respuesta = self.client.post(reverse("institucional:acceso"), {"username": "vecino-demo", "password": "clave-demo-123"})
		self.assertEqual(respuesta.status_code, 200)
		self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

	def test_panel_requiere_sesion(self):
		respuesta = self.client.get(reverse("institucional:panel"))
		self.assertRedirects(respuesta, f"{reverse('institucional:acceso')}?next={reverse('institucional:panel')}")

	@override_settings(PHPMYADMIN_URL="/phpmyadmin/", PHPMYADMIN_DB="sgr_laserena")
	def test_panel_enlaza_tablas_en_phpmyadmin(self):
		self.client.force_login(self.staff)
		respuesta = self.client.get(reverse("institucional:panel"))
		self.assertContains(respuesta, "/phpmyadmin/index.php?route=%2Fsql&amp;db=sgr_laserena&amp;table=institucional_delegacion")
		self.assertContains(respuesta, "route=%2Ftable%2Fchange")
		self.assertContains(respuesta, "Sedes y delegaciones")

	def test_verificar_acceso_para_nginx(self):
		url = reverse("institucional:verificar")
		self.assertEqual(self.client.get(url).status_code, 401)
		self.client.force_login(self.vecino)
		self.assertEqual(self.client.get(url).status_code, 401)
		self.client.force_login(self.staff)
		self.assertEqual(self.client.get(url).status_code, 204)

	def test_cerrar_sesion(self):
		self.client.force_login(self.staff)
		respuesta = self.client.post(reverse("institucional:salir"))
		self.assertRedirects(respuesta, reverse("institucional:inicio"))
		self.assertEqual(self.client.get(reverse("institucional:verificar")).status_code, 401)

	def test_login_se_bloquea_tras_intentos_fallidos(self):
		url = reverse("institucional:acceso")
		for _ in range(5):
			self.client.post(url, {"username": "admin-demo", "password": "incorrecta"})
		respuesta = self.client.post(url, {"username": "admin-demo", "password": "clave-demo-123"})
		self.assertEqual(respuesta.status_code, 429)
		self.assertContains(respuesta, "Demasiados intentos fallidos", status_code=429)
		self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

	def test_login_exitoso_reinicia_intentos(self):
		url = reverse("institucional:acceso")
		for _ in range(4):
			self.client.post(url, {"username": "admin-demo", "password": "incorrecta"})
		respuesta = self.client.post(url, {"username": "admin-demo", "password": "clave-demo-123"})
		self.assertRedirects(respuesta, reverse("institucional:panel"))
