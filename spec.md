# Feature Spec · Gestión de cursos instalables en AVACOM OPS

## 1. Objetivo

Construir un prototipo offline-first que permita instalar, consultar, utilizar y desinstalar cursos dentro de una AVACOM OPS Master, utilizando el backend local desarrollado con Django REST Framework y SQLite.

El prototipo debe demostrar especialmente que un curso puede:

1. Instalarse en una OPS (cómo funciona el instalador actualmente)
2. Quedar disponible para los estudiantes.
3. Ser utilizado por uno o varios estudiantes.
4. Registrar progreso, actividades, intentos y calificaciones.
5. Ser desinstalado posteriormente de la OPS.
6. Dejar de aparecer como contenido disponible para nuevas interacciones.
7. Mantener intacta toda la información histórica relacionada con los estudiantes.
8. Poder instalarse nuevamente sin perder ni duplicar el progreso existente.

Los cursos podrán importarse inicialmente mediante paquetes:

* SCORM.
* CMI5.

El formato del paquete no deberá modificar la lógica principal de disponibilidad del curso dentro de la OPS.

---

# 2. Arquitectura del prototipo

El sistema estará compuesto por tres componentes principales.

## 2.1 AVACOM OPS Master

Aplicación .NET MAUI ejecutada principalmente sobre Windows.

Representa el nodo principal del aula y se conecta al backend local.

Responsabilidades:

* Iniciar una clase.
* Detectar el backend local.
* Consultar cursos instalados.
* Instalar nuevos cursos.
* Desinstalar cursos.
* Mostrar la tabla m05_curso_host para ver los cambios en el prototipo
* Consultar cursos históricos.
* Servir contenido a los estudiantes.
* Consultar estudiantes asociados a cada curso.
* Monitorear dispositivos conectados.
* Visualizar el estado del contenido disponible en la OPS.

La OPS Master no debe considerar que eliminar físicamente un curso equivale a eliminar su información académica.

---

# 3. AVACOM Student

Aplicación .NET MAUI instalada en los dispositivos de estudiantes.

Responsabilidades:

* Descubrir la OPS dentro de la red local.
* Conectarse al backend local.
* Identificar al estudiante.
* Consultar los cursos que tiene asignados.
* Identificar cuáles cursos están disponibles actualmente en la OPS.
* Consultar secciones, lecciones y contenidos.
* Participar en actividades.
* Consultar calificaciones.
* Mantener visible el historial académico aunque un curso deje de estar instalado.

La aplicación Student debe diferenciar entre:

```text
Curso asignado al estudiante
```

y:

```text
Curso actualmente disponible en esta OPS
```

Estas condiciones son independientes.

---

# 4. Backend

## Tecnología

* Python.
* Django.
* Django REST Framework.
* SQLite.

El backend se ejecutará localmente dentro de la OPS.

Será la fuente de verdad para:

* Cursos.
* Versiones de cursos.
* Contenido instalado.
* Estudiantes.
* Matrículas.
* Progreso.
* Actividades.
* Intentos.
* Calificaciones.
* Estado de instalación de cada curso.

---

# 5. Modelo conceptual

La identidad académica del curso debe permanecer independiente de su instalación física.

El modelo debe entenderse de la siguiente manera:

```text
m05_curso
   │
   ├────────────── m05_curso_estudiante
   │                     │
   │                     └── relación histórica/académica
   │
   ├────────────── m05_curso_host
   │                     │
   │                     └── presencia física en la OPS
   │
   └── m05_seccion
          │
          └── m05_leccion
                 │
                 └── m05_leccion_item
```

La eliminación de un paquete de contenido únicamente deberá modificar:

```text
m05_curso_host
```

y eliminar, cuando corresponda, los archivos físicos asociados al paquete.

No deberá eliminar:

```text
m05_curso
m05_curso_estudiante
progreso
intentos
respuestas
notas
calificaciones
historial
```

---

# 6. Tabla principal del Feature: `m05_curso_host`

