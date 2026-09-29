# Documento Técnico
## Sistema de Gestión de Resultados para Delegaciones Municipales

**Asignatura:** Programación Back End (TI3041)  
**Institución:** INACAP  
**Proyecto:** Evolución del sitio de la Ilustre Municipalidad de La Serena  
**Evaluación:** Sumativa N.° 2  
**Período:** Primavera 2026  
**Estudiante:** Completar  
**Fecha:** Completar

> Este documento utiliza exclusivamente datos ficticios de demostración. Las capturas reales de AWS, GitHub, MariaDB/phpMyAdmin y la ejecución final deben agregarse antes de entregar.

---

## 1. Descripción del proyecto

### 1.1 Objetivo

Desarrollar una aplicación web para centralizar el registro, seguimiento, validación y medición de actividades realizadas por funcionarios de las Delegaciones Municipales de La Serena.

El sistema permite registrar actividades y compromisos territoriales, asociar evidencias, validar resultados y consultar indicadores de gestión por funcionario, período y delegación.

### 1.2 Temática elegida

La temática corresponde a la gestión territorial de las Delegaciones Municipales de La Serena. Estas unidades acercan los servicios municipales a los territorios, canalizan solicitudes, coordinan respuestas y permiten realizar seguimiento de compromisos con la comunidad.

El sistema considera las siguientes delegaciones ficticias de demostración:

- Avenida del Mar.
- Centro.
- La Antena.
- Las Compañías.
- La Pampa.
- Rural.

### 1.3 Funcionalidades implementadas

- Administración de municipios, delegaciones, cargos, funcionarios y autoridades.
- Catálogo de servicios municipales.
- Configuración de períodos de medición.
- Configuración de ítems y metas.
- Registro de actividades con código único de evidencia.
- Registro de compromisos en agenda colectiva.
- Asociación de evidencias a actividades.
- Validación de evidencias mediante aprobación, rechazo o solicitud de corrección.
- Cálculo de avance aprobado.
- Cálculo de porcentaje de cumplimiento.
- Cálculo de resultado ponderado.
- Clasificación mediante semáforo verde, ámbar y rojo.
- Dashboard de indicadores básicos.
- Filtros de actividades, servicios y compromisos.
- Administración CRUD mediante Django Admin.
- Variables sensibles configurables mediante `.env`.
- Preparación de despliegue con Gunicorn y Nginx.

---

## 2. Arquitectura

### 2.1 Arquitectura lógica

La aplicación utiliza una arquitectura web basada en Django:

```text
Navegador web
    |
    v
URLs Django
    |
    v
Vistas y consultas ORM
    |
    v
Modelos Django y reglas de negocio
    |
    v
MariaDB/MySQL en EC2
    |
    +-- Evidencias almacenadas en media/
```

En desarrollo local se utiliza SQLite para facilitar las pruebas. En Amazon Linux EC2 se utiliza MariaDB/MySQL, configurable mediante variables de entorno.

### 2.2 Estructura de carpetas

```text
gestion_municipal_delegacion/
├── laserena/
│   ├── settings.py          # Configuración y variables de entorno
│   ├── urls.py              # Rutas principales y Django Admin
│   ├── wsgi.py              # Entrada para Gunicorn
│   └── asgi.py
├── institucional/
│   ├── models.py            # Municipio, delegación, cargo, funcionario
│   ├── views.py             # Inicio y autoridades mediante ORM
│   ├── admin.py             # Administración institucional
│   ├── migrations/          # Migraciones institucionales
│   └── data/                # Datos fuente ficticios para carga demo
├── servicios/
│   ├── models.py            # Actividades, metas, evidencias y agenda
│   ├── views.py             # Catálogo, dashboard, actividades y agenda
│   ├── admin.py             # Administración SGR
│   ├── management/commands/
│   │   └── cargar_datos_demo.py
│   ├── migrations/          # Migraciones SGR
│   └── data/                # Catálogo fuente ficticio
├── templates/
│   ├── base.html
│   ├── institucional/
│   └── servicios/
├── static/
│   ├── css/
│   ├── img/
│   └── js/
├── deploy/
│   ├── laserena.service     # Servicio systemd para Amazon Linux
│   └── nginx.conf            # Proxy inverso
├── docs/
│   ├── DOCUMENTO_TECNICO_EV2.md
│   └── MATRIZ_TRAZABILIDAD.md
├── manage.py
├── requirements.txt
├── .env.example
└── README.md
```

