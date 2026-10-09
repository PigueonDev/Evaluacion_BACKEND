import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
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


class SeguridadSitioTest(TestCase):
	def setUp(self):
		cache.clear()
		modelo_usuario = get_user_model()
		self.staff = modelo_usuario.objects.create_user(username="admin-demo", password="clave-demo-123", is_staff=True)
		self.raiz = tempfile.mkdtemp()
		self.directorio = os.path.join(self.raiz, "media")
		os.makedirs(os.path.join(self.directorio, "evidencias"))
		with open(os.path.join(self.directorio, "evidencias", "acta.pdf"), "wb") as archivo:
			archivo.write(b"%PDF-1.4 demo")
		with open(os.path.join(self.raiz, "secreto.txt"), "w") as archivo:
			archivo.write("no")

	def tearDown(self):
		shutil.rmtree(self.raiz, ignore_errors=True)

	def test_cabeceras_de_seguridad(self):
		respuesta = self.client.get(reverse("institucional:inicio"))
		self.assertIn("default-src 'self'", respuesta["Content-Security-Policy"])
		self.assertIn("frame-ancestors 'none'", respuesta["Content-Security-Policy"])
		self.assertEqual(respuesta["X-Frame-Options"], "DENY")
		self.assertEqual(respuesta["X-Content-Type-Options"], "nosniff")
		self.assertIn("camera=()", respuesta["Permissions-Policy"])

	def test_paginas_con_sesion_no_se_guardan_en_cache(self):
		self.client.force_login(self.staff)
		self.assertIn("no-store", self.client.get(reverse("institucional:panel"))["Cache-Control"])

	def test_login_del_admin_tambien_se_bloquea(self):
		for _ in range(5):
			self.client.post("/admin/login/", {"username": "admin-demo", "password": "incorrecta"})
		respuesta = self.client.post("/admin/login/", {"username": "admin-demo", "password": "clave-demo-123"})
		self.assertEqual(respuesta.status_code, 429)

	def test_login_del_admin_redirige_al_admin(self):
		respuesta = self.client.post("/admin/login/?next=/admin/", {"username": "admin-demo", "password": "clave-demo-123", "next": "/admin/"})
		self.assertRedirects(respuesta, "/admin/")

	def test_evidencias_solo_para_personal(self):
		with self.settings(MEDIA_ROOT=self.directorio, MEDIA_X_ACCEL=False):
			url = "/media/evidencias/acta.pdf"
			self.assertEqual(self.client.get(url).status_code, 302)
			self.client.force_login(self.staff)
			respuesta = self.client.get(url)
			self.assertEqual(respuesta.status_code, 200)
			self.assertIn("attachment", respuesta["Content-Disposition"])

	def test_evidencias_con_nginx_usan_x_accel(self):
		self.client.force_login(self.staff)
		with self.settings(MEDIA_ROOT=self.directorio, MEDIA_X_ACCEL=True):
			respuesta = self.client.get("/media/evidencias/acta.pdf")
			self.assertEqual(respuesta["X-Accel-Redirect"], "/media-protegida/evidencias/acta.pdf")

	def test_evidencias_bloquean_salto_de_directorio(self):
		self.client.force_login(self.staff)
		with self.settings(MEDIA_ROOT=self.directorio, MEDIA_X_ACCEL=False):
			for url in ("/media/../secreto.txt", "/media/%2e%2e/secreto.txt", "/media/evidencias/../../secreto.txt"):
				self.assertEqual(self.client.get(url).status_code, 404, url)

	def test_contrasenas_debiles_se_rechazan(self):
		with self.assertRaises(ValidationError):
			validate_password("12345678")
		with self.assertRaises(ValidationError):
			validate_password("password123")
		validate_password("Faro-Serena-2026!")

	def test_evidencia_rechaza_extensiones_peligrosas(self):
		from servicios.models import Evidencia
		campo = Evidencia._meta.get_field("archivo")
		with self.assertRaises(ValidationError):
			campo.run_validators(SimpleUploadedFile("ataque.php", b"<?php system($_GET['c']); ?>"))
		with self.assertRaises(ValidationError):
			campo.run_validators(SimpleUploadedFile("grande.pdf", b"0" * (5 * 1024 * 1024 + 1)))
		campo.run_validators(SimpleUploadedFile("acta.pdf", b"%PDF-1.4"))