La tabla `m05_curso_host` representa la instalación de un curso determinado dentro de una OPS.

Su responsabilidad es responder:

> ¿Este curso y esta versión están físicamente disponibles en esta OPS?

No representa matrícula ni progreso académico.

## Campos mínimos propuestos

```text
id
host_id

curso_id
curso_version_id

formato_contenido
package_identifier
package_version

manifest_tipo
manifest_ref

package_ref
package_huella

presente_local
disponible_estudiante

instalado_en
retirado_en
verificado_en

creado_en
creado_por
secuencia
```

### `formato_contenido`

Valores iniciales:

```text
scorm_12
scorm_2004
cmi5
```

### `presente_local`

```text
1 = los archivos del curso están instalados en esta OPS
0 = los archivos no están instalados
```

### `disponible_estudiante`

```text
1 = el curso puede abrirse desde AVACOM Student
0 = el curso no puede abrirse actualmente
```

Ambos campos deben tratarse de manera independiente.

Ejemplo:

```text
presente_local = 1
disponible_estudiante = 0
```

puede representar un curso que acaba de instalarse pero todavía está siendo validado.

---

# 7. Regla principal de negocio

La regla central del prototipo será:

> Desinstalar contenido no significa eliminar el curso.

Formalmente:

```text
DESINSTALAR CURSO
        ≠
DELETE m05_curso
```

Una desinstalación debe producir:

```text
m05_curso_host.presente_local = 0
m05_curso_host.disponible_estudiante = 0
m05_curso_host.retirado_en = fecha_actual
```

Opcionalmente:

```text
eliminar archivos físicos del paquete
```

Pero deberán conservarse:

```text
m05_curso
m05_curso_estudiante
progreso del estudiante
actividades realizadas
intentos
respuestas
calificaciones
```

---

# 8. Estados funcionales del curso

Para el prototipo deben distinguirse al menos cuatro situaciones.

## Estado A · Curso instalado y disponible

```text
presente_local = 1
disponible_estudiante = 1
```

Comportamiento:

* Aparece en OPS Master como instalado.
* Aparece para los estudiantes asignados.
* Puede abrirse.
* Puede consumirse contenido.
* Puede registrar progreso.

---

## Estado B · Curso instalado pero no habilitado

```text
presente_local = 1
disponible_estudiante = 0
```

Comportamiento:

* Aparece en OPS Master.
* No puede abrirse desde Student.
* Puede encontrarse en proceso de instalación o validación.

---

## Estado C · Curso desinstalado con historial

```text
presente_local = 0
disponible_estudiante = 0
```

Comportamiento:

* No aparece en el catálogo de cursos disponibles.
* Sí puede aparecer en una sección de cursos históricos.
* El estudiante conserva progreso y calificaciones.
* No se permite abrir las lecciones físicas.
* El curso puede volver a instalarse.

---

## Estado D · Curso reinstalado

```text
presente_local = 1
disponible_estudiante = 1
```

Si `curso_id` corresponde al mismo curso previamente utilizado:

* No debe crearse una nueva matrícula.
* No debe duplicarse el estudiante.
* No debe reiniciarse automáticamente el progreso.
* No deben eliminarse calificaciones existentes.
* Debe recuperarse el progreso anterior.

---

# 9. Flujo 1 · Instalar un curso

## Actor

Administrador / profesor desde AVACOM OPS Master.

## Flujo

1. Usuario abre `Cursos`.
2. Selecciona `Agregar curso`.
3. Selecciona un archivo:

```text
.zip
```

4. Backend recibe el paquete.
5. Identifica el formato:

```text
SCORM
o
CMI5
```

6. Lee el descriptor correspondiente.

SCORM:

```text
imsmanifest.xml
```

CMI5:

```text
cmi5.xml
```

7. Obtiene el identificador del paquete.
8. Comprueba si el curso ya existe.
9. Comprueba si la versión ya existe.
10. Registra o actualiza `m05_curso`.
11. Registra la versión correspondiente.
12. Importa la estructura:

