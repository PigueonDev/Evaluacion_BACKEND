# Evidencias técnicas — Evaluaciones Sumativas 1 y 2

**Asignatura:** Programación Back End (TI3041)  
**Proyecto:** Sitio informativo Ilustre Municipalidad de La Serena (2026)  
**Herramienta de IA:** Cursor (modelo Grok 4.6)  
**Fecha:** 28 de agosto de 2026

## 1. Descripción general EV1

Se desarrolló un sitio web modular con Django para presentar información institucional y de trámites de la Municipalidad de La Serena. El sistema no usa base de datos: las vistas leen archivos JSON, procesan listas con ciclos y condicionales, y envían el resultado a plantillas Bootstrap mediante el contexto.

El archivo `Contexto_Institucional_Municipalidad_La_Serena_2026.pdf` descargado correspondía a la página de inicio de sesión de INACAP (ADFS) y no al documento institucional. El contenido se construyó con información pública de la comuna (misión, visión, alcaldesa Daniela Norambuena y ejes 2025-2026).

## 2. Estructura de carpetas

```
gestion_municipal_delegacion/
├── laserena/                 # Proyecto Django (settings, urls principal)
│   ├── settings.py
│   ├── urls.py
│   └── json_utils.py         # Lectura de JSON
├── institucional/            # Aplicación 1
│   ├── views.py              # inicio + autoridades
│   ├── urls.py
│   └── data/institucion.json
├── servicios/                # Aplicación 2
│   ├── views.py              # catálogo + detalle
│   ├── urls.py
│   └── data/servicios.json
├── templates/
│   ├── base.html             # Navbar, encabezado, pie, estáticos
│   ├── institucional/
│   └── servicios/
├── static/
│   ├── css/bootstrap.min.css # Bootstrap local
│   ├── css/estilos.css
│   ├── js/bootstrap.bundle.min.js
│   └── img/                  # Imágenes locales
├── generar_estaticos.py
├── requirements.txt
├── manage.py
└── EVIDENCIAS_IA.md
```

## 3. Prompts utilizados

### Prompt 1 (solicitud inicial)
> necesito hacer un backend y con estas instrucciones de la evaluación sumativa 1; la documentación está ahí; haz un entorno virtual, descarga las librerías y completa todo lo necesario.

### Prompt 2 (contexto implícito de los PDFs)
Se adjuntaron:
- `Evaluación sumativa 1.pdf` (requerimientos oficiales del proyecto Django)
- `Contexto_Institucional_Municipalidad_La_Serena_2026.pdf` (archivo que resultó ser login INACAP)

## 4. Respuestas obtenidas y cómo se incorporaron

| Apoyo de la IA | Incorporación en el proyecto |
|---|---|
| Arquitectura de dos apps Django y `urls.py` raíz con `include` | `laserena/urls.py`, `institucional/urls.py`, `servicios/urls.py` |
| Carga de JSON desde vistas | `laserena/json_utils.py` y lectura en ambas apps |
| Plantilla base con Bootstrap (navbar, header, footer) | `templates/base.html` + `{% extends %}` en todas las páginas |
| Componentes HTML/Bootstrap (cards, badges, breadcrumb, filtros) | Inicio, autoridades, catálogo y ficha de servicio |
| Bootstrap local (CSS/JS en `static/`) | Descarga en `generar_estaticos.py` |
| Imágenes locales por app | Faro/edificio en institucional; atención ciudadana en servicios |
| Entorno virtual y dependencias | `.venv`, `requirements.txt` (Django, WhiteNoise, Pillow) |

## 5. Cumplimiento de requisitos EV1

1. Proyecto Django principal: `laserena`.
2. Dos aplicaciones: `institucional` y `servicios`.
3. Rutas principales que delegan a cada app.
4. Cada app tiene `urls.py` y al menos dos vistas.
5. Variables, tipos, operadores, funciones, `if` y `for` en las vistas.
6. Librería externa web: WhiteNoise; Pillow para imágenes.
7. Sin modelos ni uso de ORM; datos 100 % JSON.
8. Bootstrap almacenado en `static/css` y `static/js`.
9. `base.html` con navegación, encabezado, pie y `{% static %}`.
10. Herencia con `{% extends %}` y `{% block %}`.
11. Navegación global a ambas aplicaciones.
12. Imágenes locales con `{% static %}`.

## 6. Evolución EV2: Sistema de Gestión de Resultados

La segunda etapa transforma el sitio informativo en un MVP del Sistema de Gestión de Resultados (SGR) para Delegaciones Municipales. Se conservaron las aplicaciones `institucional` y `servicios`, pero ahora los datos operativos se almacenan en modelos Django y se consultan mediante ORM.

Se incorporaron delegaciones, cargos, funcionarios, períodos, ítems de medición, metas, actividades, evidencias, validaciones, compromisos, historial de compromisos y auditoría. Todas las entidades están registradas en Django Admin con búsqueda y filtros.

La configuración usa variables de entorno mediante `.env`, SQLite para desarrollo y MariaDB/MySQL para Amazon Linux EC2. El comando `python manage.py cargar_datos_demo` carga información ficticia y permite demostrar el panel, el avance y la agenda sin utilizar datos reales.

La matriz de trazabilidad y la guía de despliegue se encuentran en `docs/MATRIZ_TRAZABILIDAD.md` y `README.md`.

## 7. Evaluación Sumativa 3: uso de IA

Herramienta: agente de programación con IA (Cursor, modelo Claude) usado como asistente; las decisiones de negocio las tomó el estudiante.

| # | Prompt (resumen) | Respuesta de la IA | Cómo se aplicó |
|---|---|---|---|
| 1 | "Analiza la pauta de la Eva 3 y los nuevos requerimientos del cliente (matriz, base JJVV, descriptor) y propón cómo encajan en el SGR." | Tabla de requerimientos RF-039 a RF-058, preguntas abiertas y plan por rúbrica. | El estudiante respondió las preguntas: 3 grupos, consulta → Supervisor, tope 120 %, 7 por día, cierre semanal, importar las 2.709 organizaciones. |
| 2 | "Migra el campo `rol` y los decoradores de `permisos.py` a Grupos de Django." | Migración de datos `0006_roles_a_grupos`, eliminación del campo en `0007`, decoradores basados en grupos y sincronización de permisos en `post_migrate`. | Se revisó el mapeo de roles y se ejecutó `migrate` sobre la base con datos demo. |
| 3 | "Implementa la recuperación de contraseña por correo con token usando las vistas de Django y plantillas propias." | `PasswordResetView` y sus vistas con plantillas Bootstrap, correo en texto y HTML, backend de archivo para demo y SMTP por `.env`. | Se probó el flujo completo (solicitud, correo, enlace, nueva clave, ingreso) y se agregaron pruebas de token reutilizado y alterado. |
| 4 | "Crea la transacción Registrar actividad con tareas preparatorias que no suman, aprobación del Supervisor, 7 por día y cierre semanal." | Servicio `servicios/transacciones.py` con `transaction.atomic` y `select_for_update`, reglas en `servicios/reglas.py` y pruebas unitarias. | El estudiante validó las reglas con el cliente y revisó los casos borde (sábado, semana anterior, anuladas). |
| 5 | "Crea un comando para importar la base JJVV en estado sin verificar." | Comando `importar_jjvv` idempotente (archivo + fila de origen) con informe de calidad de datos. | Se importaron las 2.709 filas; el informe detectó filas sin domicilio, sin territorio y socios no numéricos. |

Toda respuesta se revisó, se ejecutó `python manage.py check` y `python manage.py test` antes de cada commit.
