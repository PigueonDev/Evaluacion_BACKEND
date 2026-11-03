import os
import re
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, grupo_usuario

from .cuentas import asignar_grupo
from .models import Cargo, Delegacion, Funcionario

CLAVE = "Serena-demo-2026"


def crear_usuario(username, grupo=None, delegacion=None, cargo=None, **extra):
	usuario = get_user_model().objects.create_user(username=username, password=CLAVE, email=f"{username}@ejemplo.cl", **extra)
	if grupo:
		asignar_grupo(usuario, grupo)
	if delegacion and cargo:
		Funcionario.objects.create(usuario=usuario, identificador=username.upper()[:30], nombre_completo=username, delegacion=delegacion, cargo=cargo)
	return usuario


class AccesoFuncionariosTest(TestCase):
	def setUp(self):
		cache.clear()
		self.admin = crear_usuario("admin-demo", GRUPO_ADMINISTRADOR)
		self.vecino = crear_usuario("vecino-demo")
		self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="Centro histórico", enfoque="Demo")
		self.cargo = Cargo.objects.create(nombre="Gestor")

	def test_paginas_publicas_muestran_boton_de_acceso(self):
		for nombre in ("institucional:inicio", "institucional:autoridades", "servicios:catalogo"):
			self.assertContains(self.client.get(reverse(nombre)), reverse("institucional:acceso"))

	def test_login_lleva_al_dashboard_de_cada_perfil(self):
		crear_usuario("sup", GRUPO_SUPERVISOR, self.centro, self.cargo)
		crear_usuario("fun", GRUPO_ADMINISTRATIVO, self.centro, self.cargo)
		esperado = {
			"admin-demo": "institucional/panel.html",
			"sup": "institucional/dashboard_supervisor.html",
			"fun": "institucional/dashboard_administrativo.html",
		}
		for username, plantilla in esperado.items():
			respuesta = self.client.post(reverse("institucional:acceso"), {"username": username, "password": CLAVE}, follow=True)
			self.assertTemplateUsed(respuesta, plantilla, username)
			self.client.post(reverse("institucional:salir"))

	def test_login_rechaza_usuario_sin_grupo(self):
		respuesta = self.client.post(reverse("institucional:acceso"), {"username": "vecino-demo", "password": CLAVE})
		self.assertEqual(respuesta.status_code, 200)
		self.assertContains(respuesta, "no tiene un perfil del SGR")
		self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

	def test_panel_requiere_sesion(self):
		respuesta = self.client.get(reverse("institucional:panel"))
		self.assertRedirects(respuesta, f"{reverse('institucional:acceso')}?next={reverse('institucional:panel')}")

	def test_verificar_acceso_para_nginx(self):
		url = reverse("institucional:verificar")
		self.assertEqual(self.client.get(url).status_code, 401)
		self.client.force_login(self.vecino)
		self.assertEqual(self.client.get(url).status_code, 401)
		self.client.force_login(crear_usuario("sup2", GRUPO_SUPERVISOR, self.centro, self.cargo))
		self.assertEqual(self.client.get(url).status_code, 401)
		self.client.force_login(self.admin)
		self.assertEqual(self.client.get(url).status_code, 204)

	def test_cerrar_sesion(self):
		self.client.force_login(self.admin)
		respuesta = self.client.post(reverse("institucional:salir"))
		self.assertRedirects(respuesta, reverse("institucional:acceso"))
		self.assertEqual(self.client.get(reverse("institucional:verificar")).status_code, 401)

	def test_login_se_bloquea_tras_intentos_fallidos(self):
		url = reverse("institucional:acceso")
		for _ in range(5):
			self.client.post(url, {"username": "admin-demo", "password": "incorrecta"})
		respuesta = self.client.post(url, {"username": "admin-demo", "password": CLAVE})
		self.assertEqual(respuesta.status_code, 429)
		self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

	def test_login_exitoso_reinicia_intentos(self):
		url = reverse("institucional:acceso")
		for _ in range(4):
			self.client.post(url, {"username": "admin-demo", "password": "incorrecta"})
		respuesta = self.client.post(url, {"username": "admin-demo", "password": CLAVE})
		self.assertRedirects(respuesta, reverse("institucional:mi_panel"), target_status_code=302)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecuperacionClaveTest(TestCase):
	def setUp(self):
		cache.clear()
		self.usuario = crear_usuario("funcionario.demo", GRUPO_ADMINISTRATIVO)

	def _enlace(self):
		self.assertEqual(len(mail.outbox), 1)
		return re.search(r"https?://[^/]+(/acceso/recuperar/[^\s]+/)", mail.outbox[0].body).group(1)

	def test_flujo_completo_con_token(self):
		respuesta = self.client.post(reverse("institucional:recuperar"), {"email": "funcionario.demo@ejemplo.cl"})
		self.assertRedirects(respuesta, reverse("institucional:recuperar_enviado"))
		self.assertIn("Recuperación de contraseña", mail.outbox[0].subject)
		enlace = self._enlace()
		formulario = self.client.get(enlace, follow=True)
		self.assertContains(formulario, "Crea tu nueva contraseña")
		url_formulario = formulario.redirect_chain[-1][0]
		final = self.client.post(url_formulario, {"new_password1": "Faro-Nuevo-2026!", "new_password2": "Faro-Nuevo-2026!"})
		self.assertRedirects(final, reverse("institucional:recuperar_listo"))
		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.check_password("Faro-Nuevo-2026!"))
		entrada = self.client.post(reverse("institucional:acceso"), {"username": "funcionario.demo", "password": "Faro-Nuevo-2026!"})
		self.assertEqual(entrada.status_code, 302)
		self.client.logout()
		reutilizado = self.client.get(enlace, follow=True)
		self.assertContains(reutilizado, "Enlace no válido")

	def test_token_alterado_no_sirve(self):
		self.client.post(reverse("institucional:recuperar"), {"email": "funcionario.demo@ejemplo.cl"})
		enlace = self._enlace()
		alterado = enlace.rstrip("/")[:-3] + "zzz/"
		self.assertContains(self.client.get(alterado), "Enlace no válido")

	def test_correo_desconocido_no_revela_nada(self):
		respuesta = self.client.post(reverse("institucional:recuperar"), {"email": "nadie@ejemplo.cl"})
		self.assertRedirects(respuesta, reverse("institucional:recuperar_enviado"))
		self.assertEqual(len(mail.outbox), 0)

	def test_cuenta_inactiva_no_recibe_correo(self):
		self.usuario.is_active = False
		self.usuario.save()
		respuesta = self.client.post(reverse("institucional:recuperar"), {"email": "funcionario.demo@ejemplo.cl"})
		self.assertRedirects(respuesta, reverse("institucional:recuperar_enviado"))
		self.assertEqual(len(mail.outbox), 0)

	def test_correo_html_y_texto(self):
		self.client.post(reverse("institucional:recuperar"), {"email": "FUNCIONARIO.demo@ejemplo.cl"})
		mensaje = mail.outbox[0]
		self.assertEqual(mensaje.to, ["funcionario.demo@ejemplo.cl"])
		html, tipo = mensaje.alternatives[0]
		self.assertEqual(tipo, "text/html")
		self.assertIn("Crear nueva contraseña", html)
		self.assertIn("/acceso/recuperar/", mensaje.body)

	def test_falla_smtp_no_rompe_el_sitio(self):
		with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("SMTP caído")):
			respuesta = self.client.post(reverse("institucional:recuperar"), {"email": "funcionario.demo@ejemplo.cl"})
		self.assertRedirects(respuesta, reverse("institucional:recuperar_enviado"))

	def test_clave_debil_se_rechaza(self):
		self.client.post(reverse("institucional:recuperar"), {"email": "funcionario.demo@ejemplo.cl"})
		formulario = self.client.get(self._enlace(), follow=True)
		respuesta = self.client.post(formulario.redirect_chain[-1][0], {"new_password1": "1234567890", "new_password2": "1234567890"})
		self.assertEqual(respuesta.status_code, 200)
		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.check_password(CLAVE))