```text
Curso
   ↓
Secciones
   ↓
Lecciones
   ↓
Lesson Items
```

13. Registra la instalación en:

```text
m05_curso_host
```

14. Valida los archivos.
15. Cambia:

```text
presente_local = 1
disponible_estudiante = 1
```

16. El curso aparece en el catálogo disponible.

---

# 10. Flujo 2 · Estudiante inicia un curso

1. Student identifica al estudiante.
2. Consulta sus relaciones en:

```text
m05_curso_estudiante
```

3. Consulta disponibilidad en:

```text
m05_curso_host
```

4. Encuentra:

```text
presente_local = 1
disponible_estudiante = 1
```

5. Permite abrir el curso.
6. El estudiante navega:

```text
m05_curso
   ↓
m05_seccion
   ↓
m05_leccion
   ↓
m05_leccion_item
```

7. Se puede realizar un examen del curso.

Ejemplo:

```text
Matemáticas 6°

Unidad 1
    100%

Lección 1
    100%

Lección 2
    60%

Lección 3
    0%
```

---

# 11. Flujo 3 · Desinstalar un curso

## Actor

Usuario de AVACOM OPS Master.

## Acción

Selecciona:

```text
Desinstalar curso
```

El sistema debe mostrar una advertencia:

```text
El contenido será eliminado de esta OPS.

Los estudiantes, progreso, calificaciones e historial
asociados al curso serán conservados.
```

Al confirmar:

1. Localizar `m05_curso_host`.
2. Cambiar:

```text
presente_local = 0
disponible_estudiante = 0
```

3. Registrar:

```text
retirado_en
```

4. Eliminar archivos físicos cuando aplique.
5. Mantener el registro `m05_curso_host`.
6. Mantener `m05_curso`.
7. Mantener `m05_curso_estudiante`.
8. Mantener progreso.
9. Mantener intentos.
10. Mantener respuestas.
11. Mantener calificaciones.

El sistema no debe ejecutar cascadas destructivas relacionadas con historial académico.

---

# 12. Flujo 4 · Estudiante consulta después de una desinstalación

Supongamos:

```text
Estudiante: Juan
Curso: Matemáticas 6
Progreso: 62%
```

El curso es desinstalado.

Cuando Juan vuelve a consultar su información:

```text
Matemáticas 6
Progreso: 62%
Estado: No disponible en esta OPS
```

Puede consultar:

* Nombre del curso.
* Estado.
* Progreso alcanzado.
* Nota obtenida.
* Historial.

No puede:

* Abrir nuevas lecciones.
* Descargar recursos eliminados.
* Iniciar nuevas actividades.

---

# 13. Flujo 5 · Reinstalar un curso

El administrador vuelve a importar el mismo paquete.

El backend identifica:

```text
package_identifier
curso_id
curso_version_id
```

Si corresponde al mismo contenido:

```text
UPDATE m05_curso_host

presente_local = 1
disponible_estudiante = 1
retirado_en = NULL
```

No debe crear otro:

```text
m05_curso
```

ni duplicar:

```text
m05_curso_estudiante
```

Cuando Juan vuelve a entrar:

```text
Matemáticas 6
Progreso: 62%
Estado: Disponible
```

y puede continuar desde donde estaba.

---

# 14. Pantallas · AVACOM OPS Master

## Pantalla 1 · Cursos instalados

Mostrar únicamente:

```text
presente_local = 1
```

Cada tarjeta puede mostrar:

* Nombre.
* Versión.
* Formato.
* Estado.
* Número de estudiantes relacionados.
* Fecha de instalación.
* Tamaño aproximado.
* Botón `Abrir`.
* Botón `Desinstalar`.

Ejemplo:

```text
Matemáticas 6°
SCORM 2004

Versión 2
12 estudiantes
Instalado

[ Abrir ] [ Desinstalar ]
```

