from datetime import date, timedelta
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from institucional.models import Cargo, Delegacion, Funcionario
from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, asignar_grupo
from oficina.models import Carta
from servicios.models import Actividad, Auditoria, ItemMedicion, Periodo, TareaPreparatoria
from servicios.tests import HOY_PRUEBAS, fijar_hoy

CLAVE = "Serena-pruebas-2026"


def cuenta(username, grupo, email=""):
    usuario = get_user_model().objects.create_user(username=username, password=CLAVE, email=email, first_name=username.title())
    if grupo:
        asignar_grupo(usuario, grupo)
    return usuario


class BaseAPI(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.centro = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="Centro", enfoque="-")
        self.norte = Delegacion.objects.create(nombre="Norte", slug="norte", territorio="Norte", enfoque="-")
        self.cargo = Cargo.objects.create(nombre="Territorial", perfil="Administrativo")
        self.cargo_delegado = Cargo.objects.create(nombre="Delegado", perfil="Supervisor")
        self.admin = cuenta("admin", GRUPO_ADMINISTRADOR, "admin@laserena.cl")
        self.supervisor = cuenta("delegada", GRUPO_SUPERVISOR, "delegada.privado@gmail.com")
        self.supervisor_norte = cuenta("delegado-norte", GRUPO_SUPERVISOR)
        self.administrativo = cuenta("funcionaria", GRUPO_ADMINISTRATIVO, "ana.privado@gmail.com")
        self.administrativo_2 = cuenta("funcionario2", GRUPO_ADMINISTRATIVO)
        self.ficha_delegada = Funcionario.objects.create(usuario=self.supervisor, identificador="S-1", nombre_completo="Delegada Centro", correo="delegada.privado@gmail.com", delegacion=self.centro, cargo=self.cargo_delegado)
        Funcionario.objects.create(usuario=self.supervisor_norte, identificador="S-2", nombre_completo="Delegado Norte", delegacion=self.norte, cargo=self.cargo_delegado)
        self.funcionario = Funcionario.objects.create(usuario=self.administrativo, identificador="F-1", nombre_completo="Ana Funcionaria", correo="ana.privado@gmail.com", delegacion=self.centro, cargo=self.cargo)
        self.funcionario_2 = Funcionario.objects.create(usuario=self.administrativo_2, identificador="F-2", nombre_completo="Bruno Funcionario", delegacion=self.centro, cargo=self.cargo)

    def autenticar(self, usuario):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(usuario).access_token}")

    def assertError(self, respuesta, codigo, tipo=None):
        self.assertEqual(respuesta.status_code, codigo, respuesta.content)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        cuerpo = respuesta.json()["error"]
        self.assertEqual(cuerpo["codigo"], codigo)
        self.assertTrue(cuerpo["mensaje"])
        if tipo:
            self.assertEqual(cuerpo["tipo"], tipo)
        return cuerpo


