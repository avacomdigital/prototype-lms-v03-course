# API del prototipo AVACOM Courses

Base local: `http://127.0.0.1:8000`. En los clientes de la LAN se usa la IP del Master: `http://<ip-master>:8000`.

Todos los cuerpos son JSON. No hay autenticación en este prototipo; debe añadirse antes de cualquier despliegue fuera de una LAN controlada.

## Salud

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health/` | Diagnóstico de conexión mostrado por ambas apps. |

Respuesta: `{"status":"ok","service":"avacom-ops-master"}`.

## CRUD con APIViews

Cada colección admite `GET` y `POST`; cada detalle admite `GET`, `PUT`, `PATCH` y `DELETE`.

| Recurso | Colección | Detalle |
|---|---|---|
| Marco curricular | `/api/curriculum-frameworks/` | `/api/curriculum-frameworks/{clave}/` |
| Curso | `/api/courses/` | `/api/courses/{id}/` |
| Versión | `/api/course-versions/` | `/api/course-versions/{id}/` |
| Inscripción | `/api/enrollments/` | `/api/enrollments/{id}/` |
| Sección | `/api/sections/` | `/api/sections/{id}/` |
| Lección | `/api/lessons/` | `/api/lessons/{id}/` |
| Lesson Item | `/api/lesson-items/` | `/api/lesson-items/{id}/` |
| Recurso | `/api/learning-resources/` | `/api/learning-resources/{id}/` |
| Actividad | `/api/activities/` | `/api/activities/{id}/` |
| Auditoría | `/api/audit-logs/` | `/api/audit-logs/{id}/` |
| Pregunta (administración) | `/api/quiz-questions/` | `/api/quiz-questions/{id}/` |
| Opción (administración) | `/api/quiz-options/` | `/api/quiz-options/{id}/` |

Filtros disponibles: `courses?student=1`, `courses?estado=habilitado`, `course-versions?curso_id=…`, `enrollments?curso_id=…`, `sections?curso_id=…`, `lessons?seccion_id=…`, `lesson-items?leccion_id=…`, `quiz-questions?actividad_id=…` y `quiz-options?pregunta_id=…`.

`GET /api/courses/{id}/` devuelve la jerarquía completa curso → secciones → lecciones → Lesson Items. En actividades quiz incluye preguntas y opciones públicas, nunca `es_correcta`.

## Experiencia del quiz

| Método | Ruta | Cuerpo/resultado |
|---|---|---|
| GET | `/api/quizzes/{actividad_id}/` | Actividad, 5 preguntas y opciones públicas. |
| POST | `/api/quiz-attempts/start/` | `actividad_id`, `nombre_estudiante`, `persona_id?`, `device_id?`. Crea o reanuda el intento en progreso. |
| POST | `/api/quiz-attempts/progress/` | `intento_id`, `pregunta_actual`. Actualiza y difunde al profesor. |
| POST | `/api/quiz-attempts/answer/` | `intento_id`, `pregunta_id`, `opcion_id`, `client_event_id?`. Inserta o reemplaza la respuesta. |
| POST | `/api/quiz-attempts/finish/` | `intento_id`. Califica sobre `max_score` y finaliza de forma idempotente. |
| GET | `/api/quiz-results/?actividad_id={id}` | Consolidado para Master. |
| GET | `/api/quiz-results/{intento_id}/` | Resumen y detalle con elegida/correcta. |

Ejemplo de inicio:

```json
{
  "actividad_id": "ab12…",
  "nombre_estudiante": "Mariana López",
  "persona_id": "mariana-lópez",
  "device_id": "android-aula-08"
}
```

La nota se calcula como `aciertos × max_score / total_preguntas`, redondeada a dos decimales.

## WebSocket

Ruta:

```text
ws://<ip-master>:8000/ws/activities/{actividad_id}/?role=professor
ws://<ip-master>:8000/ws/activities/{actividad_id}/?role=student&attempt_id={intento_id}
```

Eventos:

- `presence_changed`: cantidad de estudiantes conectados.
- `activity_state`: confirma actividad activa.
- `student_progress`: sólo grupo de profesor; incluye intento, nombre, pregunta actual y respuestas guardadas.
- `attempt_finished`: sólo profesor; incluye nota y estado final.
- `pong`: respuesta a `{"type":"ping"}` o heartbeat.

El canal en memoria es suficiente para una única instancia local de Daphne. Si se escala a varios procesos, debe reemplazarse por Redis.

