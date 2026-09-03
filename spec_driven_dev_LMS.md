# Desarrollo dirigido por especificación · AVACOM

| Campo | Valor |
|---|---|
| Documento | `spec_driven_dev.md` |
| Versión | 1.0 |
| Fecha | 2026-09-01 |
| Método | Spec Kit (`/speckit.*`) |
| Caso aplicado | Conectar el consumo de contenido al curso |
| Estado | Prototipo |

---

## Parte I · El método

El desarrollo dirigido por especificación invierte el orden habitual: en vez de escribir código y
documentarlo después, se escribe la intención primero y el código se deriva de ella. La
especificación deja de ser un documento muerto y pasa a ser la fuente que gobierna la
implementación.

Seis fases, cada una con su comando:

| # | Fase | Comando | Qué produce | Qué **no** hace |
|---|---|---|---|---|
| 1 | **Constitución** | `/speckit.constitution` | Reglas no negociables del proyecto | No describe ninguna función |
| 2 | **Especificación** | `/speckit.specify` | Qué se construye y qué problema resuelve | **No** habla de tecnología |
| 3 | **Clarificación** | — | Preguntas que resuelven ambigüedades | No inventa respuestas |
| 4 | **Plan** | `/speckit.plan` | Diseño técnico: arquitectura y dependencias | No parte en tareas |
| 5 | **Tareas** | `/speckit.tasks` | Lista ordenada y atómica | No escribe código |
| 6 | **Implementación** | `/speckit.implement` | El código, paso a paso | No redefine el alcance |


### Por qué la clarificación no es opcional

Es la única fase sin comando, y la que más veces se salta. Su trabajo es convertir supuestos
silenciosos en decisiones explícitas. Un supuesto que no se pregunta no desaparece: se implementa.

---

## Parte II · Caso aplicado

### Contexto real de partida

Lo que ya existe en este repositorio, y que la propuesta debe respetar:

* **El componente de contenido no es el LMS.** El esquema lo declara literalmente: el LMS lleva
  personas, grupos, matrículas, intentos y calificaciones, tiene su propio esquema y lo desarrolla
  otro equipo. Este componente sabe qué material hay instalado, sabe abrirlo y apunta que se abrió.
* **El índice es una proyección, no una fuente de verdad.** `m04_indice_elemento` se reconstruye
  escaneando los paquetes y da exactamente lo mismo. El manifiesto de cada paquete manda.
* **El repaso no genera nota.** `m08_repaso_sesion` deja constancia de que se abrió algo y cuánto
  tiempo. Nada más.
* **`persona_id` admite nulo a propósito.** La biblioteca es abierta: alguien puede consultar
  material sin identificarse, y en preescolar no hay con qué identificarse.
* **Toda tabla lleva `secuencia`**, un contador monótono por tabla. Hoy solo se escribe; es el
  punto de enganche natural para un feed incremental.
* **Ya hay un servidor local en el nodo**, `ServidorDeMedios`: escucha solo en 127.0.0.1, con
  puerto asignado por el sistema y fichas aleatorias de 128 bits. Es el precedente a seguir.
* **El aula funciona sin conexión.** Es requisito declarado, no una degradación aceptable.
* **La clave de respuesta no sale del manifiesto cifrado.** Hay una prueba dedicada que lo verifica.
* **Este el prototype-lms-v03** Este es el prototipo del LMS y debe poder consumir el contenido de 
    la otra aplicación, la otra aplicación recibirá el nombre de AVACOM-Contenido
* **Este el prototype-lms-v03 tiene dos aplicaciones** El proyecto tiene dos aplicaciones, una 
    llamada AVACOM OPS Master que es quién contiene el software que contiene la API de AVACOM-Contenido
    y a la vez el AVACOM OPS Master que cuanta con su propia API.
* **Sobre AVACOM OPS Master.** Es la aplicación que maneja el profesor dentro de la OPS, es un ejecutale
    realizado sobre MAUI .NET C# que se encarga las funciones del frontend.