class JWTTest(BaseAPI):
    def test_token_valido_entrega_access_refresh_y_perfil(self):
        respuesta = self.client.post("/api/token/", {"username": "admin", "password": CLAVE}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(set(datos), {"access", "refresh", "perfil"})
        self.assertEqual(datos["perfil"], GRUPO_ADMINISTRADOR)
        payload = AccessToken(datos["access"]).payload
        self.assertEqual(payload["perfil"], GRUPO_ADMINISTRADOR)
        self.assertNotIn("email", payload)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        self.assertEqual(self.client.get("/api/yo/").json()["usuario"], "admin")

    def test_credenciales_invalidas_responden_401_en_json(self):
        respuesta = self.client.post("/api/token/", {"username": "admin", "password": "otra"}, format="json")
        self.assertError(respuesta, 401, "no_autenticado")

    def test_cuenta_sin_perfil_sgr_no_recibe_token(self):
        cuenta("sin-perfil", None)
        respuesta = self.client.post("/api/token/", {"username": "sin-perfil", "password": CLAVE}, format="json")
        self.assertError(respuesta, 401)

    def test_faltan_credenciales_responde_400(self):
        cuerpo = self.assertError(self.client.post("/api/token/", {"username": "admin"}, format="json"), 400, "solicitud_invalida")
        self.assertIn("password", cuerpo["detalle"])

    def test_endpoints_protegidos_exigen_token(self):
        for ruta in ("/api/yo/", "/api/usuarios/", "/api/cartas/", "/api/actividades/", "/api/cartas/exportar/excel/"):
            self.assertError(self.client.get(ruta), 401, "no_autenticado")

    def test_token_invalido_o_vencido_responde_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer no-es-un-jwt")
        self.assertError(self.client.get("/api/cartas/"), 401)
        vencido = AccessToken.for_user(self.admin)
        vencido.set_exp(lifetime=-timedelta(minutes=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {vencido}")
        self.assertError(self.client.get("/api/cartas/"), 401)

    def test_refresh_no_sirve_como_access(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.admin)}")
        self.assertError(self.client.get("/api/cartas/"), 401)

    def test_refresh_rota_y_el_anterior_queda_en_lista_negra(self):
        tokens = self.client.post("/api/token/", {"username": "delegada", "password": CLAVE}, format="json").json()
        renovado = self.client.post("/api/token/renovar/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(renovado.status_code, 200)
        self.assertIn("access", renovado.json())
        self.assertNotEqual(renovado.json()["refresh"], tokens["refresh"])
        self.assertError(self.client.post("/api/token/renovar/", {"refresh": tokens["refresh"]}, format="json"), 401)

    def test_cerrar_sesion_revoca_el_refresh(self):
        refresh = self.client.post("/api/token/", {"username": "funcionaria", "password": CLAVE}, format="json").json()["refresh"]
        self.assertEqual(self.client.post("/api/token/revocar/", {"refresh": refresh}, format="json").status_code, 200)
        self.assertError(self.client.post("/api/token/renovar/", {"refresh": refresh}, format="json"), 401)

    def test_verificar_token(self):
        access = str(RefreshToken.for_user(self.admin).access_token)
        self.assertEqual(self.client.post("/api/token/verificar/", {"token": access}, format="json").status_code, 200)
        self.assertError(self.client.post("/api/token/verificar/", {"token": access + "x"}, format="json"), 401)

    def test_limita_los_intentos_de_obtener_token(self):
        with mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"token": "3/min"}):
            for _ in range(3):
                self.client.post("/api/token/", {"username": "admin", "password": "mala"}, format="json")
            self.assertError(self.client.post("/api/token/", {"username": "admin", "password": CLAVE}, format="json"), 429, "demasiadas_solicitudes")

    def test_cuenta_desactivada_pierde_el_acceso(self):
        self.autenticar(self.supervisor)
        self.supervisor.is_active = False
        self.supervisor.save()
        self.assertError(self.client.get("/api/cartas/"), 401)


class DocumentacionYErroresTest(BaseAPI):
    def test_esquema_openapi_documenta_jwt_y_endpoints(self):
        respuesta = self.client.get("/api/esquema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(respuesta.status_code, 200)
        esquema = respuesta.json()
        self.assertEqual(esquema["components"]["securitySchemes"]["BearerAuth"]["scheme"], "bearer")
        for ruta in ("/api/token/", "/api/token/renovar/", "/api/usuarios/{id}/", "/api/cartas/{id}/", "/api/actividades/", "/api/cartas/exportar/{formato}/"):
            self.assertIn(ruta, esquema["paths"])
        self.assertEqual(set(esquema["paths"]["/api/cartas/{id}/"]), {"get", "put", "delete"})
        self.assertFalse(esquema["paths"]["/api/token/"]["post"].get("security"))
        self.assertEqual(esquema["paths"]["/api/cartas/"]["get"]["security"], [{"BearerAuth": []}])
        self.assertEqual(set(esquema["components"]["securitySchemes"]), {"BearerAuth"})
        self.assertIn("examples", str(esquema["paths"]["/api/cartas/"]["post"]))

    def test_swagger_y_redoc_disponibles(self):
        swagger = self.client.get("/api/swagger/")
        self.assertContains(swagger, "swagger-ui")
        self.assertNotContains(swagger, "cdn.jsdelivr")
        self.assertEqual(self.client.get("/api/swagger/?script=").status_code, 200)
        self.assertEqual(self.client.get("/api/redoc/").status_code, 200)

    def test_ruta_inexistente_responde_404_en_json(self):
        self.autenticar(self.admin)
        self.assertError(self.client.get("/api/no-existe/"), 404, "no_encontrado")

    def test_metodo_no_permitido_405(self):
        self.autenticar(self.admin)
        self.assertError(self.client.patch("/api/cartas/", {}, format="json"), 405, "metodo_no_permitido")

    def test_cuerpo_que_no_es_json_responde_415(self):
        self.autenticar(self.admin)
        self.assertError(self.client.post("/api/cartas/", {"remitente": "X"}), 415)

    def test_error_interno_responde_500_sin_exponer_la_traza(self):
        self.autenticar(self.admin)
        with mock.patch("api.views._cartas_visibles", side_effect=RuntimeError("detalle interno de la base")):
            respuesta = self.client.get("/api/cartas/")
        self.assertError(respuesta, 500, "error_interno")
        self.assertNotIn("detalle interno", respuesta.content.decode())

    def test_respuestas_de_la_api_no_se_guardan_en_cache(self):
        self.autenticar(self.admin)
        self.assertEqual(self.client.get("/api/cartas/")["Cache-Control"], "no-store, private")


class CartasAPITest(BaseAPI):
    def datos(self, **extra):
        datos = {"fecha_ingreso": "2026-06-10", "tipo": "solicitud", "remitente": "JJVV Las Rosas", "contacto_remitente": "+56 9 1111 2222",
                 "asunto": "Poda de árboles", "estado": "ingresada", "delegacion": self.centro.pk}
        datos.update(extra)
        return datos

    def test_admin_crud_completo(self):
        self.autenticar(self.admin)
        creada = self.client.post("/api/cartas/", self.datos(), format="json")
        self.assertEqual(creada.status_code, 201, creada.content)
        carta = creada.json()
        self.assertEqual(carta["folio"], "OP-2026-0001")
        self.assertEqual(carta["contacto_remitente"], "+56 9 1111 2222")
        self.assertEqual(carta["registrada_por"], "admin")

        listado = self.client.get("/api/cartas/", {"q": "poda"}).json()
        self.assertEqual(listado["total"], 1)
        self.assertEqual(listado["resultados"][0]["folio"], "OP-2026-0001")
        self.assertEqual(self.client.get(f"/api/cartas/{carta['id']}/").status_code, 200)

        editada = self.client.put(f"/api/cartas/{carta['id']}/", self.datos(estado="derivada", derivada_a=self.funcionario.pk), format="json")
        self.assertEqual(editada.status_code, 200, editada.content)
        self.assertEqual(editada.json()["derivada_a_nombre"], "Ana Funcionaria")

        eliminada = self.client.delete(f"/api/cartas/{carta['id']}/")
        self.assertEqual(eliminada.status_code, 200)
        self.assertIn("OP-2026-0001", eliminada.json()["mensaje"])
        self.assertError(self.client.get(f"/api/cartas/{carta['id']}/"), 404, "no_encontrado")

    def test_validaciones_responden_400_con_detalle_por_campo(self):
        self.autenticar(self.admin)
        cuerpo = self.assertError(self.client.post("/api/cartas/", self.datos(remitente="", delegacion=None), format="json"), 400, "solicitud_invalida")
        self.assertIn("remitente", cuerpo["detalle"])
        self.assertIn("delegacion", cuerpo["detalle"])
        cuerpo = self.assertError(self.client.post("/api/cartas/", self.datos(estado="derivada"), format="json"), 400)
        self.assertIn("Indica a quién se deriva", str(cuerpo["detalle"]))
        cuerpo = self.assertError(self.client.post("/api/cartas/", self.datos(estado="no-existe"), format="json"), 400)
        self.assertIn("estado", cuerpo["detalle"])
        self.assertFalse(Carta.objects.exists())

    def test_supervisor_no_ve_datos_sensibles_y_queda_en_su_delegacion(self):
        self.autenticar(self.supervisor)
        creada = self.client.post("/api/cartas/", self.datos(delegacion=self.norte.pk), format="json")
        self.assertEqual(creada.status_code, 201, creada.content)
        self.assertNotIn("contacto_remitente", creada.json())
        self.assertNotIn("registrada_por", creada.json())
        carta = Carta.objects.get()
        self.assertEqual(carta.delegacion, self.centro)
        self.assertEqual(carta.contacto_remitente, "+56 9 1111 2222")
        self.assertNotIn("contacto_remitente", self.client.get("/api/cartas/").json()["resultados"][0])

        self.autenticar(self.supervisor_norte)
        self.assertError(self.client.get(f"/api/cartas/{carta.pk}/"), 404)
        self.assertEqual(self.client.get("/api/cartas/").json()["total"], 0)

    def test_administrativo_solo_da_seguimiento_a_sus_cartas(self):
        propia = Carta.objects.create(fecha_ingreso=date(2026, 6, 10), remitente="A", asunto="Uno", delegacion=self.centro, estado="derivada", derivada_a=self.funcionario, registrada_por=self.admin)
        ajena = Carta.objects.create(remitente="B", asunto="Dos", delegacion=self.centro, registrada_por=self.admin)
        self.autenticar(self.administrativo)
        self.assertError(self.client.post("/api/cartas/", self.datos(), format="json"), 403, "sin_permiso")
        self.assertError(self.client.delete(f"/api/cartas/{propia.pk}/"), 403)
        self.assertError(self.client.get(f"/api/cartas/{ajena.pk}/"), 404)
        self.assertError(self.client.put(f"/api/cartas/{propia.pk}/", {"estado": "respondida"}, format="json"), 400)
        respuesta = self.client.put(f"/api/cartas/{propia.pk}/", {"estado": "respondida", "respuesta": "Listo", "fecha_respuesta": "2026-06-12", "remitente": "Cambiado"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        propia.refresh_from_db()
        self.assertEqual((propia.estado, propia.remitente, propia.resolucion), ("respondida", "A", "finalizada"))


class UsuariosAPITest(BaseAPI):
    def datos(self, **extra):
        datos = {"usuario": "paula", "nombres": "Paula", "apellidos": "Rojas", "correo": "paula@laserena.cl", "perfil": GRUPO_ADMINISTRATIVO,
                 "identificador": "F-9", "delegacion": self.norte.pk, "cargo": self.cargo.pk, "clave": "Territorio-Norte-2026", "clave_confirmacion": "Territorio-Norte-2026"}
        datos.update(extra)
        return datos

    def test_admin_crea_edita_y_elimina_sin_exponer_la_clave(self):
        self.autenticar(self.admin)
        creada = self.client.post("/api/usuarios/", self.datos(), format="json")
        self.assertEqual(creada.status_code, 201, creada.content)
        cuerpo = creada.content.decode()
        for oculto in ("password", "clave", "Territorio-Norte-2026", "pbkdf2"):
            self.assertNotIn(oculto, cuerpo)
        usuario = creada.json()
        self.assertEqual(usuario["perfil"], GRUPO_ADMINISTRATIVO)
        self.assertEqual(usuario["funcionario"]["delegacion"], "Norte")
        token = self.client.post("/api/token/", {"username": "paula", "password": "Territorio-Norte-2026"}, format="json")
        self.assertEqual(token.status_code, 200)

        editada = self.client.put(f"/api/usuarios/{usuario['id']}/", self.datos(nombres="Paulina", clave="", clave_confirmacion=""), format="json")
        self.assertEqual(editada.status_code, 200, editada.content)
        self.assertEqual(editada.json()["funcionario"]["nombre_completo"], "Paulina Rojas")
        self.assertTrue(get_user_model().objects.get(username="paula").check_password("Territorio-Norte-2026"))

        self.assertEqual(self.client.delete(f"/api/usuarios/{usuario['id']}/").status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="paula").exists())

    def test_reglas_del_mantenedor_web_se_aplican(self):
        self.autenticar(self.admin)
        cuerpo = self.assertError(self.client.post("/api/usuarios/", self.datos(clave="12345", clave_confirmacion="12345"), format="json"), 400)
        self.assertIn("clave", cuerpo["detalle"])
        cuerpo = self.assertError(self.client.post("/api/usuarios/", self.datos(perfil=GRUPO_SUPERVISOR), format="json"), 400)
        self.assertIn("perfil", cuerpo["detalle"])
        cuerpo = self.assertError(self.client.post("/api/usuarios/", self.datos(usuario="FUNCIONARIA"), format="json"), 400)
        self.assertIn("usuario", cuerpo["detalle"])
        self.assertError(self.client.delete(f"/api/usuarios/{self.admin.pk}/"), 400)

    def test_perfil_usuario_solo_ve_campos_publicos_de_su_delegacion(self):
        self.autenticar(self.supervisor)
        listado = self.client.get("/api/usuarios/").json()
        self.assertEqual({u["nombre"] for u in listado["resultados"]}, {"Delegada Centro", "Ana Funcionaria", "Bruno Funcionario"})
        for usuario in listado["resultados"]:
            self.assertEqual(set(usuario), {"id", "nombre", "perfil", "cargo", "delegacion"})
        self.assertNotIn("privado@gmail.com", self.client.get(f"/api/usuarios/{self.administrativo.pk}/").content.decode())
        self.assertError(self.client.get(f"/api/usuarios/{self.admin.pk}/"), 404)

    def test_perfil_usuario_no_crea_ni_modifica(self):
        for cuenta_usuario in (self.supervisor, self.administrativo):
            self.autenticar(cuenta_usuario)
            self.assertError(self.client.post("/api/usuarios/", self.datos(), format="json"), 403, "sin_permiso")
            self.assertError(self.client.put(f"/api/usuarios/{self.administrativo.pk}/", self.datos(), format="json"), 403)
            self.assertError(self.client.delete(f"/api/usuarios/{self.administrativo_2.pk}/"), 403)

    def test_admin_ve_todos_los_campos(self):
        self.autenticar(self.admin)
        detalle = self.client.get(f"/api/usuarios/{self.administrativo.pk}/").json()
        self.assertEqual(detalle["correo"], "ana.privado@gmail.com")
        self.assertEqual(set(detalle), {"id", "usuario", "nombres", "apellidos", "correo", "perfil", "activo", "ultimo_acceso", "fecha_creacion", "funcionario"})
        self.assertEqual(detalle["funcionario"]["identificador"], "F-1")
        self.assertNotIn("password", detalle)


class ActividadesAPITest(BaseAPI):
    def setUp(self):
        super().setUp()
        fijar_hoy(self)
        self.periodo = Periodo.objects.create(nombre="Período 2026", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))
        self.item = ItemMedicion.objects.create(codigo="ACT-API", nombre="Talleres y actividades")

    def datos(self, **extra):
        datos = {"fecha": HOY_PRUEBAS.isoformat(), "periodo": self.periodo.pk, "item": self.item.pk, "descripcion": "Taller de huertos",
                 "accion": "Se inscribieron 25 vecinos", "solicitante": "Junta de vecinos Villa Alegre", "contacto": "María González", "telefono": "+56 9 1234 5678",
                 "tareas": [{"descripcion": "Gestión de sillas"}, {"descripcion": "Gestión de afiches"}]}
        datos.update(extra)
        return datos

    def registrar(self, usuario=None, **extra):
        self.autenticar(usuario or self.administrativo)
        respuesta = self.client.post("/api/actividades/", self.datos(**extra), format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return respuesta.json()

    def test_registrar_actividad_guarda_tareas_y_auditoria(self):
        actividad = self.registrar()
        self.assertEqual(actividad["estado"], "pendiente")
        self.assertEqual(actividad["funcionario_nombre"], "Ana Funcionaria")
        self.assertEqual(len(actividad["tareas"]), 2)
        self.assertEqual({tarea["descripcion"] for tarea in actividad["tareas"]}, {"Gestión de sillas", "Gestión de afiches"})
        self.assertTrue(all("tipo" not in tarea for tarea in actividad["tareas"]))
        self.assertEqual(actividad["solicitante"], "Junta de vecinos Villa Alegre")
        self.assertNotIn("telefono", actividad)
        self.assertNotIn("contacto", actividad)
        guardada = Actividad.objects.get()
        self.assertEqual(guardada.telefono, "+56 9 1234 5678")
        self.assertTrue(Auditoria.objects.filter(accion="registrar_actividad", identificador=str(guardada.codigo_evidencia)).exists())

    def test_solo_el_administrador_ve_contacto_y_telefono(self):
        actividad = self.registrar()
        self.autenticar(self.supervisor)
        self.assertNotIn("telefono", self.client.get(f"/api/actividades/{actividad['id']}/").json())
        self.autenticar(self.admin)
        detalle = self.client.get(f"/api/actividades/{actividad['id']}/").json()
        self.assertEqual((detalle["contacto"], detalle["telefono"]), ("María González", "+56 9 1234 5678"))

    def test_admin_registra_indicando_funcionario(self):
        self.autenticar(self.admin)
        cuerpo = self.assertError(self.client.post("/api/actividades/", self.datos(), format="json"), 400)
        self.assertIn("funcionario", cuerpo["detalle"])
        actividad = self.registrar(self.admin, funcionario=self.funcionario_2.pk)
        self.assertEqual(actividad["funcionario"], self.funcionario_2.pk)

    def test_si_una_regla_falla_no_queda_nada_guardado(self):
        self.autenticar(self.administrativo)
        manana = (HOY_PRUEBAS + timedelta(days=1)).isoformat()
        cuerpo = self.assertError(self.client.post("/api/actividades/", self.datos(fecha=manana), format="json"), 400)
        self.assertIn("fecha futura", str(cuerpo["detalle"]))
        cuerpo = self.assertError(self.client.post("/api/actividades/", self.datos(tareas=[]), format="json"), 400)
        self.assertIn("tareas", cuerpo["detalle"])
        cuerpo = self.assertError(self.client.post("/api/actividades/", self.datos(telefono="abc"), format="json"), 400)
        self.assertIn("telefono", cuerpo["detalle"])
        self.assertFalse(Actividad.objects.exists())
        self.assertFalse(TareaPreparatoria.objects.exists())

    def test_la_tarea_es_texto_libre_sin_tipo(self):
        self.autenticar(self.administrativo)
        cuerpo = self.assertError(
            self.client.post("/api/actividades/", self.datos(tareas=[{"descripcion": "  "}]), format="json"),
            400,
        )
        self.assertIn("Gestión de sillas", str(cuerpo))
        actividad = self.registrar(tareas=[{"tipo": "sillas", "descripcion": "Gestión de sillas"}])
        self.assertEqual(actividad["tareas"][0]["descripcion"], "Gestión de sillas")
        self.assertNotIn("tipo", actividad["tareas"][0])
        self.assertFalse(TareaPreparatoria.objects.exclude(descripcion="Gestión de sillas").exists())

    def test_cupo_diario_de_siete_actividades(self):
        for _ in range(7):
            self.registrar()
        cuerpo = self.assertError(self.client.post("/api/actividades/", self.datos(), format="json"), 400)
        self.assertIn("máximo diario", str(cuerpo["detalle"]))

    def test_flujo_completo_modificar_tareas_y_aprobacion(self):
        actividad = self.registrar()
        url = f"/api/actividades/{actividad['id']}/"
        editada = self.client.put(url, {k: v for k, v in self.datos(descripcion="Taller de compostaje").items() if k != "tareas"}, format="json")
        self.assertEqual(editada.status_code, 200, editada.content)
        self.assertEqual(editada.json()["descripcion"], "Taller de compostaje")

        self.autenticar(self.supervisor)
        self.assertError(self.client.post("/api/actividades/", self.datos(), format="json"), 403)
        cuerpo = self.assertError(self.client.post(url + "revision/", {"decision": "aprobar"}, format="json"), 400)
        self.assertIn("tareas preparatorias sin realizar", cuerpo["mensaje"])

        self.autenticar(self.administrativo)
        for tarea in actividad["tareas"]:
            marcada = self.client.put(f"{url}tareas/{tarea['id']}/", {"realizada": True}, format="json")
            self.assertTrue(marcada.json()["realizada"])
        self.assertError(self.client.post(url + "revision/", {"decision": "aprobar"}, format="json"), 403)

        self.autenticar(self.supervisor)
        aprobada = self.client.post(url + "revision/", {"decision": "aprobar"}, format="json")
        self.assertEqual(aprobada.json()["estado"], "validada")

        self.autenticar(self.administrativo)
        self.assertError(self.client.delete(url), 400)

    def test_anular_actividad_con_delete(self):
        actividad = self.registrar()
        anulada = self.client.delete(f"/api/actividades/{actividad['id']}/")
        self.assertEqual(anulada.status_code, 200)
        self.assertEqual(anulada.json()["estado"], "anulada")
        self.assertTrue(Actividad.objects.filter(pk=actividad["id"]).exists())
        self.assertError(self.client.delete(f"/api/actividades/{actividad['id']}/"), 400)

    def test_administrativo_no_modifica_actividades_ajenas(self):
        actividad = self.registrar()
        self.autenticar(self.administrativo_2)
        self.assertEqual(self.client.get(f"/api/actividades/{actividad['id']}/").status_code, 200)
        self.assertError(self.client.delete(f"/api/actividades/{actividad['id']}/"), 403)
        self.autenticar(self.supervisor_norte)
        self.assertError(self.client.get(f"/api/actividades/{actividad['id']}/"), 404)


class ExportacionesTest(BaseAPI):
    def setUp(self):
        super().setUp()
        Carta.objects.create(remitente="JJVV Las Rosas", contacto_remitente="+56 9 1111 2222", asunto="Poda", delegacion=self.centro, registrada_por=self.admin)
        Carta.objects.create(remitente="Club Norte", contacto_remitente="club@norte.cl", asunto="Sede", delegacion=self.norte, registrada_por=self.admin)

    def hoja(self, respuesta):
        self.assertEqual(respuesta.status_code, 200, respuesta.content[:300])
        self.assertEqual(respuesta["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment;", respuesta["Content-Disposition"])
        hoja = load_workbook(BytesIO(respuesta.content)).active
        filas = [list(fila) for fila in hoja.iter_rows(values_only=True)]
        indice = next(i for i, fila in enumerate(filas) if fila and fila[0] in ("Folio", "Código"))
        self.assertTrue(hoja.cell(row=indice + 1, column=1).font.bold)
        self.assertEqual(hoja.freeze_panes, f"A{indice + 2}")
        return filas[indice], [fila for fila in filas[indice + 1:] if any(fila)]

    def test_excel_del_administrador_incluye_columnas_sensibles(self):
        self.autenticar(self.admin)
        encabezado, filas = self.hoja(self.client.get("/api/cartas/exportar/excel/"))
        self.assertIn("Contacto remitente", encabezado)
        self.assertEqual(len(filas), 2)
        self.assertIn("+56 9 1111 2222", sum(filas, []))

    def test_excel_del_perfil_usuario_omite_datos_sensibles_y_respeta_el_ambito(self):
        self.autenticar(self.supervisor)
        encabezado, filas = self.hoja(self.client.get("/api/cartas/exportar/excel/"))
        self.assertNotIn("Contacto remitente", encabezado)
        self.assertNotIn("Registrada por", encabezado)
        self.assertEqual(len(filas), 1)
        self.assertNotIn("+56 9 1111 2222", sum(filas, []))

    def test_pdf_de_cartas_y_actividades(self):
        self.autenticar(self.admin)
        for ruta in ("/api/cartas/exportar/pdf/", "/api/actividades/exportar/pdf/"):
            respuesta = self.client.get(ruta, HTTP_ACCEPT="application/pdf")
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta["Content-Type"], "application/pdf")
            self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_excel_de_actividades_por_perfil(self):
        fijar_hoy(self)
        periodo = Periodo.objects.create(nombre="P", fecha_inicio=date(2026, 1, 1), fecha_termino=date(2026, 12, 31))
        item = ItemMedicion.objects.create(codigo="X-1", nombre="Atención")
        actividad = Actividad.objects.create(funcionario=self.funcionario, periodo=periodo, item=item, fecha=HOY_PRUEBAS, descripcion="Atención", accion="Orientación", telefono="+56 9 5555 6666")
        TareaPreparatoria.objects.create(actividad=actividad, tipo="otra", descripcion="Gestión de sillas")
        self.autenticar(self.admin)
        encabezado, filas = self.hoja(self.client.get("/api/actividades/exportar/excel/"))
        self.assertIn("Teléfono", encabezado)
        self.assertIn("0/1", filas[0])
        self.autenticar(self.administrativo)
        encabezado, _ = self.hoja(self.client.get("/api/actividades/exportar/excel/"))
        self.assertNotIn("Teléfono", encabezado)

    def test_errores_de_exportacion_salen_en_json(self):
        self.assertError(self.client.get("/api/cartas/exportar/pdf/", HTTP_ACCEPT="application/pdf"), 401)
        self.autenticar(self.admin)
        self.assertError(self.client.get("/api/cartas/exportar/word/"), 404)

    def test_exportar_desde_la_web_con_sesion(self):
        self.client.force_login(self.supervisor)
        _, filas = self.hoja(self.client.get(reverse("oficina:cartas_exportar", args=["excel"])))
        self.assertEqual(len(filas), 1)
        self.assertContains(self.client.get(reverse("oficina:cartas")), reverse("oficina:cartas_exportar", args=["pdf"]))
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("servicios:actividades_exportar", args=["pdf"]))
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("oficina:cartas_exportar", args=["pdf"])).status_code, 302)


