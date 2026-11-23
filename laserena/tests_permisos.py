from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.request import Request

from institucional.models import Cargo, Delegacion, Funcionario
from laserena.permisos import (
    GRUPO_ADMINISTRADOR,
    GRUPO_ADMINISTRATIVO,
    GRUPO_SUPERVISOR,
    GRUPOS_SGR,
    PERMISOS_POR_PERFIL,
    EsAdministradorOSoloLectura,
    PermisoActividad,
    PermisoCarta,
    PermisoRevision,
    asignar_grupo,
    codigos_del_perfil,
    matriz_permisos,
    permisos_del_sistema,
)

ADMINISTRADOR, SUPERVISOR, ADMINISTRATIVO, ANONIMO = GRUPO_ADMINISTRADOR, GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO, "Anónimo"

# Matriz vigente de cada perfil operativo. Un permiso nuevo se suma aquí a propósito.
SUPERVISOR_ANTERIOR = {
    "organizaciones.view_organizacioncomunitaria", "organizaciones.add_organizacioncomunitaria", "organizaciones.change_organizacioncomunitaria",
    "organizaciones.verificar_organizacion", "servicios.view_actividad", "servicios.aprobar_actividad", "servicios.view_evidencia",
    "servicios.aprobar_evidencia", "servicios.view_tareapreparatoria",
    "servicios.view_compromiso", "servicios.view_meta", "institucional.view_funcionario", "oficina.view_carta", "oficina.add_carta",
    "oficina.change_carta", "oficina.delete_carta", "oficina.view_beneficionino", "oficina.add_beneficionino", "oficina.change_beneficionino",
    "oficina.delete_beneficionino", "oficina.view_ausencia", "oficina.add_ausencia", "oficina.anular_ausencia", "oficina.view_ajustemeta",
    "oficina.view_reconocimiento", "oficina.add_reconocimiento", "oficina.change_reconocimiento", "institucional.view_cargo",
    "institucional.view_unidadmunicipal",
}
ADMINISTRATIVO_ANTERIOR = {
    "organizaciones.view_organizacioncomunitaria", "servicios.view_actividad", "servicios.add_actividad", "servicios.change_actividad",
    "servicios.view_evidencia", "servicios.add_evidencia",
    "servicios.view_tareapreparatoria", "servicios.add_tareapreparatoria", "servicios.change_tareapreparatoria", "servicios.view_caso",
    "servicios.add_caso", "servicios.change_caso", "servicios.add_gestion", "servicios.change_gestion", "servicios.view_compromiso",
    "servicios.add_compromiso", "servicios.change_compromiso", "oficina.view_carta", "oficina.change_carta", "oficina.view_beneficionino",
    "oficina.add_beneficionino", "oficina.change_beneficionino", "oficina.view_ausencia", "oficina.view_reconocimiento",
}

# Código HTTP esperado de cada pantalla por perfil (200 entra, 403 denegado, 302 al inicio de sesión o a su panel).
ACCESO_WEB = {
    "/administracion/": (200, 403, 403, 302),
    "/administracion/usuarios/": (200, 403, 403, 302),
    "/administracion/usuarios/nuevo/": (200, 403, 403, 302),
    "/administracion/grupos/": (200, 403, 403, 302),
    "/administracion/grupos/nuevo/": (200, 403, 403, 302),
    "/administracion/cargos/": (200, 403, 403, 302),
    "/administracion/unidades/": (200, 403, 403, 302),
    "/administracion/unidades/nueva/": (200, 403, 403, 302),
    "/panel/": (302, 200, 200, 302),
    "/servicios/panel-municipal/": (200, 403, 403, 302),
    "/servicios/actividades/": (200, 403, 200, 302),
    "/servicios/actividades/nueva/": (200, 403, 200, 302),
    "/servicios/actividades/codigo/": (200, 403, 200, 302),
    "/servicios/actividades/exportar/excel/": (200, 403, 200, 302),
    "/servicios/casos/": (200, 403, 200, 302),
    "/servicios/casos/nuevo/": (200, 403, 200, 302),
    "/servicios/agenda/": (200, 403, 200, 302),
    "/servicios/agenda/nueva/": (200, 403, 200, 302),
    "/servicios/aprobaciones/": (200, 200, 403, 302),
    "/servicios/evidencias/": (200, 200, 403, 302),
    "/servicios/agenda/resumen/": (200, 200, 403, 302),
    "/servicios/matriz/resumen/": (200, 200, 403, 302),
    "/servicios/consulta/": (200, 200, 403, 302),
    "/oficina/cartas/": (200, 200, 200, 302),
    "/oficina/cartas/nueva/": (200, 200, 403, 302),
    "/oficina/cartas/exportar/excel/": (200, 200, 200, 302),
    "/oficina/beneficios/": (200, 200, 200, 302),
    "/oficina/beneficios/nuevo/": (200, 200, 200, 302),
    "/oficina/ausencias/": (200, 200, 200, 302),
    "/oficina/ausencias/registrar/": (200, 200, 403, 302),
    "/oficina/felicitaciones-y-reclamos/": (200, 200, 200, 302),
    "/oficina/felicitaciones-y-reclamos/registrar/": (200, 200, 403, 302),
    "/organizaciones/": (200, 200, 200, 302),
    "/organizaciones/nueva/": (200, 200, 403, 302),
}