* **Backend de AVACOM OPS Master** Es una API que debería consumir los recursos del contenido y
    administrar la información del LMS, administra también conexiones en web sockets con las aplicaciones
    que abren los estudiantes desde sus tablets o desde sus computadores. 
* **AVACOM Student** Es la aplicación que abren los estudiantes, este se encuentra dentro de la misma
    red LAN del AVACOM OPS Master.



---

## Fase 1 · Constitución

`/speckit.constitution`

> Reglas que la IA debe respetar siempre, en cualquier tarea de este proyecto. No se negocian por
> conveniencia de una funcionalidad concreta.

### C-1 · Frontera de dominio

El componente de contenido **no** almacena personas, matrículas, intentos ni calificaciones. Esos
datos pertenecen al LMS. Ninguna funcionalidad nueva puede crear en el nodo una segunda copia
autoritativa de datos del LMS.

**Corolario operativo:** si una tabla nueva necesita una clave foránea a una tabla del LMS, la
tabla nueva está en el sitio equivocado.

### C-2 · El manifiesto manda

Cualquier proyección del catálogo debe poder reconstruirse desde los paquetes instalados. En cuanto
una proyección contenga un dato que no venga de ningún paquete, deja de ser reconstruible y se
convierte en un segundo catálogo que hay que sincronizar a mano.

### C-3 · El repaso no califica

Abrir material por cuenta propia no genera intento, no genera calificación y no alimenta el
dominio. Ninguna integración puede convertir un consumo de repaso en una nota.

### C-4 · Superficie de red mínima

Todo servicio que escuche en el nodo dentro del mismo es:

* escucha **solo en 127.0.0.1**;
* usa puerto asignado por el sistema, distinto en cada arranque, salvo que un consumidor externo
  exija lo contrario y quede justificado;
* expone el mínimo de verbos necesarios;
* autentica cada llamada, aunque sea local.

En el nodo principal solo puede correr el backend en:
* escucha y envía en el **solo en 0.0.0.0** puerto **8000**
* El backend del AVACOM OPS Master debe ser el único que es accesible desde la LAN
* Para propositos del prototipo es necesario mostrar las conexiones activas en web sockets

Cuanto menos código escuche en un puerto, menos superficie hay que revisar.

### C-5 · La clave de respuesta no sale del manifiesto

Ni por la API, ni en registros, ni en trazas, ni en mensajes de error. La calificación se resuelve
donde vive la clave o donde vive el dominio, nunca transportando la clave a un tercer sitio.

### C-6 · Sin conexión es el caso normal

El aula funciona con la red caída. Toda comunicación con el LMS es asíncrona, con cola durable y
reintento. Ninguna función del aula puede quedar bloqueada esperando al LMS.

### C-7 · Entrega idempotente

Todo mensaje hacia el LMS lleva identificador estable. Reenviar un mensaje ya procesado no puede
duplicar un intento ni alterar una nota.

### C-8 · Convenciones del repositorio

* Nombres de código, tablas y rutas en español, como el resto del proyecto.
* Prefijo de tabla por módulo (`m04_`, `m08_`, …).
* El módulo de los cursos tiene el prefijo `m05_`
* Toda tabla nueva lleva `creado_en`, `creado_por` y `secuencia`.
* Los comentarios explican **por qué**, no qué. El qué ya está en el código.
* Nada se da por terminado sin ejecutarse. `probar-todo.ps1` debe seguir pasando entero.

### C-9 · Sin dependencias nuevas sin justificación

Cada paquete añadido es superficie que alguien tendrá que mantener y auditar. Se justifica en el
plan o no entra.

---

## Fase 2 · Especificación

`/speckit.specify`

> Qué se quiere construir y qué problema resuelve. **Sin decisiones técnicas.**

### Problema

Hoy el equipo del aula sabe qué contenido tiene instalado y registra qué se abrió, pero esa
información se queda en el equipo. El LMS, que es quien lleva el curso, no se entera de nada:
no sabe qué material está realmente disponible en esa aula, y no recibe los resultados de las
evaluaciones que los alumnos resuelven en la pantalla.

