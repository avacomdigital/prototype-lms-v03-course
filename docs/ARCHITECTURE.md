# Arquitectura del prototipo

## Componentes

```text
AVACOM Student (Windows / Android)
        │ HTTP JSON + WebSocket
        ▼
Django + DRF APIViews + Channels :8000
        │
        ▼
SQLite (modelo LMS + quiz)
        ▲
        │ HTTP JSON + WebSocket profesor
AVACOM OPS Master (Windows)
```

Master hospeda la API local en `0.0.0.0:8000`, consulta salud y muestra la dirección LAN. Student normaliza la URL escrita por el alumno y enseña explícitamente nombre, servidor y estado de conexión. El contrato compartido y los clientes HTTP/WebSocket viven en `Avacom.OPS.Core`.

## Modelo de datos

Se replican, sin crear tablas adicionales de dominio, las 10 tablas del SQLite suministrado:

| Tabla | Modelo |
|---|---|
| `m05_marco_curricular` | `CurriculumFramework` |
| `m05_curso` | `Course` |
| `m05_curso_version` | `CourseVersion` |
| `m05_curso_estudiante` | `CourseEnrollment` |
| `m05_seccion` | `Section` |
| `m05_leccion` | `Lesson` |
| `m05_recurso_aprendizaje` | `LearningResource` |
| `m05_leccion_item` | `LessonItem` |
| `m10_actividad` | `Activity` |
| `m19_auditoria` | `AuditLog` |

Las únicas tablas nuevas son las cuatro necesarias para definir y registrar el quiz:

| Tabla | Propósito |
|---|---|
| `m10_quiz_pregunta` | Enunciado, categoría y orden. |
| `m10_quiz_opcion` | Opciones y marca de corrección privada. |
| `m10_quiz_intento` | Estudiante/dispositivo, pregunta actual, estado y nota. |
| `m10_quiz_respuesta` | Opción elegida y resultado por pregunta. |

No se agrega una tabla de persona/estudiante: `persona_id` sigue el modelo entregado y el intento conserva el nombre visible para el consolidado.

## Responsabilidades

- **Backend:** integridad, CRUD nativo, payload público seguro, calificación, auditoría básica y eventos de actividad.
- **OPS Master:** ciclo de vida del proceso Daphne, diagnóstico, creación guiada del curso, asignación, panel en vivo y detalle de resultados.
- **Student:** conexión, catálogo, exploración completa, intento, progreso, respuestas y resultado propio.
- **Core:** DTOs y transporte compartido; no contiene UI ni persistencia de dominio.

## Datos demo

El comando `python manage.py seed_exam` conserva ese nombre por compatibilidad con el instalador existente, pero ahora siembra el curso. Es idempotente; `--recreate` recompone la demo durante desarrollo.

La jerarquía es: 2 secciones → 3 lecciones → 6 items. Recursos de lectura/video ocupan los primeros cinco items y el sexto enlaza la actividad de quiz. Las preguntas y respuestas son exactamente las definidas en el alcance del prototipo.

## Instalación y operación

El instalador empaquetado incluye panel Windows autocontenido, Python embebido, API y migraciones. Genera una clave por sede, una base en una ruta escribible, registros rotativos, regla opcional TCP/8000 y accesos directos. Al abrir el `.exe`, Master intenta iniciar la API y presenta fallos de puerto, runtime, migración o salud en la propia interfaz.

## Límites conscientes del prototipo

- Sin autenticación/autorización.
- CORS amplio sólo durante `DEBUG`; clientes MAUI no dependen de CORS.
- Channels usa memoria local: un único proceso Daphne.
- Sin sincronización offline ni distribución de contenidos binarios.
- La creación guiada registra curso/secciones/lecciones; el quiz demo permanece precargado para mantener el alcance del prototipo.

