from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, grupo_usuario
from oficina.models import Reconocimiento
from servicios.management.commands.cargar_datos_demo import CUENTAS_DEMO
from servicios.models import Actividad, Periodo

from .cuentas import asignar_grupo
from .forms import UsuarioForm
from .models import Cargo, Delegacion, Funcionario, UnidadMunicipal


def cuenta(username, grupo):
	usuario = get_user_model().objects.create_user(username=username, password="x")
	asignar_grupo(usuario, grupo)
	return usuario


class MantenedoresMatrizTest(TestCase):
	def setUp(self):
		call_command("cargar_matriz", stdout=StringIO())
		self.admin = cuenta("adm", GRUPO_ADMINISTRADOR)

	def test_solo_el_administrador_entra(self):
		centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="-", enfoque="-")
		supervisor = cuenta("sup", GRUPO_SUPERVISOR)
		Funcionario.objects.create(usuario=supervisor, identificador="S-1", nombre_completo="S", delegacion=centro, cargo=Cargo.objects.get(nombre="Delegado"))
		self.client.force_login(supervisor)
		for nombre in ("institucional:cargos", "institucional:unidades", "institucional:unidad_crear"):
			self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, nombre)

	def test_cargos_muestran_metas_y_avisan_ponderadores_incompletos(self):
		self.client.force_login(self.admin)
		respuesta = self.client.get(reverse("institucional:cargos"))
		self.assertContains(respuesta, "Gestor Social")
		self.assertContains(respuesta, "Los ponderadores no suman 100%", count=1)
		cargo = Cargo.objects.get(nombre="Gestor Social")
		datos = {"nombre": cargo.nombre, "sigla": " soc ", "perfil": "Administrativo", "descripcion": "x", "funciones": list(cargo.funciones.values_list("pk", flat=True)), "activo": "on"}
		self.client.post(reverse("institucional:cargo_editar", args=[cargo.pk]), datos)
		cargo.refresh_from_db()
		self.assertEqual(cargo.sigla, "SOC")

	def test_crea_y_edita_unidades_sin_duplicar(self):
		self.client.force_login(self.admin)
		self.client.post(reverse("institucional:unidad_crear"), {"nombre": "  Oficina   de la Vivienda ", "sigla": "VIV", "tipo": "interna", "activa": "on"})
		unidad = UnidadMunicipal.objects.get(sigla="VIV")
		self.assertEqual(unidad.nombre, "Oficina de la Vivienda")
		repetida = self.client.post(reverse("institucional:unidad_crear"), {"nombre": "oficina de la vivienda", "tipo": "interna"})
		self.assertContains(repetida, "Ya existe una unidad con ese nombre")
		self.client.post(reverse("institucional:unidad_editar", args=[unidad.pk]), {"nombre": unidad.nombre, "sigla": "VIV", "tipo": "interna"})
		unidad.refresh_from_db()
		self.assertFalse(unidad.activa)


class UsuarioCargoMatrizTest(TestCase):
	def setUp(self):
		call_command("cargar_matriz", stdout=StringIO())
		asignar_grupo(get_user_model().objects.create_user(username="semilla"), GRUPO_ADMINISTRADOR)
		self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="-", enfoque="-")

	def datos(self, cargo, grupo, **extra):
		datos = {
			"username": "nuevo", "first_name": "Nuevo", "email": "nuevo@ejemplo.cl", "grupo": Group.objects.get(name=grupo).pk,
			"is_active": True, "identificador": "F-9", "delegacion": self.centro.pk, "cargo": Cargo.objects.get(nombre=cargo).pk,
			"clave": "Delegacion-Centro-2026", "clave_confirmacion": "Delegacion-Centro-2026",
		}
		datos.update(extra)
		return datos

	def test_perfil_debe_corresponder_al_cargo(self):
		form = UsuarioForm(self.datos("Delegado", GRUPO_ADMINISTRATIVO))
		self.assertFalse(form.is_valid())
		self.assertIn("corresponde al perfil Supervisor", form.errors["grupo"][0])

	def test_guarda_codigo_de_area(self):
		form = UsuarioForm(self.datos("Territorial de Organizaciones Comunitarias", GRUPO_ADMINISTRATIVO, codigo_area=" com 2 "))
		self.assertTrue(form.is_valid(), form.errors)
		usuario = form.save()
		self.assertEqual(usuario.perfil_sgr.codigo_area, "COM2")
		self.assertEqual(usuario.perfil_sgr.prefijo_codigo, "COM2")
		invalido = UsuarioForm(self.datos("Gestor Social", GRUPO_ADMINISTRATIVO, username="otro", identificador="F-10", codigo_area="SOC-1"))
		self.assertIn("codigo_area", invalido.errors)


class DatosDemoMatrizTest(TestCase):
	def test_cuentas_por_cargo_e_idempotencia(self):
		call_command("cargar_datos_demo", stdout=StringIO())
		actividades = Actividad.objects.count()
		call_command("cargar_datos_demo", stdout=StringIO())
		self.assertEqual(Actividad.objects.count(), actividades)
		self.assertEqual(Periodo.objects.filter(estado="abierto").count(), 1)
		for username, _, grupo, _, _, cargo, codigo_area, _ in CUENTAS_DEMO:
			usuario = get_user_model().objects.get(username=username)
			self.assertEqual(grupo_usuario(usuario), grupo, username)
			self.assertEqual(usuario.perfil_sgr.cargo.nombre, cargo)
			self.assertEqual(usuario.perfil_sgr.cargo.perfil, grupo)
			self.assertEqual(usuario.perfil_sgr.codigo_area, codigo_area)
		self.assertTrue(Actividad.objects.filter(codigo_verificador__startswith="COM1-").exists())
		self.assertEqual(Reconocimiento.objects.count(), 3)
		self.assertEqual(Group.objects.count(), 3)