La consecuencia práctica: un docente califica en la pantalla y luego vuelve a introducir las notas
a mano en el LMS. Y un coordinador que mira el LMS no puede saber si el material que planificó está
instalado en el aula o no.

El prototype LMS debe conectarse a la aplicación de AVACOM_CONTENIDO_VERSION02 para consumir el contenido
traerselo y revisar qué información hay para consumir. 

### Qué se quiere

Que el equipo del aula y el LMS estén de acuerdo sobre dos cosas, sin intervención manual:

1. **Qué material hay disponible** en ese equipo, en cada momento.
2. **Qué pasó con el curso**: quién resolvió qué evaluación, con qué resultado, y qué nota sale de
   ahí - esto queda dentro del LMS
3. **Qué el LMS guarde la información** aunque el contenido sea eliminado, el LMS debe mantener el registro
    de notas de los estudiantes en el curso
4. **El curso guarda información asociado a las actividades y exámenes** no guarda información del contenido

5. **El curso está dentro del LMS** esta es la tabla que resuelve la información del curso


### Para quién

| Persona | Qué gana |
|---|---|
| **Docente** | Califica una vez. Lo que hace en la pantalla aparece en el LMS |
| **Coordinador** | Ve desde el LMS qué aulas tienen instalado el material que planificó |
| **Alumno** | Su trabajo en la pantalla cuenta para el curso |
| **Técnico de soporte** | Ve si un aula está sincronizada y desde cuándo, sin ir al aula |

### Comportamiento esperado

* El material disponible en el aula se refleja en el LMS **sin que nadie lo declare a mano**. Si un
  paquete se instala, se desactiva, o el administrador lo deshabilita por política, el LMS lo sabe.
* Cuando un alumno resuelve una evaluación identificándose, el resultado llega al LMS como parte de
  su curso.
* Cuando alguien consulta material **sin identificarse, o solo por repasar**, eso no produce nota
  ni intento. Queda como uso, y ahí se acaba.
* Con la red caída, el aula sigue funcionando igual. Lo que no se pudo enviar se envía al volver la
  conexión, sin duplicar nada ni perder nada.
* Un técnico puede saber, desde el LMS, cuándo fue la última vez que un aula habló y qué tiene
  pendiente.

### Fuera de alcance

* Cambiar el formato de los paquetes o la criptografía.
* Que el LMS distribuya contenido. Esa tubería ya existe y no se toca.
* Sincronizar personas o matrículas hacia el aula, más allá de lo mínimo para identificar a quien
  resuelve.
* Calificación automática de respuesta abierta.

### Criterios de aceptación

| # | Criterio |
|---|---|
| A-1 | Instalar un paquete en el aula hace que aparezca en el LMS sin acción manual |
| A-2 | Deshabilitar contenido por política se refleja en el LMS |
| A-3 | Una evaluación resuelta con persona identificada llega al LMS con su resultado |
| A-4 | Una sesión de repaso **no** produce intento ni nota en el LMS |
| A-5 | Con la red caída, resolver una evaluación funciona; al volver la red, llega una sola vez |
| A-6 | Reenviar el mismo resultado no duplica el intento ni cambia la nota |
| A-7 | La clave de respuesta no aparece en ninguna respuesta de la API ni en ningún registro |
| A-8 | El LMS puede consultar el estado de sincronización de un aula |
| A-9 | El LMS no pierde la información cuando el contenido es eliminado |

---

## Fase 3 · Clarificación

> La IA analiza la especificación y pregunta antes de avanzar. Cada pregunta lleva la
> recomendación por defecto; lo marcado ⚠ **debe** confirmarse antes de la Fase 4.

### Q-1  ¿Dónde se califica?

La clave de respuesta vive en el manifiesto cifrado y no puede salir de ahí (C-5). Tres opciones:

