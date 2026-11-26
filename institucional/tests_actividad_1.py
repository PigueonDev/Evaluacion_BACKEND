"""Una prueba por hueco de la Actividad 1. Si la regla se pierde, la prueba falla."""

import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, asignar_grupo
from oficina.models import Reconocimiento
from oficina.transacciones import registrar_ausencia
from servicios.desempeno import resumen_funcionario
from servicios.models import Actividad, Caso, Compromiso, ItemMedicion, Meta, Periodo, TareaPreparatoria, TipoAtencion
from servicios.tests import HOY_PRUEBAS, fijar_hoy
from servicios.transacciones import registrar_actividad

from .models import Cargo, Delegacion, EstadoClave, Funcionario, Hito, Territorio, Vecino

CLAVE_TEMPORAL = "Temporal-Ingreso-2026"
CLAVE_PROPIA = "Propia-Ingreso-2026"


def _png():
	buffer = BytesIO()
	Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
	return SimpleUploadedFile("captura.png", buffer.getvalue(), content_type="image/png")


def _cuenta(username, grupo, delegacion=None, cargo=None, nombre=""):
	usuario = get_user_model().objects.create_user(username=username, password="Clave-fija-2026", email=f"{username}@ejemplo.cl")
	asignar_grupo(usuario, grupo)
	funcionario = None
	if delegacion and cargo:
		funcionario = Funcionario.objects.create(
			usuario=usuario, identificador=username.upper()[:30], nombre_completo=nombre or username,
			delegacion=delegacion, cargo=cargo,
		)
	return usuario, funcionario