### 2.3 Aplicaciones desarrolladas

#### Aplicación `institucional`

Administra la información organizacional y territorial:

- Municipio.
- Delegación.
- Cargo.
- Funcionario.
- Autoridad.

#### Aplicación `servicios`

Administra la operación del Sistema de Gestión de Resultados:

- Servicio.
- Ítem de medición.
- Período.
- Meta.
- Actividad.
- Evidencia.
- Validación.
- Compromiso.
- Historial de compromisos.
- Auditoría.

### 2.4 Base de datos utilizada

En Amazon Linux EC2 se utiliza MariaDB/MySQL con los siguientes parámetros configurables:

```env
DB_ENGINE=mysql
DB_NAME=sgr_laserena
DB_USER=sgr_user
DB_PASSWORD=CLAVE_DE_LA_BASE
DB_HOST=127.0.0.1
DB_PORT=3306
```

Las credenciales no se almacenan en el repositorio. Se cargan desde `.env` mediante `python-dotenv`.

---

## 3. Instalación y ejecución

### 3.1 Desarrollo local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py createsuperuser
python manage.py runserver
```

Rutas principales:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/servicios/dashboard/`
- `http://127.0.0.1:8000/servicios/actividades/`
- `http://127.0.0.1:8000/servicios/agenda/`
- `http://127.0.0.1:8000/admin/`

### 3.2 Amazon Linux EC2