| Opción | Dónde | Consecuencia |
|---|---|---|
| **a** | En el nodo, dentro del componente de contenido | La clave no viaja. El nodo pasa a producir un dato de dominio |
| **b** | En el LMS, que recibe las respuestas crudas | El LMS necesitaría la clave: **rompe C-5** |
| **c** | En el nodo, pero el veredicto lo confirma el LMS | Dos fuentes de verdad para la misma nota |

**Recomendación: (a).** Es la única que respeta C-5 sin duplicar autoridad. El nodo emite un
*resultado* (acertado/fallado y puntaje), no la respuesta ni la clave. La nota final del curso
—ponderaciones, recuperaciones, redondeo— sigue siendo del LMS. 

Recuerda que el nodo principal es AVACOM OPS Master y su respectivo backend

### Q-2 ¿Qué identifica a la persona en el aula?

`persona_id` admite nulo a propósito. Para que un intento llegue al LMS hace falta identidad.

**Recomendación:** que el LMS emita un identificador opaco de corta vida que el aula presenta al
enviar. El aula **no** guarda un padrón de alumnos. Sin identidad, la interacción es repaso y no
genera nota (respeta C-1 y C-3).

Cómo estamos a modo prototipo todavía no se cuenta con una autenticación por lo que 

### Q-3 ⚠ ¿Cuál es el contrato del LMS?

El LMS es Django Rest Framework, no cuenta con autenticación todavía debido que está a modo de
prototipo y pruebas de constantes, por lo que la autenticación aún no está definida. Pero
sí está definido los modelos de curso, actividades y lecciones. Esto está en ./backend


### Q-5 ¿Una API o dos?

El enunciado pide dos. Se sostiene, y no por simetría: son dos ciclos de vida distintos. La de
contenido no conoce la red externa ni la identidad; la de curso no sabe descifrar nada. Separarlas
mantiene la frontera de C-1 en el código y no solo en la documentación. 

**Recomendación:** dos servicios, dos procesos.


---

## Fase 4 · Plan

`/speckit.plan`

> Diseño técnico. Asume Q-1(a), Q-2, Q-4, Q-5 y Q-8 según la recomendación. **Q-3 sigue abierta**:
> el adaptador del LMS se diseña detrás de una interfaz para no bloquear el resto.

### 4.1 Arquitectura

```
  EQUIPO MAESTRO DEL AULA (nodo)                          FUERA DEL AULA
  ┌──────────────────────────────────────────┐
  │  App MAUI (Avacom.Biblioteca.App)        │
  │        │                                 │
  │        ▼                                 │
  │  Avacom.Contenido  ──►  indice.db        │
  │        │                                 │
  │  ┌─────▼──────────────────┐              │
  │  │  API DE CONTENIDO      │  :127.0.0.1  │
  │  │  Avacom.Contenido.Api  │              │
  │  │  · qué hay instalado   │              │
  │  │  · feed de cambios     │              │
  │  │  · resultado evaluación│              │
  │  └─────┬──────────────────┘              │
  │        │ HTTP local + ficha              │
  │  ┌─────▼──────────────────┐              │      ┌──────────────┐
  │  │  API DE CURSO          │──────────────┼─────►│  LMS Django  │
  │  │  Avacom.Curso.Api      │   red, async │      │  intentos    │
  │  │  · bandeja de salida   │              │      │  notas       │
  │  │  · identidad           │              │      └──────────────┘
  │  │  · adaptador LMS       │              │
  │  └────────────────────────┘  curso.db    │
  └──────────────────────────────────────────┘
```

**Regla de dependencia:** la API de contenido no conoce la existencia del LMS. La de curso sí
conoce a la de contenido. La flecha nunca se invierte — es C-1 hecha código.

### 4.2 API de contenido — `Avacom.Contenido.Api`

Envuelve lo que ya hace `Avacom.Contenido`. No duplica lógica.