---

# 15. Pantalla 2 · Historial de cursos

Mostrar cursos conocidos por la OPS independientemente de su disponibilidad actual.

Ejemplo:

```text
Matemáticas 6°
Disponible
12 estudiantes


Ciencias 6°
No instalado
8 estudiantes
4 tienen progreso registrado


Historia 7°
No instalado
16 estudiantes
Curso finalizado
```

Esta pantalla permite demostrar que la información académica permanece aunque el contenido haya sido retirado.

---

# 16. Pantalla 3 · Agregar curso

Título:

```text
Agregar contenido
```

Permitir seleccionar:

```text
SCORM
CMI5
```

o permitir detección automática.

Elementos:

* Seleccionar archivo.
* Nombre detectado.
* Formato detectado.
* Identificador.
* Versión.
* Cantidad de secciones.
* Cantidad de lecciones.
* Cantidad de recursos.
* Botón `Instalar`.

Antes de guardar:

```text
Validando paquete...
```

Después:

```text
Curso instalado correctamente.
```

---

# 17. Pantalla 4 · Detalle de curso

Mostrar:

```text
Matemáticas 6°

Formato
SCORM 2004

Versión
2.0

Estado
Instalado

Estudiantes
12
```

Mostrar árbol:

```text
Unidad 1
├── Lección 1
├── Lección 2
└── Lección 3

Unidad 2
├── Lección 4
└── Lección 5
```

Y estudiantes:

```text
Juan
62%

Laura
100%

Pedro
25%
```

---

# 18. Pantallas · AVACOM Student

## Mis cursos

Separar visualmente:

### Disponibles

```text
Matemáticas
62%
[Continuar]
```

### No disponibles actualmente

```text
Ciencias
45%

Contenido no disponible actualmente
en esta OPS.
```

El registro no debe desaparecer.

---

# 19. API mínima del prototipo

## Cursos disponibles

```text
GET /api/courses/available/
```

## Cursos históricos

```text
GET /api/courses/history/
```

## Detalle

```text
GET /api/courses/{course_id}/
```

## Instalar

```text
POST /api/course-packages/install/
```

Debe aceptar inicialmente:

```text
SCORM
CMI5
```

## Desinstalar

```text
POST /api/courses/{course_id}/uninstall/
```

No debe hacer:

```text
DELETE /api/courses/{course_id}/
```

## Reinstalar

Puede utilizarse nuevamente:

```text
POST /api/course-packages/install/
```

y el backend deberá detectar que el curso ya existe.

## Cursos del estudiante

```text
GET /api/students/{student_id}/courses/
```

Respuesta conceptual:

```json
{
  "course_id": "course-001",
  "name": "Matemáticas 6",
  "progress": 0.62,
  "installed": false,
  "available": false
}
```

---

# 20. Reglas de persistencia

## Nunca borrar automáticamente

La desinstalación nunca debe borrar:

```text
m05_curso
m05_curso_estudiante
progreso
intentos
respuestas
calificaciones
```

## Se puede eliminar

Contenido físico:

```text
HTML
CSS
JavaScript
PDF
video
audio
imágenes
otros recursos del paquete
```

siempre que la metadata necesaria para reconocer el curso permanezca registrada.

---

# 21. Escenario principal de demostración

El prototipo debe permitir ejecutar esta prueba completa.

### Paso 1

OPS inicialmente sin el curso:

```text
Matemáticas 6
```

### Paso 2

Instalar:

```text
matematicas6.zip
```

Resultado:

```text
presente_local = 1
disponible_estudiante = 1
```

### Paso 3

Asignar Juan al curso.

### Paso 4

Juan completa:

```text
Lección 1 → 100%
Lección 2 → 50%
Quiz → 80/100
```

Progreso general:

```text
62%
```

### Paso 5

Desde OPS Master:

```text
Desinstalar Matemáticas 6
```

Resultado:

```text
presente_local = 0
disponible_estudiante = 0
```

