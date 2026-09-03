# Requerimiento Principal 

Realizar un ajuste para el AVACOM Student dónde pueda ver los cursos disponibles cómo se ve en el resumen de AVACOM OPS Master

# Constitución

1. No debes modificar nada del AVACOM OPS Master este ya funciona perfecto
2. No debes modificar nada del backend 
3. Recuerda que la API del Backend debe correr en el 0.0.0.0
4. No va a existir login por ahora porque es un prototipo
 
# Especificación

Los cursos que ya están disponibles en el backend y el AVACOM OPS Master, ahora debemos hacer una versión para estudiantes con el objetivo de que la app del estudiante también
sepa qué contenido está instalado en la clase.

Base para las tabletas
http://192.168.0.29:8000

Todos son GET. Ninguno modifica nada.

1 · Los cursos del alumno, con los que no tienen contenido
GET /api/students/{persona_id}/courses/?host_id={host}

Es el endpoint principal para lo que preguntas: sale de la MATRÍCULA, no del catálogo, así que un curso cuyo contenido desapareció sigue apareciendo —con su progreso— en vez de desvanecerse.

{
  "student_id": "juan-contenido",
  "host_id": "DESKTOP-0OODE4D",
  "available":   [ /* los que se pueden abrir ahora */ ],
  "unavailable": [ /* los que NO tienen contenido disponible */ ],
  "courses": [
    {
      "course_id": "CURSO-CO-PREESCOLAR-TRANSICION--3DBBA139",
      "name": "Exploración del medio · Transición",
      "progress": 0.28,
      "progress_pct": 28.0,
      "installed": true,
      "available": true,
      "enrollment": "activa",
      "content_format": "avacom_contenido",
      "host_state": "disponible",
      "retired_at": null,
      "lessons": 5,
      "lessons_completed": 1
    }
  ]
}

Un curso sin contenido llega en unavailable con installed: false, available: false, host_state: "desinstalado", retired_at con la fecha — y su progress intacto. Eso es lo que la tableta debe pintar atenuado con el motivo, no esconder.

$b = "http://192.168.0.29:8000"; $p = "juan-contenido"; $h = "DESKTOP-0OODE4D"
$d = Invoke-RestMethod "$b/api/students/$p/courses/?host_id=$h"
$d.courses | Format-Table name, progress_pct, installed, available, host_state -AutoSize
2 · El catálogo con el árbol, para navegar
GET /api/courses/?student=1

Devuelve un array de cursos con secciones → lecciones → items. Solo trae lo que se puede abrir: filtra por m05_curso_host y por la política de la escuela. Es lo que ya consume CoursesViewModel.

(Invoke-RestMethod "$b/api/courses/?student=1") | Format-Table id, titulo, estado -AutoSize
3 · El veredicto de un curso
GET /api/courses/{course_id}/contenido/

Cuerpo relevante:

{
  "titulo": "Exploración del medio · Transición",
  "componente_disponible": true,
  "contenido_retirado": false,
  "motivo": "",
  "estructura_visible": true,
  "registro_desfasado": false,
  "registro_saneado": false,
  "origen": {
    "formato_contenido": "avacom_contenido",
    "package_identifier": "co-preescolar-transicion-exploracion",
    "depende_de_biblioteca": true,
    "paquete_presente": true,
    "presente_local": true,
    "retirado_en": null
  },
  "elementos": [ { "ref": "...", "tipo": "leccion", "titulo": "...", "nivel": "...", "grado": "...", "asignatura": "..." } ],
  "conteos": { "elementos_del_paquete": 5, "materiales": 3, "materiales_disponibles": 3, "materiales_ausentes": 0 }
}
4 · El material repartido a la clase
GET /api/students/{persona_id}/contenido/?host_id={host}
{
  "persona_id": "juan-contenido",
  "componente_disponible": true,
  "count": 1,
  "materiales": [
    { "elemento_ref": "co-sec-mat-eval-funcion", "tipo": "evaluacion",
      "titulo": "Evaluación · Función lineal", "disponible": true, "motivo": "" }
  ]
}
Lo de no poder borrar, y un defecto que encontré al documentarlo