```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip git mariadb105-server nginx
sudo systemctl enable --now mariadb
sudo systemctl enable --now nginx

git clone URL_DEL_REPOSITORIO
cd gestion_municipal_delegacion
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

La aplicación se ejecuta mediante Gunicorn y Nginx usando los archivos preparados en `deploy/`.

---

## 4. Evidencia AWS

### 4.1 Instancia EC2

**Captura requerida:** consola de AWS mostrando la instancia EC2 activa.

> Insertar aquí la captura de la instancia EC2.

**Datos a identificar en la captura:**

- Nombre de la instancia.
- Estado `Running`.
- Sistema operativo Amazon Linux.
- Dirección IP pública o DNS, sin exponer credenciales privadas.

### 4.2 Terminal Linux

**Captura requerida:** conexión SSH a la instancia y ejecución de comandos.

Comandos sugeridos para evidenciar:

```bash
cat /etc/os-release
python3 --version
git --version
source .venv/bin/activate
python manage.py showmigrations
```

> Insertar aquí la captura de la terminal Linux con el entorno virtual activo.

### 4.3 Ejecución del proyecto

**Captura requerida:** aplicación ejecutándose desde EC2.

Comandos posibles:

```bash
sudo systemctl status laserena
sudo systemctl status nginx
curl http://127.0.0.1
```

> Insertar aquí la captura del sitio funcionando desde la IP pública de EC2.

---

## 5. Evidencia GitHub

### 5.1 Repositorio

El repositorio debe contener:

- Código fuente.
- Migraciones.
- README.
- `.gitignore`.
- Documentación técnica.
- Historial de commits.

> Insertar aquí la captura de la página principal del repositorio GitHub.

### 5.2 Historial de commits

Comando de verificación:

```bash
git log --oneline --decorate --graph -10
```

> Insertar aquí la captura del historial de commits.

### 5.3 Clonación hacia EC2

Comando solicitado por la evaluación:

```bash
git clone URL_DEL_REPOSITORIO
```

> Insertar aquí la captura de la clonación desde GitHub hacia EC2.

---

## 6. Evidencia de base de datos

### 6.1 Modelos Django

Los modelos están implementados en:

- `institucional/models.py`.
- `servicios/models.py`.

> Insertar aquí capturas del código de los modelos principales.

### 6.2 Migraciones

Comandos utilizados:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

Migraciones relevantes:

- `institucional/migrations/0001_initial.py`.
- `institucional/migrations/0002_initial.py`.
- `institucional/migrations/0003_autoridad_municipio.py`.
- `servicios/migrations/0001_initial.py`.

> Insertar aquí la captura de `showmigrations` mostrando las migraciones aplicadas.

### 6.3 Tablas creadas

Las tablas principales corresponden a:

- Delegaciones.
- Cargos.
- Funcionarios.
- Servicios.
- Ítems de medición.
- Períodos.
- Metas.
- Actividades.
- Evidencias.
- Validaciones.
- Compromisos.
- Historial de compromisos.
- Auditoría.

> Insertar aquí la captura de las tablas en MariaDB/phpMyAdmin.

---

## 7. Evidencia phpMyAdmin

### 7.1 Existencia de tablas

> Insertar aquí la captura del listado de tablas de la base `sgr_laserena`.

### 7.2 Registros almacenados

El comando de carga demo utilizado es:

```bash
python manage.py cargar_datos_demo
```

Este comando crea datos ficticios de demostración, incluyendo una actividad validada, una meta, un compromiso y un funcionario.

> Insertar aquí una captura de registros almacenados en phpMyAdmin.

### 7.3 Relaciones implementadas

Relaciones principales:

```text
Delegacion 1 ─── N Funcionario
Cargo 1 ─── N Funcionario
Periodo 1 ─── N Meta
ItemMedicion 1 ─── N Meta
Funcionario 1 ─── N Actividad
Actividad 1 ─── N Evidencia
Evidencia 1 ─── N Validacion
Delegacion 1 ─── N Compromiso
Compromiso 1 ─── N HistorialCompromiso
```

> Insertar aquí una captura de la estructura de una tabla con sus claves foráneas.

---

## 8. Evidencia de Django Admin

El panel administrativo está disponible en:

```text
/admin/
```

El superusuario de demostración debe crearse mediante:

```bash
python manage.py createsuperuser
```

Desde el panel se pueden crear, modificar, eliminar, buscar y visualizar las entidades del sistema.

> Insertar aquí capturas de:
>
> - Inicio de sesión del Admin.
> - Listado de modelos.
> - Creación de una delegación.
> - Edición de una actividad.
> - Búsqueda de un funcionario.
> - Validación de una evidencia.

---

## 9. Evidencia de IA

La evidencia detallada se encuentra en `EVIDENCIAS_IA.md`.

### 9.1 Prompts utilizados

Ejemplos de prompts aplicados:

- Solicitud de transformación del proyecto Django desde JSON hacia modelos ORM.
- Solicitud de diseño de entidades para delegaciones, funcionarios, actividades, metas y evidencias.
- Solicitud de configuración de variables de entorno para una base MySQL/MariaDB.
- Solicitud de preparación del despliegue en Amazon Linux EC2 con Gunicorn y Nginx.
- Solicitud de adaptación visual a la identidad de la Municipalidad de La Serena.

### 9.2 Respuestas obtenidas

La asistencia de IA propuso:

- Mantener las dos aplicaciones existentes.
- Crear modelos relacionados mediante `ForeignKey` y `ManyToManyField`.
- Registrar todos los modelos en Django Admin.
- Utilizar migraciones y consultas ORM.
- Cargar datos ficticios mediante un comando Django.
- Separar secretos mediante `.env`.
- Preparar archivos systemd y Nginx para Amazon Linux.

### 9.3 Aplicación en el desarrollo

Las propuestas fueron aplicadas en:

- `institucional/models.py`.
- `servicios/models.py`.
- `institucional/admin.py`.
- `servicios/admin.py`.
- `laserena/settings.py`.
- `servicios/management/commands/cargar_datos_demo.py`.
- `deploy/laserena.service`.
- `deploy/nginx.conf`.
- `docs/MATRIZ_TRAZABILIDAD.md`.

---

## 10. Pruebas realizadas

Comandos ejecutados:

```bash
python manage.py check
python manage.py test servicios.tests
python manage.py showmigrations
```

Resultados esperados:

- `System check identified no issues`.
- Pruebas unitarias de período, meta y avance aprobadas.
- Migraciones institucionales y SGR aplicadas.
- Rutas públicas y Django Admin disponibles.

> Insertar aquí la captura de la consola con las pruebas exitosas.

---

## 11. Conclusiones y limitaciones

El proyecto evolucionó desde un sitio informativo con archivos JSON hacia una aplicación Django con persistencia relacional, administración de entidades y un flujo inicial de gestión de resultados.

La versión implementada cubre el MVP académico de registro, agenda, medición básica, administración y despliegue. Como trabajo posterior se pueden ampliar los formularios frontend, los permisos por delegación, la auditoría automática de cambios y los informes exportables.

Las capturas de AWS, GitHub y phpMyAdmin deben corresponder al ambiente real utilizado durante la revisión presencial.