### Paso 6

Juan vuelve a iniciar sesión.

Debe observar:

```text
Matemáticas 6
62%

No disponible actualmente
```

### Paso 7

Verificar en base de datos:

```text
m05_curso                     EXISTE
m05_curso_estudiante          EXISTE
progreso de Juan              EXISTE
nota del quiz                 EXISTE

m05_curso_host
presente_local                0
```

### Paso 8

Reinstalar `matematicas6.zip`.

Resultado:

```text
presente_local = 1
disponible_estudiante = 1
```

### Paso 9

Juan abre nuevamente el curso.

Debe observar:

```text
Progreso: 62%
Quiz: 80/100

Continuar desde Lección 2
```

---

# 22. Criterios de aceptación

## AC-01 · Instalación

Dado un paquete SCORM o CMI5 válido, cuando se instala en la OPS, entonces deberá crearse o actualizarse su registro de presencia en `m05_curso_host`.

## AC-02 · Disponibilidad

Un curso solo podrá abrirse desde Student cuando:

```text
presente_local = 1
AND
disponible_estudiante = 1
```

## AC-03 · Desinstalación

Cuando se desinstala un curso, `m05_curso_host.presente_local` deberá cambiar a `0`.

## AC-04 · Persistencia académica

La desinstalación no deberá eliminar relaciones existentes entre estudiantes y cursos.

## AC-05 · Persistencia de progreso

El progreso alcanzado antes de la desinstalación deberá conservarse.

## AC-06 · Persistencia de notas

Las notas, respuestas e intentos deberán permanecer después de desinstalar.

## AC-07 · Ocultamiento

Un curso desinstalado no deberá aparecer dentro del listado de cursos disponibles.

## AC-08 · Historial

Un curso desinstalado sí deberá poder aparecer en el historial del estudiante.

## AC-09 · Reinstalación

Al instalar nuevamente el mismo curso, deberá recuperarse la relación histórica existente.

## AC-10 · No duplicación

Reinstalar un curso no deberá generar duplicados de:

```text
curso
estudiante
matrícula
progreso
calificación
```

## AC-11 · Independencia de formato

La lógica de `m05_curso_host` deberá funcionar independientemente de que el paquete sea:

```text
SCORM
CMI5
```

## AC-12 · Funcionamiento offline

Todo el flujo deberá funcionar sin conexión a Internet mientras OPS Master, Student y backend se encuentren dentro de la misma red local.

---

# 23. Fuera de alcance del primer prototipo

Para mantener el POC pequeño, inicialmente no es necesario implementar:

* Sincronización entre múltiples OPS.
* LRS CMI5 completo.
* Implementación completa de xAPI.
* Todas las reglas de sequencing de SCORM 2004.
* Sincronización con servicios cloud.
* Actualizaciones automáticas de paquetes.
* Resolución avanzada de conflictos entre versiones.
* DRM.
* Firma criptográfica completa.

El objetivo inicial es demostrar correctamente:

```text
INSTALAR
   ↓
USAR
   ↓
REGISTRAR PROGRESO
   ↓
DESINSTALAR
   ↓
CONSERVAR HISTORIAL
   ↓
REINSTALAR
   ↓
CONTINUAR
```

---

# 24. Resultado esperado del prototipo

Al finalizar el prototipo deberá poder demostrarse que la disponibilidad física de un contenido y la información académica del estudiante son conceptos desacoplados.

La arquitectura debe cumplir:

```text
Contenido físico
      │
      ▼
m05_curso_host
      │
      │ puede desaparecer
      ▼

────────────────────────

Información académica
      │
      ├── m05_curso
      ├── m05_curso_estudiante
      ├── progreso
      ├── intentos
      └── notas

      permanece
```

La prueba será considerada exitosa si un estudiante puede utilizar parcialmente un curso, este puede ser retirado de la OPS y posteriormente reinstalado manteniendo exactamente el progreso académico alcanzado previamente.
