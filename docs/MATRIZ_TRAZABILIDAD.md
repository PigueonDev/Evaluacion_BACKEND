# Matriz inicial de trazabilidad SGR

| Historia | Requisito | Implementación | Evidencia sugerida |
|---|---|---|---|
| HU-01 Registro de actividades | RF-009, RF-010, RF-011 | `Actividad`, código UUID y vista de actividades | Actividad creada y código visible |
| HU-02 Compromisos | RF-016 a RF-019 | `Compromiso`, estados y agenda | Compromiso pendiente y vencido |
| HU-04 Funciones por cargo | RF-003, RF-006 | `Cargo.funciones` y `Meta` | Cargo configurado en Admin |
| HU-05 Metas | RF-005 a RF-007 | `Periodo` y `Meta` | Período y ponderador en Admin |
| HU-06 Seguimiento | RF-008, RF-022 a RF-028 | Propiedades de avance, cumplimiento y semáforo | Panel SGR |
| HU-09 Evidencias | RF-012 | `Evidencia` con `FileField` | Archivo asociado a actividad |
| HU-11 Validación | RF-013, RF-014 | `Validacion` y estado de evidencia | Aprobación o rechazo en Admin |
| HU-18 Resumen ejecutivo | RF-028, RF-029 | Dashboard ORM | Totales por delegación |
| HU-26 Administración | RF-001, RF-002, RF-004 | Django Admin para entidades | Capturas de CRUD y búsqueda |
| HU-29 Filtros | RF-032 | Filtros por estado y categoría | URL filtrada |
| HU-30 Auditoría | RF-036 | Modelo `Auditoria` | Registro de operación |

## Casos de prueba pendientes de ejecutar

- Crear una actividad con datos obligatorios y verificar su UUID.
- Registrar una evidencia y cambiar su decisión a aprobada o rechazada.
- Confirmar que solo una actividad validada cuenta para el avance.
- Crear un compromiso con fecha vencida y verificar su resaltado en Agenda.
- Crear usuarios con permisos diferenciados y probar acceso horizontal.
- Cerrar un período y verificar que los resultados operativos no se modifiquen.