class APIEnEspanolTest(BaseAPI):
    def test_rutas_en_espanol_y_rutas_anteriores_compatibles(self):
        esquema = self.client.get("/api/esquema/", HTTP_ACCEPT="application/vnd.oai.openapi+json").json()
        for ruta in ("/api/token/renovar/", "/api/token/verificar/", "/api/token/revocar/"):
            self.assertIn(ruta, esquema["paths"])
        for ruta in ("/api/token/refresh/", "/api/token/verify/", "/api/token/blacklist/", "/api/schema/"):
            self.assertNotIn(ruta, esquema["paths"])
        refresh = self.client.post("/api/token/", {"username": "admin", "password": CLAVE}, format="json").json()["refresh"]
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": refresh}, format="json").status_code, 200)
        self.assertEqual(self.client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json").status_code, 200)

    def test_mensajes_de_django_drf_y_simplejwt_en_espanol(self):
        cuerpo = self.assertError(self.client.get("/api/cartas/"), 401)
        self.assertEqual(cuerpo["mensaje"], "Las credenciales de autenticación no se proveyeron.")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer no-es-un-jwt")
        cuerpo = self.assertError(self.client.get("/api/cartas/"), 401)
        self.assertNotIn("Given token", cuerpo["mensaje"])
        self.assertIn("token", cuerpo["mensaje"].lower())
        self.client.credentials()
        cuerpo = self.assertError(self.client.post("/api/token/", {"username": "admin", "password": "otra"}, format="json"), 401)
        self.assertNotIn("No active account", cuerpo["mensaje"])
        cuerpo = self.assertError(self.client.post("/api/token/renovar/", {"refresh": "x"}, format="json"), 401)
        self.assertIn("inválido", cuerpo["mensaje"])
        refresh = self.client.post("/api/token/", {"username": "admin", "password": CLAVE}, format="json").json()["refresh"]
        self.client.post("/api/token/revocar/", {"refresh": refresh}, format="json")
        cuerpo = self.assertError(self.client.post("/api/token/renovar/", {"refresh": refresh}, format="json"), 401)
        self.assertEqual(cuerpo["mensaje"], "El token es inválido, venció o fue revocado.")
        with mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"token": "1/min"}):
            cache.clear()
            self.client.post("/api/token/", {"username": "admin", "password": "mala"}, format="json")
            cuerpo = self.assertError(self.client.post("/api/token/", {"username": "admin", "password": "mala"}, format="json"), 429)
        self.assertRegex(cuerpo["mensaje"], r"^Demasiadas solicitudes\. Intenta nuevamente en \d+ segundos\.$")
        self.autenticar(self.admin)
        cuerpo = self.assertError(self.client.post("/api/cartas/", {}, format="json"), 400)
        self.assertEqual(cuerpo["detalle"]["remitente"], ["Este campo es requerido."])

    def test_listados_paginados_con_claves_en_espanol(self):
        self.autenticar(self.admin)
        listado = self.client.get("/api/usuarios/", {"tamano": 2}).json()
        self.assertEqual(set(listado), {"total", "siguiente", "anterior", "resultados"})
        self.assertEqual(listado["total"], 5)
        self.assertIn("pagina=2", listado["siguiente"])
        self.assertIsNone(listado["anterior"])

    def test_textos_de_opciones_y_errores_generales_en_espanol(self):
        self.autenticar(self.admin)
        carta = self.client.post("/api/cartas/", {"remitente": "JJVV", "asunto": "Poda", "delegacion": self.centro.pk, "fecha_ingreso": "2026-06-10"}, format="json").json()
        self.assertEqual(carta["estado_texto"], "Ingresada")
        self.assertIn("resolucion_texto", carta)
        self.assertFalse([clave for clave in carta if clave.endswith("_display")])
        cuerpo = self.assertError(self.client.post("/api/usuarios/", {
            "usuario": "nuevo", "nombres": "Nuevo", "correo": "nuevo@laserena.cl", "perfil": GRUPO_ADMINISTRATIVO,
            "identificador": "F-77", "delegacion": self.norte.pk, "cargo": self.cargo.pk, "clave": "Territorio-Norte-2026", "clave_confirmacion": "Otra-clave-2026",
        }, format="json"), 400)
        self.assertNotIn("non_field_errors", cuerpo["detalle"])
        self.assertTrue(set(cuerpo["detalle"]) <= {"errores_generales", "clave_confirmacion", "clave"}, cuerpo["detalle"])