| Verbo | Ruta | Devuelve |
|---|---|---|
| `GET` | `/contenido/disponible` | Proyección de `v_contenido_disponible`, ya filtrada por política |
| `GET` | `/contenido/taxonomia?padre=` | Árbol curricular |
| `GET` | `/contenido/paquetes` | Paquetes instalados, estado y verificación de firma |
| `GET` | `/contenido/cambios?desde=<secuencia>` | **Feed incremental.** Cambios con `secuencia` mayor |
| `GET` | `/contenido/estado` | Contadores y antigüedad de la proyección |
| `POST` | `/evaluacion/{ref}/resultado` | Recibe respuestas, califica **en el nodo**, devuelve veredicto |

Notas de diseño:

* **`/contenido/cambios` es el corazón de "constantemente revisando".** No hay sondeo de disco: la
  columna `secuencia`, que ya existe en todas las tablas, se usa como marca de agua. El consumidor
  guarda la última que procesó y pide lo posterior. Barato, ordenado y reanudable tras un corte.
* **`/evaluacion/{ref}/resultado` es el único punto donde se toca la clave de respuesta**, y no la
  devuelve: compara y emite veredicto. Cumple C-5 y materializa Q-1(a).
* Reconciliación periódica: compara `m04_indice_estado` con los paquetes en disco y marca
  `incompleto` si discrepan. Es la red de seguridad de Q-4, no el mecanismo principal.

### 4.3 API de curso — `Avacom.Curso.Api`

Es donde vive todo lo que el componente de contenido tiene prohibido saber.

| Pieza | Responsabilidad |
|---|---|
| **Bandeja de salida** | Cola durable en `curso.db`. Cada mensaje con identificador estable (C-7) |
| **Despachador** | Reintento con espera creciente. Sin red, acumula (C-6) |
| **Adaptador LMS** | Interfaz `IPuenteLms`. **La única pieza que cambia cuando se cierre Q-3** |
| **Identidad** | Canjea el identificador opaco del LMS. Sin identidad → no hay intento (Q-2) |
| **Seguidor de contenido** | Consume `/contenido/cambios` y traduce a mensajes de disponibilidad |
| **Estado** | Expone al LMS última sincronización y pendientes (criterio A-8) |

Esquema propuesto, prefijo `m09_` ⚠ *a confirmar con el equipo del LMS*:

| Tabla | Para qué |
|---|---|
| `m09_salida` | Mensajes pendientes: tipo, cuerpo, intentos, estado, `secuencia` |
| `m09_marca_agua` | Última `secuencia` procesada por origen |
| `m09_envio` | Historial de entregas, para diagnosticar sin abrir la cola |

Ninguna guarda personas, matrículas ni notas: guardan **mensajes sobre** ellas, en tránsito. Es la
diferencia entre una cola y una copia (C-1).

### 4.4 Seguridad

Sigue el precedente de `ServidorDeMedios`:

* Ambas escuchan **solo en 127.0.0.1**, con puerto del sistema.
* **La API de contenido no acepta conexiones anónimas ni de la app.** Ficha compartida, generada al
  arranque, entregada por el mecanismo que se decida en tareas.
* Solo los verbos de la tabla. Nada más.
* Hacia el LMS: TLS y la autenticación que resuelva Q-3.
* **Nunca** se registra ni se devuelve `clave_respuesta` (C-5). Hay que probarlo, no afirmarlo.

### 4.5 Aislamiento de red de Windows

Restricción real y ya documentada en el `.csproj`: una aplicación **empaquetada** corre dentro del
aislamiento de red de Windows, que bloquea las conexiones al propio equipo salvo exención con
`CheckNetIsolation` en cada máquina. Por eso la app va sin empaquetar.

**Los dos servicios nuevos heredan esa restricción.** Como servicios de Windows sin empaquetar
(Q-8) no les aplica, pero si alguien decide empaquetar la aplicación más adelante, la comunicación
local deja de funcionar. Queda anotado aquí para que no se descubra en un aula.

### 4.6 Dependencias (C-9)

| Dependencia | Justificación |
|---|---|
| ASP.NET Core minimal API | Ya viene en el SDK de .NET 10. Cero dependencias nuevas |
| `Microsoft.Data.Sqlite` | Ya en uso por `Avacom.Contenido` |
| `Microsoft.Extensions.Hosting.WindowsServices` | Necesaria para Q-8 |
| Cliente HTTP | `HttpClient` del framework |