# Permiso de la API por método HTTP: (Administrador, Supervisor, Administrativo).
ACCESO_API = {
    PermisoCarta: {"GET": (True, True, True), "POST": (True, True, False), "PUT": (True, True, True), "DELETE": (True, True, False)},
    PermisoActividad: {"GET": (True, True, True), "POST": (True, False, True), "PUT": (True, False, True), "DELETE": (True, False, True)},
    PermisoRevision: {"POST": (True, True, False)},
    EsAdministradorOSoloLectura: {"GET": (True, True, True), "POST": (True, False, False), "PUT": (True, False, False), "DELETE": (True, False, False)},
}


class BasePermisos(TestCase):
    @classmethod
    def setUpTestData(cls):
        delegacion = Delegacion.objects.create(nombre="Centro", slug="centro", territorio="Centro", enfoque="-")
        cargo = Cargo.objects.create(nombre="Territorial", perfil=GRUPO_ADMINISTRATIVO)
        cls.cuentas = {}
        for perfil in GRUPOS_SGR:
            usuario = get_user_model().objects.create_user(username=perfil.lower(), password="Serena-pruebas-2026")
            asignar_grupo(usuario, perfil)
            Funcionario.objects.create(usuario=usuario, identificador=perfil, nombre_completo=perfil, delegacion=delegacion, cargo=cargo)
            cls.cuentas[perfil] = usuario

    def cuenta(self, perfil):
        return get_user_model().objects.get(pk=self.cuentas[perfil].pk)


class MatrizDePermisosTest(BasePermisos):
    def test_la_matriz_concede_lo_mismo_que_antes(self):
        self.assertEqual(set(codigos_del_perfil(GRUPO_SUPERVISOR)), SUPERVISOR_ANTERIOR)
        self.assertEqual(set(codigos_del_perfil(GRUPO_ADMINISTRATIVO)), ADMINISTRATIVO_ANTERIOR)
        self.assertEqual(set(PERMISOS_POR_PERFIL), {GRUPO_SUPERVISOR, GRUPO_ADMINISTRATIVO})

    def test_los_grupos_quedan_con_su_matriz_despues_de_migrate(self):
        for perfil, esperado in ((GRUPO_SUPERVISOR, SUPERVISOR_ANTERIOR), (GRUPO_ADMINISTRATIVO, ADMINISTRATIVO_ANTERIOR)):
            grupo = Group.objects.get(name=perfil)
            concedidos = {f"{p.content_type.app_label}.{p.codename}" for p in grupo.permissions.select_related("content_type")}
            self.assertEqual(concedidos, esperado, perfil)
        administrador = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        self.assertEqual(set(administrador.permissions.all()), set(permisos_del_sistema()))
        self.assertTrue(administrador.permissions.filter(codename="change_user").exists())

    def test_cada_perfil_tiene_los_permisos_de_su_grupo(self):
        administrativo, supervisor, administrador = (self.cuenta(p) for p in (GRUPO_ADMINISTRATIVO, GRUPO_SUPERVISOR, GRUPO_ADMINISTRADOR))
        self.assertTrue(supervisor.has_perm("servicios.aprobar_actividad"))
        self.assertFalse(administrativo.has_perm("servicios.aprobar_actividad"))
        self.assertTrue(administrativo.has_perm("servicios.add_actividad"))
        self.assertFalse(supervisor.has_perm("servicios.add_actividad"))
        self.assertTrue(administrativo.has_perm("servicios.add_evidencia"))
        self.assertFalse(administrativo.has_perm("servicios.aprobar_evidencia"))
        self.assertTrue(supervisor.has_perm("servicios.aprobar_evidencia"))
        self.assertFalse(supervisor.has_perm("servicios.add_evidencia"))
        self.assertTrue(administrador.has_perm("servicios.add_evidencia"))
        self.assertTrue(administrador.has_perm("servicios.aprobar_evidencia"))
        self.assertFalse(supervisor.has_perm("auth.change_user"))
        self.assertTrue(administrador.has_perm("auth.change_user"))
        self.assertTrue(administrador.has_perm("organizaciones.delete_organizacioncomunitaria"))

    def test_nombres_de_permisos_en_espanol(self):
        nombres = set(permisos_del_sistema().values_list("name", flat=True))
        self.assertFalse([nombre for nombre in nombres if nombre.startswith("Can ")])
        for nombre in ("Puede ver actividad", "Puede agregar carta de Oficina de Partes", "Puede modificar usuario",
                       "Puede eliminar grupo", "Puede ver ítem de medición", "Puede aprobar o rechazar actividades"):
            self.assertIn(nombre, nombres)

    def test_matriz_legible_por_perfil_y_accion(self):
        perfiles, filas = matriz_permisos()
        self.assertEqual(perfiles, list(GRUPOS_SGR))
        por_recurso = {fila["recurso"]: dict(zip(perfiles, fila["celdas"])) for fila in filas}
        self.assertEqual(por_recurso["Actividades"], {
            GRUPO_ADMINISTRADOR: ["Ver", "Agregar", "Modificar", "Eliminar", "Aprobar"],
            GRUPO_SUPERVISOR: ["Ver", "Aprobar"],
            GRUPO_ADMINISTRATIVO: ["Ver", "Agregar", "Modificar"],
        })
        self.assertEqual(por_recurso["Evidencias"], {
            GRUPO_ADMINISTRADOR: ["Ver", "Agregar", "Modificar", "Eliminar", "Aprobar"],
            GRUPO_SUPERVISOR: ["Ver", "Aprobar"],
            GRUPO_ADMINISTRATIVO: ["Ver", "Agregar"],
        })
        self.assertEqual(por_recurso["Organizaciones comunitarias"][GRUPO_SUPERVISOR], ["Ver", "Agregar", "Modificar", "Verificar"])
        self.assertEqual(por_recurso["Ausencias"][GRUPO_SUPERVISOR], ["Ver", "Agregar", "Anular"])
        self.assertEqual(por_recurso["Usuarios"][GRUPO_ADMINISTRATIVO], [])


