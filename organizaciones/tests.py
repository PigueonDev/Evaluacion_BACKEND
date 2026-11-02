import tempfile
from datetime import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from institucional.cuentas import asignar_grupo
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR

from .models import OrganizacionComunitaria, normalizar_territorio


def usuario(username, grupo):
	cuenta = get_user_model().objects.create_user(username=username, password="x")
	asignar_grupo(cuenta, grupo)
	return cuenta


class MantenedorOrganizacionesTest(TestCase):
	def setUp(self):
		self.admin = usuario("adm", GRUPO_ADMINISTRADOR)
		self.supervisor = usuario("sup", GRUPO_SUPERVISOR)
		self.administrativo = usuario("fun", GRUPO_ADMINISTRATIVO)
		self.org = OrganizacionComunitaria.objects.create(nombre="JUNTA DE VECINOS LAS ROSAS", tipo="junta_vecinos", territorio="CENTRO")

	def _datos(self, **extra):
		datos = {"nombre": "Club adulto mayor Esperanza", "tipo": "funcional", "territorio": "PAMPA", "domicilio": "Calle 1", "socios_activos": "25"}
		datos.update(extra)
		return datos

	def test_crud_completo_por_el_administrador(self):
		self.client.force_login(self.admin)
		respuesta = self.client.post(reverse("organizaciones:crear"), self._datos())
		nueva = OrganizacionComunitaria.objects.get(nombre="CLUB ADULTO MAYOR ESPERANZA")
		self.assertRedirects(respuesta, reverse("organizaciones:detalle", args=[nueva.pk]))
		self.assertEqual(nueva.estado, "sin_verificar")
		duplicada = self.client.post(reverse("organizaciones:crear"), self._datos(nombre="club adulto mayor  esperanza"))
		self.assertContains(duplicada, "Ya existe una organización")
		self.assertContains(self.client.get(reverse("organizaciones:listado"), {"q": "esperanza", "territorio": "PAMPA"}), "CLUB ADULTO MAYOR ESPERANZA")
		self.client.post(reverse("organizaciones:editar", args=[nueva.pk]), self._datos(socios_activos="30"))
		nueva.refresh_from_db()
		self.assertEqual(nueva.socios_activos, 30)
		self.client.post(reverse("organizaciones:eliminar", args=[nueva.pk]))
		self.assertFalse(OrganizacionComunitaria.objects.filter(pk=nueva.pk).exists())

	def test_supervisor_verifica_pero_no_elimina(self):
		self.client.force_login(self.supervisor)
		self.client.post(reverse("organizaciones:verificar", args=[self.org.pk]), {"estado": "verificada"})
		self.org.refresh_from_db()
		self.assertEqual(self.org.estado, "verificada")
		self.assertEqual(self.org.verificada_por, self.supervisor)
		self.assertIsNotNone(self.org.verificada_en)
		self.assertEqual(self.client.post(reverse("organizaciones:eliminar", args=[self.org.pk])).status_code, 403)
		self.assertEqual(self.client.get(reverse("organizaciones:crear")).status_code, 200)

	def test_administrativo_solo_consulta(self):
		self.client.force_login(self.administrativo)
		self.assertEqual(self.client.get(reverse("organizaciones:listado")).status_code, 200)
		self.assertEqual(self.client.get(reverse("organizaciones:detalle", args=[self.org.pk])).status_code, 200)
		for nombre, args in (("organizaciones:crear", []), ("organizaciones:editar", [self.org.pk]), ("organizaciones:eliminar", [self.org.pk])):
			self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 403, nombre)
		self.assertEqual(self.client.post(reverse("organizaciones:verificar", args=[self.org.pk]), {"estado": "verificada"}).status_code, 403)
		self.org.refresh_from_db()
		self.assertEqual(self.org.estado, "sin_verificar")

	def test_visitante_va_al_login(self):
		url = reverse("organizaciones:listado")
		self.assertRedirects(self.client.get(url), f"{reverse('institucional:acceso')}?next={url}")


class ImportarJjvvTest(TestCase):
	def test_normaliza_territorio(self):
		self.assertEqual(normalizar_territorio("CENTRO "), "CENTRO")
		self.assertEqual(normalizar_territorio(None), "SIN TERRITORIO")

	def test_importa_sin_verificar_y_es_idempotente(self):
		import openpyxl

		libro = openpyxl.Workbook()
		hoja = libro.active
		hoja.append(["ORGANIZACIONES", "DOMICILIO LEGAL ", "TERRIT. DELEG.", "SOCIOS ACTIVOS", "FECHA CONSTIT.", "Nº REG. P.J.", "FECHA INSCRIPC EN REG.", "REG. DIR. Nº"])
		hoja.append(["JUNTA DE VECINOS EL FARO", "Av. del Mar 100", "AV DEL MAR ", 40, datetime(2010, 1, 5), 1500, datetime(2010, 2, 1), 900])
		hoja.append(["CLUB DEPORTIVO NORTE", None, None, "s/i", None, None, None, None])
		with tempfile.TemporaryDirectory() as carpeta:
			ruta = Path(carpeta) / "base-datos-jjvv-sin-verificar.xlsx"
			libro.save(ruta)
			call_command("importar_jjvv", str(ruta), stdout=open("/dev/null", "w"))
			call_command("importar_jjvv", str(ruta), stdout=open("/dev/null", "w"))
		self.assertEqual(OrganizacionComunitaria.objects.count(), 2)
		faro = OrganizacionComunitaria.objects.get(nombre="JUNTA DE VECINOS EL FARO")
		self.assertEqual(faro.tipo, "junta_vecinos")
		self.assertEqual(faro.territorio, "AV DEL MAR")
		self.assertEqual(faro.estado, "sin_verificar")
		self.assertEqual(faro.fila_origen, 2)
		club = OrganizacionComunitaria.objects.get(nombre="CLUB DEPORTIVO NORTE")
		self.assertIsNone(club.socios_activos)
		self.assertEqual(club.territorio, "SIN TERRITORIO")