Ninguna dependencia externa nueva. Es una decisión, no una casualidad: cada paquete es superficie
que alguien tendrá que auditar.

### 4.7 Riesgos

| Riesgo | Mitigación |
|---|---|
| Q-3 sin cerrar bloquea la integración real | `IPuenteLms` con implementación simulada. Todo lo demás avanza |
| La cola crece sin límite sin red | Retención y aviso al superar umbral (Q-7) |
| El nodo calificando erosiona C-1 | El nodo emite **resultado**, nunca nota de curso. Probarlo |
| Reloj del aula desajustado | Marcas de tiempo del nodo + de recepción; el LMS resuelve conflictos |
| Dos servicios más que mantener | Un solo binario por servicio, sin instalador nuevo |

---

## Fase 5 · Tareas

`/speckit.tasks`

Atómicas, ordenadas, con dependencia explícita. Cada una debe poder verificarse sola.

### Bloque 0 · Desbloqueo

| id | Tarea | Dep. | Hecho cuando |
|---|---|---|---|
| T-01 | Cerrar Q-1, Q-2 y Q-3 con el equipo del LMS | — | Las tres decisiones por escrito |
| T-02 | Fijar prefijo de módulo y nombres de tabla | T-01 | Confirmado con el LMS |

### Bloque 1 · API de contenido

| id | Tarea | Dep. | Hecho cuando |
|---|---|---|---|
| T-03 | Proyecto `Avacom.Contenido.Api`, escucha en 127.0.0.1, puerto del sistema | T-02 | Responde y no es alcanzable desde otra máquina |
| T-04 | Ficha de autenticación al arranque; sin ficha, 404 | T-03 | Prueba: sin ficha no hay respuesta útil |
| T-05 | `GET /contenido/disponible` sobre `v_contenido_disponible` | T-04 | Coincide con lo que muestra la app |
| T-06 | `GET /contenido/taxonomia` y `/contenido/paquetes` | T-05 | Árbol y paquetes completos |
| T-07 | Feed `GET /contenido/cambios?desde=` con `secuencia` | T-05 | Dos llamadas seguidas no repiten ni pierden |
| T-08 | `GET /contenido/estado` con contadores y antigüedad | T-05 | Refleja `m04_indice_estado` |
| T-09 | Reconciliación periódica índice ↔ disco | T-08 | Un paquete alterado por fuera marca `incompleto` |
| T-10 | `POST /evaluacion/{ref}/resultado`: califica en el nodo | T-04 | Veredicto correcto para los 8 reactivos de grado 8 |
| T-11 | **Prueba de fuga**: `clave_respuesta` no sale por ninguna ruta ni registro | T-10 | Barrido de respuestas y trazas, sin coincidencias |

### Bloque 2 · API de curso

| id | Tarea | Dep. | Hecho cuando |
|---|---|---|---|
| T-12 | Proyecto `Avacom.Curso.Api` + `curso.db` con `m09_*` | T-02 | Esquema se aplica solo al arrancar |
| T-13 | Bandeja de salida con identificador estable | T-12 | Encolar dos veces el mismo mensaje deja uno |
| T-14 | Despachador con reintento y espera creciente | T-13 | Sin red acumula; con red vacía la cola |
| T-15 | Interfaz `IPuenteLms` + implementación simulada | T-12 | Los bloques 2 y 3 avanzan sin el LMS real |
| T-16 | Seguidor de `/contenido/cambios` con marca de agua | T-07, T-13 | Reiniciar el servicio no repite ni pierde cambios |
| T-17 | Traducir cambio de contenido a mensaje de disponibilidad | T-16 | Instalar un paquete encola un mensaje |
| T-18 | Identidad: canje del identificador opaco | T-01 | Sin identidad no se crea intento |
| T-19 | Traducir resultado de evaluación a intento de curso | T-10, T-18 | Un resultado identificado encola un intento |
| T-20 | `GET /curso/estado` para el LMS | T-14 | Última sincronización y pendientes |
| T-21 | Retención y aviso de cola por umbral | T-14 | Superar el umbral avisa, no rompe |