class AccesoWebPorPerfilTest(BasePermisos):
    def test_cada_pantalla_responde_segun_el_perfil(self):
        for indice, perfil in enumerate((ADMINISTRADOR, SUPERVISOR, ADMINISTRATIVO, ANONIMO)):
            cliente = self.client_class()
            if perfil != ANONIMO:
                cliente.force_login(self.cuentas[perfil])
            for ruta, esperado in ACCESO_WEB.items():
                with self.subTest(perfil=perfil, ruta=ruta):
                    self.assertEqual(cliente.get(ruta).status_code, esperado[indice])

    def test_denegado_muestra_la_pagina_en_espanol(self):
        self.client.force_login(self.cuentas[SUPERVISOR])
        respuesta = self.client.get("/administracion/usuarios/")
        self.assertTemplateUsed(respuesta, "institucional/denegado.html")
        self.assertContains(respuesta, "Acceso restringido", status_code=403)

    def test_la_ruta_anterior_del_panel_municipal_redirige(self):
        self.client.force_login(self.cuentas[ADMINISTRADOR])
        self.assertRedirects(self.client.get("/servicios/dashboard/"), reverse("servicios:panel_municipal"))

    def test_grupos_muestra_la_matriz_y_permisos_en_espanol(self):
        self.client.force_login(self.cuentas[ADMINISTRADOR])
        listado = self.client.get(reverse("institucional:grupos"))
        self.assertContains(listado, "Matriz de permisos por perfil")
        self.assertContains(listado, "Organizaciones comunitarias")
        self.assertContains(listado, "Verificar")
        formulario = self.client.get(reverse("institucional:grupo_editar", args=[Group.objects.get(name=GRUPO_SUPERVISOR).pk]))
        self.assertContains(formulario, "Acciones permitidas")
        self.assertNotContains(formulario, "Can ")
        aprobar = Permission.objects.get(codename="aprobar_actividad")
        self.assertContains(formulario, f'value="{aprobar.pk}"')


class AccesoAPIPorPerfilTest(BasePermisos):
    def test_permisos_drf_por_perfil_y_metodo(self):
        fabrica = RequestFactory()
        for clase, metodos in ACCESO_API.items():
            for metodo, esperado in metodos.items():
                for perfil, permitido in zip((ADMINISTRADOR, SUPERVISOR, ADMINISTRATIVO), esperado):
                    peticion = Request(fabrica.generic(metodo, "/api/"))
                    peticion.user = self.cuenta(perfil)
                    with self.subTest(clase=clase.__name__, metodo=metodo, perfil=perfil):
                        self.assertIs(clase().has_permission(peticion, None), permitido)

    def test_cuenta_sin_perfil_no_pasa_ningun_permiso(self):
        sin_perfil = get_user_model().objects.create_user(username="sin-perfil", password="Serena-pruebas-2026")
        peticion = Request(RequestFactory().get("/api/"))
        peticion.user = sin_perfil
        for clase in ACCESO_API:
            self.assertFalse(clase().has_permission(peticion, None))