class SeguridadSitioTest(TestCase):
	def setUp(self):
		cache.clear()
		self.admin = crear_usuario("admin-demo", GRUPO_ADMINISTRADOR)
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
		self.assertEqual(respuesta["X-Frame-Options"], "DENY")
		self.assertEqual(respuesta["X-Content-Type-Options"], "nosniff")

	def test_paginas_con_sesion_no_se_guardan_en_cache(self):
		self.client.force_login(self.admin)
		self.assertIn("no-store", self.client.get(reverse("institucional:panel"))["Cache-Control"])

	def test_django_admin_desactivado(self):
		self.client.force_login(self.admin)
		for ruta in ("/admin/", "/admin/login/", "/admin/auth/user/"):
			self.assertEqual(self.client.get(ruta).status_code, 404, ruta)

	def test_evidencias_solo_para_personal(self):
		with self.settings(MEDIA_ROOT=self.directorio, MEDIA_X_ACCEL=False):
			url = "/media/evidencias/acta.pdf"
			self.assertEqual(self.client.get(url).status_code, 302)
			self.client.force_login(self.admin)
			respuesta = self.client.get(url)
			self.assertEqual(respuesta.status_code, 200)
			self.assertIn("attachment", respuesta["Content-Disposition"])

	def test_evidencias_bloquean_salto_de_directorio(self):
		self.client.force_login(self.admin)
		with self.settings(MEDIA_ROOT=self.directorio, MEDIA_X_ACCEL=False):
			for url in ("/media/../secreto.txt", "/media/%2e%2e/secreto.txt", "/media/evidencias/../../secreto.txt"):
				self.assertEqual(self.client.get(url).status_code, 404, url)

	def test_contrasenas_debiles_se_rechazan(self):
		with self.assertRaises(ValidationError):
			validate_password("12345678")
		validate_password("Faro-Serena-2026!")

	def test_evidencia_rechaza_extensiones_peligrosas(self):
		from servicios.models import Evidencia
		campo = Evidencia._meta.get_field("archivo")
		with self.assertRaises(ValidationError):
			campo.run_validators(SimpleUploadedFile("ataque.php", b"<?php ?>"))
		campo.run_validators(SimpleUploadedFile("acta.pdf", b"%PDF-1.4"))