class Actividad1HuecosTest(TestCase):
	def setUp(self):
		fijar_hoy(self)
		self.media = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.media, True)
		ajuste = override_settings(MEDIA_ROOT=self.media)
		ajuste.enable()
		self.addCleanup(ajuste.disable)
		self.admin, _ = _cuenta("admin-act1", GRUPO_ADMINISTRADOR)
		self.centro = Delegacion.objects.create(nombre="Centro act1", slug="centro-act1", territorio="Centro", enfoque="Demo")
		self.norte = Delegacion.objects.create(nombre="Norte act1", slug="norte-act1", territorio="La Pampa", enfoque="Demo")
		self.cargo = Cargo.objects.create(nombre="Gestor act1", perfil=GRUPO_ADMINISTRATIVO, sigla="GAC")
		self.cargo_delegado = Cargo.objects.create(nombre="Delegado", perfil=GRUPO_SUPERVISOR, sigla="DEL")
		self.funcionario_user, self.funcionario = _cuenta("fun-act1", GRUPO_ADMINISTRATIVO, self.centro, self.cargo, "Ana Centro")
		self.companero_user, self.companero = _cuenta("par-act1", GRUPO_ADMINISTRATIVO, self.centro, self.cargo, "Bruno Centro")
		self.supervisor_user, self.delegado = _cuenta("sup-act1", GRUPO_SUPERVISOR, self.centro, self.cargo_delegado, "Delegada Centro")
		self.supervisor_norte, _ = _cuenta("sup-norte-act1", GRUPO_SUPERVISOR, self.norte, self.cargo_delegado, "Delegado Norte")
		self.item = ItemMedicion.objects.create(codigo="ACT1", nombre="Ítem actividad 1")
		self.periodo = Periodo.objects.create(nombre="Año act1", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))

	def _entrar(self, usuario):
		self.client.force_login(usuario)

	def test_clave_temporal_obliga_el_cambio_en_el_primer_ingreso(self):
		self._entrar(self.admin)
		grupo = Group.objects.get(name=GRUPO_ADMINISTRATIVO)
		alta = self.client.get(reverse("institucional:usuario_crear"))
		self.assertContains(alta, "Contraseña temporal")
		creada = self.client.post(reverse("institucional:usuario_crear"), {
			"username": "ingreso.nuevo", "first_name": "Ingreso", "last_name": "Nuevo", "email": "ingreso@ejemplo.cl",
			"grupo": str(grupo.pk), "is_active": "on", "identificador": "F-TMP-1",
			"delegacion": str(self.centro.pk), "cargo": str(self.cargo.pk),
			"clave": CLAVE_TEMPORAL, "clave_confirmacion": CLAVE_TEMPORAL,
		})
		self.assertRedirects(creada, reverse("institucional:usuarios"))
		cuenta = get_user_model().objects.get(username="ingreso.nuevo")
		self.assertTrue(cuenta.estado_clave.debe_cambiar_clave)
		self.assertFalse(EstadoClave.objects.filter(usuario=self.funcionario_user, debe_cambiar_clave=True).exists())

		cliente = self.client_class()
		self.assertTrue(cliente.login(username="ingreso.nuevo", password=CLAVE_TEMPORAL))
		bloqueado = cliente.get(reverse("servicios:agenda"))
		self.assertRedirects(bloqueado, reverse("institucional:cambiar_clave"))
		cambio = cliente.post(reverse("institucional:cambiar_clave"), {"new_password1": CLAVE_PROPIA, "new_password2": CLAVE_PROPIA})
		self.assertRedirects(cambio, reverse("institucional:mi_panel"))
		cuenta.refresh_from_db()
		self.assertFalse(cuenta.estado_clave.debe_cambiar_clave)
		self.assertEqual(cliente.get(reverse("servicios:agenda")).status_code, 200)
		self.assertTrue(cuenta.check_password(CLAVE_PROPIA))

	def test_crud_de_delegaciones(self):
		self._entrar(self.admin)
		self.assertEqual(self.client.get(reverse("institucional:delegaciones")).status_code, 200)
		alta = self.client.post(reverse("institucional:delegacion_crear"), {
			"nombre": "Poniente", "territorio": "Centro", "enfoque": "Borde poniente", "activa": "on",
		})
		self.assertRedirects(alta, reverse("institucional:delegaciones"))
		delegacion = Delegacion.objects.get(nombre="Poniente")
		self.assertEqual(delegacion.slug, "poniente")
		edicion = self.client.post(reverse("institucional:delegacion_editar", args=[delegacion.pk]), {
			"nombre": "Poniente Sur", "slug": "poniente", "territorio": "Centro", "enfoque": "Actualizado", "activa": "on",
		})
		self.assertRedirects(edicion, reverse("institucional:delegaciones"))
		delegacion.refresh_from_db()
		self.assertEqual((delegacion.nombre, delegacion.enfoque), ("Poniente Sur", "Actualizado"))
		self.client.post(reverse("institucional:delegacion_eliminar", args=[delegacion.pk]))
		self.assertFalse(Delegacion.objects.filter(pk=delegacion.pk).exists())
		self.client.force_login(self.supervisor_user)
		self.assertEqual(self.client.get(reverse("institucional:delegacion_crear")).status_code, 403)

	def test_crud_de_territorios(self):
		self._entrar(self.admin)
		alta = self.client.post(reverse("institucional:territorio_crear"), {
			"codigo": "costa", "nombre": "Borde costero", "descripcion": "Frente de mar", "activo": "on",
		})
		self.assertRedirects(alta, reverse("institucional:territorios"))
		territorio = Territorio.objects.get(codigo="COSTA")
		delegacion = Delegacion.objects.create(nombre="Costa act1", slug="costa-act1", territorio="Borde costero", enfoque="Mar")
		edicion = self.client.post(reverse("institucional:territorio_editar", args=[territorio.pk]), {
			"codigo": "COSTA", "nombre": "Borde costero norte", "descripcion": "Frente de mar", "activo": "on",
		})
		self.assertRedirects(edicion, reverse("institucional:territorios"))
		delegacion.refresh_from_db()
		self.assertEqual(delegacion.territorio, "Borde costero norte")
		self.assertContains(self.client.get(reverse("institucional:delegacion_crear")), "Borde costero norte")
		self.client.post(reverse("institucional:territorio_eliminar", args=[territorio.pk]))
		self.assertFalse(Territorio.objects.filter(pk=territorio.pk).exists())

	def test_crud_de_vecinos(self):
		self._entrar(self.admin)
		alta = self.client.post(reverse("institucional:vecino_crear"), {
			"delegacion": str(self.centro.pk), "nombre": "Rosa Campos", "rut": "12.345.678-5",
			"telefono": "+56 9 2222 3333", "correo": "", "direccion": "Los Aromos 10", "activo": "on",
		})
		self.assertRedirects(alta, reverse("institucional:vecinos"))
		vecino = Vecino.objects.get(nombre="Rosa Campos")
		self.assertEqual(vecino.rut, "12345678-5")
		edicion = self.client.post(reverse("institucional:vecino_editar", args=[vecino.pk]), {
			"delegacion": str(self.centro.pk), "nombre": "Rosa Campos Soto", "rut": "12.345.678-5",
			"telefono": "+56 9 2222 4444", "correo": "", "direccion": "Los Aromos 10", "activo": "on",
		})
		self.assertRedirects(edicion, reverse("institucional:vecinos"))
		vecino.refresh_from_db()
		self.assertEqual(vecino.telefono, "+56 9 2222 4444")
		self.client.post(reverse("institucional:vecino_eliminar", args=[vecino.pk]))
		self.assertFalse(Vecino.objects.filter(pk=vecino.pk).exists())

	def test_crud_de_hitos(self):
		self._entrar(self.admin)
		datos = {
			"nombre": "Entrega de sede", "descripcion": "Hito territorial", "fecha": "2026-06-17",
			"delegacion": str(self.centro.pk), "responsable": str(self.funcionario.pk), "estado": "pendiente", "activo": "on",
		}
		ajeno = dict(datos, responsable=str(self.supervisor_norte.perfil_sgr.pk))
		rechazo = self.client.post(reverse("institucional:hito_crear"), ajeno)
		self.assertEqual(rechazo.status_code, 200)
		self.assertFalse(Hito.objects.exists())
		alta = self.client.post(reverse("institucional:hito_crear"), datos)
		self.assertRedirects(alta, reverse("institucional:hitos"))
		hito = Hito.objects.get(nombre="Entrega de sede")
		self.assertEqual(hito.responsable, self.funcionario)
		datos["estado"] = "cumplido"
		datos["nombre"] = "Entrega de sede cumplida"
		self.assertRedirects(self.client.post(reverse("institucional:hito_editar", args=[hito.pk]), datos), reverse("institucional:hitos"))
		hito.refresh_from_db()
		self.assertEqual((hito.nombre, hito.estado), ("Entrega de sede cumplida", "cumplido"))
		self.client.post(reverse("institucional:hito_eliminar", args=[hito.pk]))
		self.assertFalse(Hito.objects.filter(pk=hito.pk).exists())

	def test_crud_de_cargos_incluye_alta_y_baja(self):
		self._entrar(self.admin)
		listado = self.client.get(reverse("institucional:cargos"))
		self.assertContains(listado, reverse("institucional:cargo_crear"))
		alta = self.client.post(reverse("institucional:cargo_crear"), {
			"nombre": "Analista territorial", "sigla": "an", "perfil": GRUPO_ADMINISTRATIVO, "descripcion": "Analiza", "activo": "on",
		})
		self.assertRedirects(alta, reverse("institucional:cargos"))
		cargo = Cargo.objects.get(nombre="Analista territorial")
		self.assertEqual(cargo.sigla, "AN")
		self.assertContains(self.client.get(reverse("institucional:cargos")), reverse("institucional:cargo_eliminar", args=[cargo.pk]))
		self.client.post(reverse("institucional:cargo_eliminar", args=[cargo.pk]))
		self.assertFalse(Cargo.objects.filter(pk=cargo.pk).exists())

	def test_crud_de_tipos_y_subtipos_de_atencion(self):
		self._entrar(self.admin)
		alta = self.client.post(reverse("institucional:tipo_crear"), {"codigo": "visitas", "nombre": "Visitas domiciliarias", "activo": "on"})
		self.assertRedirects(alta, reverse("institucional:tipos_atencion"))
		tipo = TipoAtencion.objects.get(codigo="visitas")
		sub = self.client.post(reverse("institucional:subtipo_crear", args=[tipo.pk]), {
			"codigo": "visita_social", "nombre": "Visita social", "forma": "Informe", "activo": "on",
		})
		self.assertRedirects(sub, reverse("institucional:tipos_atencion"))
		self.assertTrue(tipo.subtipos.filter(codigo="visita_social", forma="Informe").exists())
		caso = Caso(identificacion="C-VIS", nombre="Atención nueva", delegacion=self.centro, tipo_atencion="visitas", sub_atencion="visita_social")
		caso.full_clean()
		ajeno = Caso(identificacion="C-MAL", nombre="Cruce", delegacion=self.centro, tipo_atencion="visitas", sub_atencion="pgu")
		with self.assertRaises(ValidationError):
			ajeno.full_clean()
		self.client.post(reverse("institucional:subtipo_eliminar", args=[tipo.subtipos.get().pk]))
		self.client.post(reverse("institucional:tipo_eliminar", args=[tipo.pk]))
		self.assertFalse(TipoAtencion.objects.filter(codigo="visitas").exists())

	def test_trimestre_se_abre_cierra_y_fija_meta_por_funcionario(self):
		self._entrar(self.admin)
		alta = self.client.post(reverse("institucional:trimestre_crear"), {
			"nombre": "Trimestre propio", "fecha_inicio": "2026-10-01", "fecha_termino": "2026-12-31", "estado": "abierto",
		})
		self.assertRedirects(alta, reverse("institucional:trimestres"))
		periodo = Periodo.objects.get(nombre="Trimestre propio")
		Meta.objects.create(periodo=periodo, cargo=self.cargo, item=self.item, objetivo=40, ponderador=25)
		meta = self.client.post(reverse("institucional:trimestre_metas", args=[periodo.pk]), {
			"funcionario": str(self.funcionario.pk), "item": str(self.item.pk), "objetivo": "12", "ponderador": "15",
		})
		self.assertRedirects(meta, reverse("institucional:trimestre_metas", args=[periodo.pk]))
		personal = Meta.objects.get(periodo=periodo, funcionario=self.funcionario, item=self.item)
		self.assertEqual((personal.objetivo, personal.ponderador), (Decimal("12"), Decimal("15")))
		self.assertEqual(Meta.objects.get(periodo=periodo, cargo=self.cargo, funcionario__isnull=True).objetivo, 40)
		rechazo = self.client.post(reverse("institucional:trimestre_metas", args=[periodo.pk]), {
			"funcionario": str(self.delegado.pk), "item": str(self.item.pk), "objetivo": "5", "ponderador": "10",
		})
		self.assertEqual(rechazo.status_code, 200)
		self.assertFalse(Meta.objects.filter(funcionario=self.delegado).exists())
		self.client.post(reverse("institucional:trimestre_estado", args=[periodo.pk]), {"estado": "cerrado"})
		periodo.refresh_from_db()
		self.assertEqual(periodo.estado, "cerrado")
		self.client.post(reverse("institucional:trimestre_estado", args=[periodo.pk]), {"estado": "abierto"})
		periodo.refresh_from_db()
		self.assertEqual(periodo.estado, "abierto")

	def _actividad(self, funcionario, usuario, descripcion="Visita vecinal"):
		actividad = Actividad(
			periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS, descripcion=descripcion,
			accion="Entrevista", solicitante="Rosa Campos", telefono="+56 9 1111 2222",
		)
		return registrar_actividad(actividad, [TareaPreparatoria(descripcion="Acta de visita")], funcionario, usuario)

	def test_solicitud_de_mas_antecedentes(self):
		actividad = self._actividad(self.funcionario, self.funcionario_user)
		self._entrar(self.supervisor_user)
		pedido = self.client.post(reverse("servicios:actividad_revisar", args=[actividad.pk]), {
			"decision": "solicitar", "observacion": "Falta el acta firmada",
		})
		self.assertRedirects(pedido, reverse("servicios:aprobaciones"))
		actividad.refresh_from_db()
		self.assertEqual(actividad.estado, "antecedentes")
		self.assertEqual(actividad.observacion_revision, "Falta el acta firmada")
		self._entrar(self.funcionario_user)
		reenvio = self.client.post(reverse("servicios:actividad_editar", args=[actividad.pk]), {
			"fecha": "2026-06-17", "periodo": str(self.periodo.pk), "item": str(self.item.pk),
			"descripcion": "Visita con acta", "accion": "Entrevista", "solicitante": "Rosa Campos", "telefono": "+56 9 1111 2222",
		})
		self.assertRedirects(reenvio, reverse("servicios:actividad_detalle", args=[actividad.pk]))
		actividad.refresh_from_db()
		self.assertEqual(actividad.estado, "pendiente")

		tarea = actividad.tareas.get()
		tarea.realizada = True
		tarea.save(update_fields=["realizada"])
		self.client.post(reverse("servicios:actividad_detalle", args=[actividad.pk]), {"tarea": str(tarea.pk), "archivo": _png()})
		evidencia = actividad.evidencias.get()
		self._entrar(self.supervisor_user)
		self.client.post(reverse("servicios:evidencia_revisar", args=[evidencia.pk]), {"decision": "solicitar", "motivo": "La captura no se lee"})
		evidencia.refresh_from_db()
		self.assertEqual((evidencia.estado, evidencia.observacion), ("antecedentes", "La captura no se lee"))

		aprobada = self._actividad(self.funcionario, self.funcionario_user, "Ya cerrada")
		aprobada.tareas.update(realizada=True)
		from servicios.transacciones import revisar_actividad
		revisar_actividad(aprobada, "aprobar", self.supervisor_user)
		self.client.post(reverse("servicios:actividad_revisar", args=[aprobada.pk]), {"decision": "solicitar", "observacion": "No debe abrir"})
		aprobada.refresh_from_db()
		self.assertEqual(aprobada.estado, "validada")

	def test_todo_el_personal_de_la_delegacion_consulta_el_tubo(self):
		compromiso = Compromiso.objects.create(
			delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante="Junta Los Aromos",
			territorio="Centro", descripcion="Luminaria de la plaza", fecha_comprometida=HOY_PRUEBAS,
		)
		for usuario in (self.funcionario_user, self.companero_user, self.supervisor_user):
			self._entrar(usuario)
			pagina = self.client.get(reverse("servicios:agenda"))
			self.assertEqual(pagina.status_code, 200, usuario.username)
			self.assertContains(pagina, "Junta Los Aromos")
		self._entrar(self.supervisor_norte)
		self.assertNotContains(self.client.get(reverse("servicios:agenda")), "Junta Los Aromos")
		self._entrar(self.supervisor_user)
		self.assertEqual(self.client.get(reverse("servicios:compromiso_nuevo")).status_code, 403)
		self.assertEqual(compromiso.codigo[:3], "TB-")

	def test_solo_se_modifican_registros_propios_no_aprobados(self):
		actividad = self._actividad(self.funcionario, self.funcionario_user, "Registro propio")
		self._entrar(self.companero_user)
		ajena = self.client.post(reverse("servicios:actividad_editar", args=[actividad.pk]), {
			"fecha": "2026-06-17", "periodo": str(self.periodo.pk), "item": str(self.item.pk),
			"descripcion": "La cambió otro", "accion": "Entrevista", "solicitante": "Rosa Campos", "telefono": "+56 9 1111 2222",
		})
		self.assertEqual(ajena.status_code, 403)
		actividad.refresh_from_db()
		self.assertEqual(actividad.descripcion, "Registro propio")

		from servicios.transacciones import revisar_actividad
		actividad.tareas.update(realizada=True)
		revisar_actividad(actividad, "aprobar", self.supervisor_user)
		self._entrar(self.funcionario_user)
		cerrada = self.client.post(reverse("servicios:actividad_editar", args=[actividad.pk]), {
			"fecha": "2026-06-17", "periodo": str(self.periodo.pk), "item": str(self.item.pk),
			"descripcion": "Intento sobre aprobada", "accion": "Entrevista", "solicitante": "Rosa Campos", "telefono": "+56 9 1111 2222",
		})
		self.assertEqual(cerrada.status_code, 302)
		actividad.refresh_from_db()
		self.assertEqual(actividad.descripcion, "Registro propio")
		self.assertEqual(actividad.estado, "validada")

		compromiso = Compromiso.objects.create(
			delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante="Vecino propio",
			territorio="Centro", descripcion="Arreglo propio", fecha_comprometida=HOY_PRUEBAS,
		)
		datos = {
			"delegacion": str(self.centro.pk), "responsable": str(self.funcionario.pk), "origen": "Tubo",
			"solicitante": "Vecino propio", "territorio": "Centro", "descripcion": "Arreglo corregido",
			"fecha_comprometida": "2026-06-17", "estado": "pendiente", "observacion_cambio": "Pasa a pendiente",
		}
		self.assertRedirects(self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), datos), reverse("servicios:compromiso_detalle", args=[compromiso.pk]))
		compromiso.refresh_from_db()
		self.assertEqual(compromiso.descripcion, "Arreglo corregido")
		self._entrar(self.companero_user)
		datos["descripcion"] = "La cambió otro"
		self.assertEqual(self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), datos).status_code, 403)
		compromiso.refresh_from_db()
		self.assertEqual(compromiso.descripcion, "Arreglo corregido")
		compromiso.estado = "realizado"
		compromiso.save(update_fields=["estado"])
		self._entrar(self.funcionario_user)
		datos["descripcion"] = "No debe guardarse"
		self.client.post(reverse("servicios:compromiso_editar", args=[compromiso.pk]), datos)
		compromiso.refresh_from_db()
		self.assertEqual(compromiso.descripcion, "Arreglo corregido")
		self.assertEqual(compromiso.estado, "realizado")

	def test_graficos_de_carga_y_tendencia(self):
		for dia, texto in ((date(2026, 6, 3), "Semana anterior"), (HOY_PRUEBAS, "Semana actual")):
			Actividad.objects.create(
				funcionario=self.funcionario, periodo=self.periodo, item=self.item, fecha=dia,
				descripcion=texto, accion="Registro", solicitante="Rosa Campos", telefono="+56 9 1111 2222",
			)
		for dia in (date(2026, 6, 3), HOY_PRUEBAS):
			Compromiso.objects.create(
				delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante=f"Tubo {dia}",
				territorio="Centro", descripcion="Seguimiento", fecha_comprometida=dia,
			)
		self._entrar(self.admin)
		for nombre in ("servicios:panel_municipal", "servicios:resumen_matriz", "servicios:resumen_agenda"):
			pagina = self.client.get(reverse(nombre))
			self.assertEqual(pagina.status_code, 200, nombre)
			tendencia = pagina.context["grafico_tendencia"]
			self.assertFalse(tendencia["vacio"], nombre)
			valores = [marca["valor"] for marca in tendencia["marcas"]]
			self.assertGreater(len(valores), 1, nombre)
			self.assertEqual(sum(valores), 2, nombre)
			self.assertIn(0, valores, nombre)
			self.assertFalse(pagina.context["grafico_carga"]["vacio"], nombre)
			self.assertContains(pagina, "<polyline")
			self.assertContains(pagina, 'class="grafico"')

	def test_busqueda_dinamica_del_tubo_por_codigo_rut_o_nombre(self):
		compromiso = Compromiso(
			delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante="Rosa Campos",
			rut="12.345.678-5", telefono="+56 9 1111 2222", territorio="Centro", descripcion="Luminaria",
			fecha_comprometida=HOY_PRUEBAS,
		)
		compromiso.full_clean()
		compromiso.save()
		Compromiso.objects.create(
			delegacion=self.centro, responsable=self.companero, origen="Tubo", solicitante="Otra persona",
			territorio="Centro", descripcion="Otro tema", fecha_comprometida=HOY_PRUEBAS,
		)
		self._entrar(self.funcionario_user)
		for texto in (compromiso.codigo, "12345678", "Rosa Campos"):
			pagina = self.client.get(reverse("servicios:agenda"), {"q": texto})
			self.assertContains(pagina, "Rosa Campos")
			self.assertNotContains(pagina, "Otra persona")
		parcial = self.client.get(reverse("servicios:agenda"), {"q": compromiso.codigo, "parcial": "1"})
		self.assertContains(parcial, compromiso.codigo)
		self.assertNotContains(parcial, "Cerrar sesión")
		self.assertContains(self.client.get(reverse("servicios:agenda")), 'id="q-agenda"')
		script = Path(settings.BASE_DIR, "static/js/sgr.js").read_text(encoding="utf-8")
		self.assertIn('getElementById("q-agenda")', script)
		self.assertIn('addEventListener("input"', script)
		self.assertIn("parcial", script)

	def test_filtro_del_tubo_por_rango_de_fechas(self):
		Compromiso.objects.create(
			delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante="Dentro del rango",
			territorio="Centro", descripcion="Dentro", fecha_comprometida=date(2026, 6, 20),
		)
		Compromiso.objects.create(
			delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante="Fuera del rango",
			territorio="Centro", descripcion="Fuera", fecha_comprometida=date(2026, 6, 1),
		)
		self._entrar(self.funcionario_user)
		pagina = self.client.get(reverse("servicios:agenda"))
		self.assertContains(pagina, 'name="desde"')
		self.assertContains(pagina, 'name="hasta"')
		filtrada = self.client.get(reverse("servicios:agenda"), {"desde": "2026-06-10", "hasta": "2026-06-30"})
		self.assertContains(filtrada, "Dentro del rango")
		self.assertNotContains(filtrada, "Fuera del rango")

	def test_autocompletado_de_nombre_rut_y_telefono(self):
		compromiso = Compromiso(
			delegacion=self.centro, responsable=self.funcionario, origen="Tubo", solicitante="Rosa Campos",
			rut="12.345.678-5", telefono="+56 9 1111 2222", territorio="Centro", descripcion="Luminaria",
			fecha_comprometida=HOY_PRUEBAS,
		)
		compromiso.full_clean()
		compromiso.save()
		self.assertTrue(Vecino.objects.filter(delegacion=self.centro, rut="12345678-5").exists())
		self._entrar(self.funcionario_user)
		respuesta = self.client.get(reverse("servicios:autocompletar_persona"), {"q": "12345678"})
		datos = respuesta.json()["resultados"]
		self.assertEqual(datos[0]["nombre"], "Rosa Campos")
		self.assertEqual(datos[0]["rut"], "12345678-5")
		self.assertEqual(datos[0]["telefono"], "+56 9 1111 2222")
		formulario = self.client.get(reverse("servicios:actividad_nueva"))
		self.assertContains(formulario, 'data-autocompletar="solicitante"')
		self.assertContains(formulario, 'data-autocompletar="telefono"')
		script = Path(settings.BASE_DIR, "static/js/sgr.js").read_text(encoding="utf-8")
		self.assertIn("/servicios/personas/", script)

	def test_actividades_del_delegado_no_contabilizan(self):
		for funcionario in (self.delegado, self.funcionario):
			Actividad.objects.create(
				funcionario=funcionario, periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS,
				descripcion="Atención", accion="Registro", estado="validada",
				solicitante="Rosa Campos", telefono="+56 9 1111 2222",
			)
			Compromiso.objects.create(
				delegacion=self.centro, responsable=funcionario, origen="Tubo", solicitante="Solicitud",
				territorio="Centro", descripcion="Ingreso", fecha_comprometida=HOY_PRUEBAS, estado="realizado",
			)
		meta_delegado = Meta.objects.create(periodo=self.periodo, funcionario=self.delegado, item=self.item, objetivo=1, ponderador=10)
		meta_gestor = Meta.objects.create(periodo=self.periodo, funcionario=self.funcionario, item=self.item, objetivo=1, ponderador=10)
		self.assertEqual(meta_delegado.avance_aprobado, 0)
		self.assertEqual(meta_gestor.avance_aprobado, 1)
		tubo = ItemMedicion.objects.create(codigo="TUB1", nombre="Tasa tubo act1", tipo_medicion="tasa_tubo")
		tasa_delegado = Meta.objects.create(periodo=self.periodo, funcionario=self.delegado, item=tubo, objetivo=80, ponderador=10)
		tasa_gestor = Meta.objects.create(periodo=self.periodo, funcionario=self.funcionario, item=tubo, objetivo=80, ponderador=10)
		self.assertEqual(tasa_delegado.avance_aprobado, 0)
		self.assertEqual(tasa_gestor.avance_aprobado, 100)

	def test_registro_sin_nombre_o_telefono_no_puntua(self):
		meta = Meta.objects.create(periodo=self.periodo, funcionario=self.funcionario, item=self.item, objetivo=1, ponderador=100)
		Actividad.objects.create(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS,
			descripcion="Sin teléfono", accion="Registro", estado="validada", solicitante="Rosa Campos", telefono="",
		)
		self.assertEqual(meta.avance_aprobado, 0)
		Actividad.objects.create(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS,
			descripcion="Sin nombre", accion="Registro", estado="validada", solicitante="", telefono="+56 9 1111 2222",
		)
		self.assertEqual(meta.avance_aprobado, 0)
		sin_nombre = Actividad(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS,
			descripcion="Completo", accion="Registro", solicitante="", telefono="+56 9 1111 2222",
		)
		with self.assertRaises(ValidationError):
			sin_nombre.full_clean()
		sin_telefono = Actividad(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS,
			descripcion="Completo", accion="Registro", solicitante="Rosa Campos", telefono="",
		)
		sin_telefono.full_clean()
		Actividad.objects.create(
			funcionario=self.funcionario, periodo=self.periodo, item=self.item, fecha=HOY_PRUEBAS,
			descripcion="Completo", accion="Registro", estado="validada",
			solicitante="Rosa Campos", telefono="+56 9 1111 2222",
		)
		self.assertEqual(meta.avance_aprobado, 1)

	def test_felicitacion_solo_puntua_con_respaldo_formal(self):
		self._entrar(self.supervisor_user)
		datos = {
			"tipo": "felicitacion", "funcionario": str(self.funcionario.pk), "periodo": str(self.periodo.pk),
			"fecha": "2026-06-17", "usuario_nombre": "Rosa Campos", "situacion": "Agradece la visita.", "medio": "correo",
		}
		sin_archivo = self.client.post(reverse("oficina:reconocimiento_crear"), datos)
		self.assertEqual(sin_archivo.status_code, 200)
		self.assertEqual(Reconocimiento.objects.count(), 0)
		self.assertContains(sin_archivo, "respaldo")
		archivo = SimpleUploadedFile("respaldo.pdf", b"%PDF-1.4 respaldo", content_type="application/pdf")
		con_archivo = self.client.post(reverse("oficina:reconocimiento_crear"), {**datos, "respaldo": archivo})
		self.assertRedirects(con_archivo, reverse("oficina:reconocimientos"))
		registro = Reconocimiento.objects.get()
		self.assertTrue(registro.respaldo)
		self.assertEqual(resumen_funcionario(self.funcionario, self.periodo, HOY_PRUEBAS)["bono"], 10)
		Reconocimiento.objects.create(
			tipo="felicitacion", funcionario=self.funcionario, periodo=self.periodo, fecha=HOY_PRUEBAS,
			usuario_nombre="Sin papel", situacion="No acredita", medio="correo", registrado_por=self.supervisor_user,
		)
		self.assertEqual(resumen_funcionario(self.funcionario, self.periodo, HOY_PRUEBAS)["bono"], 10)
		self.client.post(reverse("oficina:reconocimiento_crear"), {**datos, "tipo": "reclamo", "situacion": "Mala atención."})
		self.assertEqual(Reconocimiento.objects.filter(tipo="reclamo").count(), 1)
		self.client.logout()
		self.assertEqual(self.client.get(registro.respaldo.url).status_code, 302)

	def test_ausencia_ajusta_conteo_tasa_y_emergencia(self):
		from oficina.models import AjusteMeta, Ausencia

		conteo = self.item
		tasa = ItemMedicion.objects.create(codigo="TUBA", nombre="Tasa ausencia", tipo_medicion="tasa_tubo")
		emergencia = ItemMedicion.objects.create(codigo="EMEA", nombre="Emergencia ausencia", tipo_medicion="emergencia")
		sin_puntaje = ItemMedicion.objects.create(codigo="SINA", nombre="Sin puntaje ausencia", tipo_medicion="sin_puntaje")
		for item, objetivo in ((conteo, 40), (tasa, 80), (emergencia, 1), (sin_puntaje, 10)):
			Meta.objects.create(periodo=self.periodo, cargo=self.cargo, item=item, objetivo=objetivo, ponderador=10)
		registrar_ausencia(
			Ausencia(funcionario=self.funcionario, periodo=self.periodo, fecha_inicio=date(2026, 6, 1), fecha_termino=date(2026, 6, 2), motivo="compensatorio"),
			self.admin,
		)
		personales = dict(Meta.objects.filter(funcionario=self.funcionario).values_list("item__codigo", "objetivo"))
		self.assertLess(personales["ACT1"], 40)
		self.assertLess(personales["TUBA"], 80)
		self.assertLess(personales["EMEA"], 1)
		self.assertNotIn("SINA", personales)
		self.assertEqual(AjusteMeta.objects.filter(ausencia__funcionario=self.funcionario).count(), 3)
		self.assertEqual(Meta.objects.get(cargo=self.cargo, item=sin_puntaje, funcionario__isnull=True).objetivo, 10)