Estos cuatro son GET puros. Lo destructivo vive en rutas que la tableta no debe llamar nunca: POST /api/courses/{id}/uninstall/, DELETE /api/materiales/{id}/, POST /api/contenido/reparto/, POST /api/contenido/reconciliar/.

Pero al capturar los cuerpos encontré que GET /api/courses/{id}/contenido/ escribía: saneaba presente_local al pasar. Una tableta que conociera la ruta habría estado modificando las banderas de presencia del equipo. Un GET no debe mutar, y menos uno alcanzable desde la LAN.

Lo hice opt-in: el saneo ahora requiere ?sanear=1, que pide el panel y no piden las tabletas. El cuerpo declara registro_desfasado (lo hay) y registro_saneado (se arregló), así que la tableta informa sin escribir. Hay una prueba dedicada a que la misma ruta sin el parámetro no toque la base.

Sigue pendiente lo que hemos hablado: no hay autenticación, así que «la tableta no debe llamar» es hoy una convención del cliente, no algo que el servidor impida. Cuando se cierre la Q-3 del spec, esas rutas deberían exigir credencial de docente.

Reinicié el backend para cargar el cambio; ya está arriba.

Es importante que la app de los estudiantes no tengan acceso a borrar ni a eliminar contenido

# Clarificación

¿La AVACOM Student -  estudiante debería poder eliminar cursos? No, bajo nignuna circunstancia

¿AVACOM Student debería poder eliminar contenido? No, AVACOM Student solo puede ver cuando el contenido no se encuentra disponible tal cuál cómo lo hace AVACOM OPS Master

¿EL estudiante también debería enterarse en la pantalla principal que un contenido fue eliminado? Sí, pero con un mensaje diferente, diciendo contenido no disponible

# Plan

1. Eliminar todas las pantallas de AVACOM Student pero sin modificar la capacidad de comunicarse con la API que corre en 0.0.0.0:8000 en el mismo host o nodo de AVACOM OPS Master

2. Generar una pantalla dónde se solicita el nombre del estudiante y dirección del nodo principal o host dónde está el AVACOM OPS Master

3. El componente que solicita la dirección del nodo principal debe mostrar en rojo o verde si ha podido realizar la conexión. 

4. El componente que solicita la dirección del nodo principal debe mostrar un mensaje en color verde "Conectado" cuando se pueda conectar a la API del Nodo principal

5. Se genera una pantalla de resumen dónde los estudiantes pueden ver el contenido cómo se muestra en AVACOM Nodo principal y la Estructura del curso

6. El ejercicio es que AVACOM Student pueda ver cuando está disponible el contenido y cuando no

7. Debe existir un botón de actualizar para verificar que el contenido todavía esté disponible o no esté disponible


# Tareas

1. Eliminar todas las pantallas de AVACOM Student pero sin modificar la capacidad de comunicarse con la API que corre en 0.0.0.0:8000 en el mismo host o nodo de AVACOM OPS Master

2. Generar una pantalla dónde se solicita el nombre del estudiante y dirección del nodo principal o host dónde está el AVACOM OPS Master

3. El componente que solicita la dirección del nodo principal debe mostrar en rojo o verde si ha podido realizar la conexión. 

4. El componente que solicita la dirección del nodo principal debe mostrar un mensaje en color verde "Conectado" cuando se pueda conectar a la API del Nodo principal

5. Se genera una pantalla de resumen dónde los estudiantes pueden ver el contenido cómo se muestra en AVACOM Nodo principal y la Estructura del curso

6. El ejercicio es que AVACOM Student pueda ver cuando está disponible el contenido y cuando no

7. Debe existir un botón de actualizar para verificar que el contenido todavía esté disponible o no esté disponible