class PerfilesYMantenedorUsuariosTest(TestCase):
	def setUp(self):
		cache.clear()
		self.centro = Delegacion.objects.create(nombre="Centro admin", slug="centro-admin", territorio="Centro", enfoque="Demo")
		self.cargo = Cargo.objects.create(nombre="Gestor admin")
		self.admin = crear_usuario("admin-local", GRUPO_ADMINISTRADOR, self.centro, self.cargo)
		self.client.force_login(self.admin)

	def _datos(self, **extra):
		datos = {
			"username": "nuevo.func", "first_name": "Nuevo", "last_name": "Funcionario", "email": "nuevo@ejemplo.cl",
			"grupo": str(Group.objects.get(name=GRUPO_ADMINISTRATIVO).pk), "is_active": "on",
			"identificador": "F-NEW", "delegacion": str(self.centro.pk), "cargo": str(self.cargo.pk),
			"clave": "Serena-nueva-2026", "clave_confirmacion": "Serena-nueva-2026",
		}
		datos.update(extra)
		return datos

	def test_existen_exactamente_tres_grupos_con_permisos_diferenciados(self):
		self.assertEqual(set(Group.objects.values_list("name", flat=True)), {GRUPO_ADMINISTRADOR, GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO})
		admin = Group.objects.get(name=GRUPO_ADMINISTRADOR)
		supervisor = Group.objects.get(name=GRUPO_SUPERVISOR)
		administrativo = Group.objects.get(name=GRUPO_ADMINISTRATIVO)
		self.assertTrue(admin.permissions.filter(codename="add_user").exists())
		self.assertTrue(supervisor.permissions.filter(codename="aprobar_actividad").exists())
		self.assertTrue(supervisor.permissions.filter(codename="verificar_organizacion").exists())
		self.assertFalse(supervisor.permissions.filter(codename="add_user").exists())
		self.assertFalse(administrativo.permissions.filter(codename="aprobar_actividad").exists())
		self.assertTrue(administrativo.permissions.filter(codename="add_actividad").exists())
		self.assertGreater(admin.permissions.count(), supervisor.permissions.count())

	def test_crud_completo_de_usuarios(self):
		debil = self.client.post(reverse("institucional:usuario_crear"), self._datos(clave="1234567890", clave_confirmacion="1234567890"))
		self.assertTrue(debil.context["form"].errors.get("clave"))
		sin_ficha = self.client.post(reverse("institucional:usuario_crear"), self._datos(delegacion=""))
		self.assertTrue(sin_ficha.context["form"].errors.get("delegacion"))
		respuesta = self.client.post(reverse("institucional:usuario_crear"), self._datos())
		self.assertRedirects(respuesta, reverse("institucional:usuarios"))
		creado = get_user_model().objects.get(username="nuevo.func")
		self.assertEqual(grupo_usuario(creado), GRUPO_ADMINISTRATIVO)
		self.assertTrue(creado.check_password("Serena-nueva-2026"))
		self.assertFalse(creado.is_superuser)
		self.assertEqual(creado.perfil_sgr.delegacion, self.centro)

		listado = self.client.get(reverse("institucional:usuarios"), {"q": "nuevo", "grupo": GRUPO_ADMINISTRATIVO})
		self.assertContains(listado, "nuevo.func")
		self.assertNotContains(listado, "admin-local</strong>")

		datos = self._datos(grupo=str(Group.objects.get(name=GRUPO_SUPERVISOR).pk), clave="", clave_confirmacion="", first_name="Renombrado")
		self.assertRedirects(self.client.post(reverse("institucional:usuario_editar", args=[creado.pk]), datos), reverse("institucional:usuarios"))
		creado = get_user_model().objects.get(pk=creado.pk)
		self.assertEqual(grupo_usuario(creado), GRUPO_SUPERVISOR)
		self.assertEqual(creado.groups.count(), 1)
		self.assertEqual(creado.first_name, "Renombrado")
		self.assertTrue(creado.check_password("Serena-nueva-2026"))

		self.assertContains(self.client.get(reverse("institucional:usuario_eliminar", args=[creado.pk])), "Sí, eliminar")
		self.client.post(reverse("institucional:usuario_eliminar", args=[creado.pk]))
		self.assertFalse(get_user_model().objects.filter(pk=creado.pk).exists())

	def test_administrador_no_se_quita_su_propio_perfil(self):
		datos = self._datos(username="admin-local", identificador="ADMIN-LOCAL", grupo=str(Group.objects.get(name=GRUPO_SUPERVISOR).pk), clave="", clave_confirmacion="")
		respuesta = self.client.post(reverse("institucional:usuario_editar", args=[self.admin.pk]), datos)
		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(grupo_usuario(get_user_model().objects.get(pk=self.admin.pk)), GRUPO_ADMINISTRADOR)

	def test_crud_de_grupos_protege_los_perfiles_base(self):
		respuesta = self.client.post(reverse("institucional:grupo_crear"), {"name": "Auditoría externa", "permissions": []})
		self.assertRedirects(respuesta, reverse("institucional:grupos"))
		grupo = Group.objects.get(name="Auditoría externa")
		self.assertContains(self.client.get(reverse("institucional:grupos"), {"q": "Audit"}), "Auditoría externa")
		self.client.post(reverse("institucional:grupo_editar", args=[grupo.pk]), {"name": "Auditoría interna"})
		grupo.refresh_from_db()
		self.assertEqual(grupo.name, "Auditoría interna")
		self.client.post(reverse("institucional:grupo_eliminar", args=[grupo.pk]))
		self.assertFalse(Group.objects.filter(pk=grupo.pk).exists())
		base = Group.objects.get(name=GRUPO_SUPERVISOR)
		self.client.post(reverse("institucional:grupo_eliminar", args=[base.pk]))
		self.assertTrue(Group.objects.filter(pk=base.pk).exists())

	def test_perfiles_operativos_no_entran_a_administracion(self):
		for username, grupo in (("sup-op", GRUPO_SUPERVISOR), ("fun-op", GRUPO_ADMINISTRATIVO)):
			self.client.force_login(crear_usuario(username, grupo, self.centro, self.cargo))
			for nombre in ("institucional:panel", "institucional:usuarios", "institucional:usuario_crear", "institucional:grupos"):
				self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, f"{grupo} {nombre}")

	def test_cargar_datos_demo_asigna_grupos(self):
		call_command("cargar_datos_demo")
		esperado = {
			"admin.demo": GRUPO_ADMINISTRADOR,
			"delegado.demo": GRUPO_SUPERVISOR,
			"consulta.demo": GRUPO_SUPERVISOR,
			"funcionario.demo": GRUPO_ADMINISTRATIVO,
		}
		for username, grupo in esperado.items():
			cuenta = get_user_model().objects.get(username=username)
			self.assertEqual(grupo_usuario(cuenta), grupo, username)
			self.assertTrue(cuenta.check_password(CLAVE))
			self.assertFalse(cuenta.is_superuser)
		self.assertEqual(Group.objects.count(), 3)