### Bloque 3 · Integración y verificación

| id | Tarea | Dep. | Hecho cuando |
|---|---|---|---|
| T-22 | Adaptador real contra el LMS | T-15, Q-3 | Un intento aparece en el LMS |
| T-23 | Ambos como servicios de Windows | T-03, T-12 | Sobreviven a cerrar la aplicación |
| T-24 | Prueba de extremo a extremo **con la red caída** | T-19, T-22 | A-5 y A-6 se cumplen |
| T-25 | Prueba: **repaso no genera nota** | T-19 | A-4. Es C-3 hecha prueba |
| T-26 | Etapas nuevas en `probar-todo.ps1` | T-24, T-25 | El guion sigue pasando entero |
| T-27 | Documentar el contrato de ambas APIs | T-22 | Otro equipo lo implementa sin preguntar |

**Camino crítico:** T-01 → T-02 → T-03 → T-04 → T-10 → T-19 → T-22 → T-24.
T-01 bloquea todo. Es donde hay que empezar.

---

## Fase 6 · Implementación

`/speckit.implement`

Ejecuta las tareas en orden. No redefine el alcance: si aparece algo que no está en el plan,
vuelve a la fase que corresponda en vez de improvisar.

### Reglas de ejecución

1. **Una tarea, una entrega verificable.** No se avanza con la anterior a medias.
2. **Se ejecuta lo que se escribe.** Nada se da por terminado sin correrlo (C-8).
3. **`probar-todo.ps1` pasa entero** después de cada bloque. Si no pasa, eso es el trabajo.
4. **Las pruebas de frontera no se posponen.** T-11 y T-25 son C-5 y C-3 hechas prueba: sin ellas,
   las reglas son solo un documento.
5. **Un cambio de contrato vuelve a la Fase 4.** Si el LMS pide algo que el plan no previó, se
   replantea el plan, no se parchea el código.

### Orden sugerido

| Hito | Tareas | Resultado demostrable |
|---|---|---|
| **H-1** | T-01 – T-02 | Decisiones cerradas. Sin esto no se escribe código |
| **H-2** | T-03 – T-09 | El nodo publica qué contenido tiene, con feed incremental |
| **H-3** | T-10 – T-11 | Califica en el nodo, y está probado que la clave no se escapa |
| **H-4** | T-12 – T-17 | La API de curso sigue el contenido y encola, aún sin LMS |
| **H-5** | T-18 – T-21 | Intentos encolados con identidad; estado visible |
| **H-6** | T-22 – T-27 | Extremo a extremo contra el LMS real, con red caída incluida |

H-2, H-3 y H-4 no dependen del LMS. Se pueden construir y demostrar mientras Q-3 sigue abierta —
que es justamente el motivo de meter `IPuenteLms` en el plan.

---

## Anexo · Cómo se usaría esto en la práctica

```
/speckit.constitution   → Parte II, Fase 1
/speckit.specify        → Fase 2
                          (la IA pregunta: Fase 3. Contestar antes de seguir)
/speckit.plan           → Fase 4
/speckit.tasks          → Fase 5
/speckit.implement      → Fase 6, tarea a tarea
```

La constitución se escribe una vez y gobierna todo lo que venga después. Las cinco fases
restantes se repiten por cada funcionalidad.

**Dos avisos que valen más que el resto del documento.** El primero: no saltarse la Fase 3. En este
caso concreto, las tres preguntas marcadas ⚠ cambian la arquitectura, no un detalle — y una de
ellas, Q-1, decide si el diseño respeta la regla C-5 o la rompe. El segundo: la constitución solo
sirve si tiene pruebas detrás. C-3 y C-5 aparecen en las tareas T-25 y T-11 precisamente por eso;
una regla que nadie verifica es una intención, no una restricción.
