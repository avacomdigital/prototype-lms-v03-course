import secrets
import time
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


def new_document_id():
    """Identificador compacto y portable entre SQLite y otros motores."""
    return secrets.token_hex(12)


def now_ms():
    return int(time.time() * 1000)


def sequence_value():
    # La secuencia del modelo entregado no es una PK. Para el prototipo basta una
    # marca monotónica de milisegundos; el id sigue siendo la identidad real.
    return now_ms()


class CurriculumFramework(models.Model):
    clave = models.CharField(primary_key=True, max_length=32)
    nombre = models.CharField(max_length=160)
    pais = models.CharField(max_length=8, null=True, blank=True)
    orden = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_marco_curricular"
        ordering = ["orden", "clave"]


class Course(models.Model):
    ESTADO_BORRADOR = "borrador"
    ESTADO_PRUEBAS = "pruebas"
    ESTADO_HABILITADO = "habilitado"
    ESTADO_RETIRADO = "retirado"
    ESTADOS = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_PRUEBAS, "Pruebas"),
        (ESTADO_HABILITADO, "Habilitado"),
        (ESTADO_RETIRADO, "Retirado"),
    ]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    titulo = models.CharField(max_length=250)
    descripcion = models.TextField(null=True, blank=True)
    docente_id = models.CharField(max_length=64)
    curriculum_framework = models.ForeignKey(
        CurriculumFramework,
        db_column="curriculum_framework",
        to_field="clave",
        related_name="cursos",
        on_delete=models.PROTECT,
    )
    # CAMBIO 2 · el entero `version` se eliminó a propósito.
    # Un contador se desincroniza del contenido; una FK no puede. Este puntero
    # es la única celda que cambia cuando se publica o se revierte contenido, y
    # es lo único que ve distinto el estudiante.
    # NULL = el curso existe pero todavía no publica ninguna versión.
    version_activa = models.ForeignKey(
        "CourseVersion",
        db_column="version_activa_id",
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    estado = models.CharField(max_length=16, choices=ESTADOS, default=ESTADO_BORRADOR)
    idioma = models.CharField(max_length=8, default="es")
    retirado_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_curso"
        ordering = ["-creado_en", "titulo"]
        indexes = [
            models.Index(fields=["docente_id", "estado"], name="ix_m05_curso_docente"),
            models.Index(fields=["curriculum_framework"], name="ix_m05_curso_marco"),
        ]
        constraints = [
            # Un curso habilitado tiene que estar mostrando algo. En el motor, no
            # en la aplicación: así lo imponen SQLite y Postgres por igual.
            models.CheckConstraint(
                condition=Q(estado__in=["borrador", "pruebas", "retirado"])
                | Q(version_activa__isnull=False),
                name="ck_m05_curso_habilitado_con_version",
            ),
        ]

    # NOTA · la FK COMPUESTA (version_activa_id, id) -> m05_curso_version (id, curso_id)
    # que sí está en el SQLite de referencia no se puede expresar en el ORM de
    # Django: ForeignKey apunta a una sola columna. La invariante «la versión
    # activa pertenece a ESTE curso» se impone en
    # exams.catalog.activate_version(), que es el único camino por el que se
    # mueve el puntero, y se verifica en las pruebas de integración.


class CourseVersion(models.Model):
    """
    Una FOTOGRAFÍA inmutable del contenido del curso.

    Instalar y publicar son dos momentos distintos, y por eso hay dos pares de
    fechas: `instalada_en` (se escribió la fotografía en este nodo) y
    `activada_en` (pasó a ser la que ven los estudiantes). Una fotografía ya
    instalada no se edita ni se borra nunca.
    """

    # CAMBIO 3 · ciclo de vida explícito.
    ESTADO_STAGED = "staged"        # llegó pero está incompleta
    ESTADO_INSTALADA = "instalada"  # íntegra y verificada, no publicada
    ESTADO_ACTIVA = "activa"        # es la que ven los estudiantes
    ESTADO_RETIRADA = "retirada"    # se dejó de publicar; conserva el contenido
    ESTADO_ERROR = "error"          # la instalación falló a mitad
    ESTADOS = [
        (ESTADO_STAGED, "Staged"),
        (ESTADO_INSTALADA, "Instalada"),
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_RETIRADA, "Retirada"),
        (ESTADO_ERROR, "Error"),
    ]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    # PROTECT y no CASCADE: un borrado accidental del curso no debe llevarse el
    # historial académico por delante en silencio.
    curso = models.ForeignKey(Course, related_name="versiones", on_delete=models.PROTECT)
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    package_version = models.CharField(max_length=32, null=True, blank=True)
    estado = models.CharField(max_length=16, choices=ESTADOS, default=ESTADO_STAGED)
    instalada_en = models.BigIntegerField(default=now_ms)
    instalada_por = models.CharField(max_length=64)
    activada_en = models.BigIntegerField(null=True, blank=True)
    retirada_en = models.BigIntegerField(null=True, blank=True)
    huella = models.CharField(max_length=64)
    notas = models.TextField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_curso_version"
        ordering = ["curso_id", "version"]
        indexes = [models.Index(fields=["estado", "curso"], name="ix_m05_cv_estado")]
        constraints = [
            models.UniqueConstraint(fields=["curso", "version"], name="ux_m05_curso_version"),
            # Una sola versión activa por curso, impuesto por un índice único
            # PARCIAL. Implicación para el código de activación: primero se
            # libera el estado 'activa' de la saliente y solo después se asigna
            # a la entrante. El orden inverso falla.
            models.UniqueConstraint(
                fields=["curso"],
                condition=Q(estado="activa"),
                name="ux_m05_cv_una_activa",
            ),
            # Coherencia del ciclo de vida.
            models.CheckConstraint(
                condition=Q(activada_en__isnull=True) | Q(activada_en__gte=F("instalada_en")),
                name="ck_m05_cv_activada_tras_instalada",
            ),
            models.CheckConstraint(
                condition=Q(retirada_en__isnull=True) | Q(retirada_en__gte=F("instalada_en")),
                name="ck_m05_cv_retirada_tras_instalada",
            ),
            models.CheckConstraint(
                condition=~Q(estado="activa") | Q(activada_en__isnull=False),
                name="ck_m05_cv_activa_con_fecha",
            ),
            models.CheckConstraint(
                condition=~Q(estado="retirada") | Q(retirada_en__isnull=False),
                name="ck_m05_cv_retirada_con_fecha",
            ),
        ]


class CourseEnrollment(models.Model):
    ESTADO_ACTIVA = "activa"
    ESTADO_RETIRADA = "retirada"
    ESTADO_CONCLUIDA = "concluida"
    ESTADOS = [
        (ESTADO_ACTIVA, "Activa"),
        (ESTADO_RETIRADA, "Retirada"),
        (ESTADO_CONCLUIDA, "Concluida"),
    ]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    # La inscripción cuelga del CURSO, no de la versión: por eso reemplazar el
    # contenido no toca ni una fila de esta tabla. PROTECT porque una nota ya
    # puesta no debe desaparecer por un borrado accidental.
    curso = models.ForeignKey(Course, related_name="inscripciones", on_delete=models.PROTECT)
    persona_id = models.CharField(max_length=64)
    alta = models.BigIntegerField(default=now_ms)
    baja = models.BigIntegerField(null=True, blank=True)
    estado = models.CharField(max_length=16, choices=ESTADOS, default=ESTADO_ACTIVA)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_curso_estudiante"
        ordering = ["curso_id", "creado_en"]
        constraints = [models.UniqueConstraint(fields=["curso", "persona_id"], name="ux_m05_curso_est")]
        indexes = [models.Index(fields=["persona_id", "estado"], name="ix_m05_curso_est_persona")]


class Section(models.Model):
    """
    CAMBIO 1 · el cambio central del modelo: la sección cuelga de la VERSIÓN,
    no del curso. Cada fotografía tiene sus propias secciones, y por eso se
    puede reemplazar el contenido sin tocar una sola inscripción.
    """

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    curso_version = models.ForeignKey(
        CourseVersion,
        db_column="curso_version_id",
        related_name="secciones",
        on_delete=models.PROTECT,
    )
    # CAMBIO 4 · identidad LÓGICA, estable entre versiones ('section.fracciones').
    # El id es el registro FÍSICO ('SEC-V4-01'). Con el codigo se reconoce que la
    # misma sección cambió de título de una versión a otra.
    codigo = models.CharField(max_length=120)
    titulo = models.CharField(max_length=250)
    orden = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_seccion"
        ordering = ["orden"]
        constraints = [
            models.UniqueConstraint(fields=["curso_version", "orden"], name="ux_m05_seccion_orden"),
            models.UniqueConstraint(fields=["curso_version", "codigo"], name="ux_m05_seccion_codigo"),
        ]


class Lesson(models.Model):
    ESTADO_DRAFT = "draft"
    ESTADO_PUBLICADO = "publicado"
    ESTADO_CERRADO = "cerrado"
    ESTADOS = [(ESTADO_DRAFT, "Borrador"), (ESTADO_PUBLICADO, "Publicado"), (ESTADO_CERRADO, "Cerrado")]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    seccion = models.ForeignKey(Section, related_name="lecciones", on_delete=models.PROTECT)
    # CAMBIO 4 · identidad lógica ('lesson.fracciones-equivalentes').
    codigo = models.CharField(max_length=120)
    titulo = models.CharField(max_length=250)
    descripcion = models.TextField(null=True, blank=True)
    competency_framework = models.CharField(max_length=64, null=True, blank=True)
    learning_outcome = models.TextField(null=True, blank=True)
    skills = models.TextField(null=True, blank=True)
    attitudes_values = models.TextField(null=True, blank=True)
    orden = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=16, choices=ESTADOS, default=ESTADO_DRAFT)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_leccion"
        ordering = ["orden"]
        constraints = [
            models.UniqueConstraint(fields=["seccion", "orden"], name="ux_m05_leccion_orden"),
            models.UniqueConstraint(fields=["seccion", "codigo"], name="ux_m05_leccion_codigo"),
        ]
        indexes = [
            models.Index(fields=["estado"], name="ix_m05_leccion_estado"),
            models.Index(fields=["competency_framework"], name="ix_m05_leccion_marco"),
        ]


class LearningResource(models.Model):
    CONTENT_TYPES = [("reading", "Lectura"), ("video", "Video"), ("audio", "Audio")]
    ESTADOS = [("activo", "Activo"), ("retirado", "Retirado")]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    titulo = models.CharField(max_length=250)
    content_type = models.CharField(max_length=16, choices=CONTENT_TYPES)
    content_ref = models.CharField(max_length=500)
    content_version = models.CharField(max_length=32)
    content_huella = models.CharField(max_length=64, null=True, blank=True)
    duracion_seg = models.PositiveIntegerField(null=True, blank=True)
    autor_id = models.CharField(max_length=64, null=True, blank=True)
    estado = models.CharField(max_length=16, choices=ESTADOS, default="activo")
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_recurso_aprendizaje"
        ordering = ["titulo"]
        indexes = [
            models.Index(fields=["content_type", "estado"], name="ix_m05_recurso_tipo"),
        ]
        constraints = [
            # CAMBIO 5 · cada fila es UNA versión concreta de un material. Las
            # v3.0, v3.1 y v3.2 de la misma lectura coexisten como filas
            # distintas: borrar la v3.0 rompería la V1 del curso, y por eso una
            # fila solo se marca 'retirado'. El binario pesado vive fuera de la
            # base: aquí solo hay referencia, versión y SHA-256.
            models.UniqueConstraint(
                fields=["content_ref", "content_version"], name="ux_m05_recurso_ref"
            ),
        ]


class Activity(models.Model):
    ACTIVITY_TYPES = [("quiz", "Quiz"), ("assignment", "Tarea"), ("exam", "Examen")]
    SUBMISSION_TYPES = [("quiz", "Quiz"), ("file", "Archivo"), ("none", "Sin entrega")]
    GRADING_TYPES = [("automatic", "Automática"), ("teacher", "Docente"), ("mixed", "Mixta")]
    ESTADOS = [("activa", "Activa"), ("retirada", "Retirada")]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    # CAMBIO 6 · identidad lógica de la actividad, mismo patrón que los recursos.
    # Un intento de quiz apunta a la fila FÍSICA, así que un intento hecho con el
    # quiz v1 sigue siendo interpretable aunque hoy se aplique el v2.
    activity_ref = models.CharField(max_length=500)
    titulo = models.CharField(max_length=250)
    descripcion = models.TextField(null=True, blank=True)
    activity_type = models.CharField(max_length=16, choices=ACTIVITY_TYPES)
    submission_type = models.CharField(max_length=16, choices=SUBMISSION_TYPES)
    grading_type = models.CharField(max_length=16, choices=GRADING_TYPES)
    max_score = models.DecimalField(max_digits=8, decimal_places=2, default=100, validators=[MinValueValidator(Decimal("0.01"))])
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    autor_id = models.CharField(max_length=64, null=True, blank=True)
    estado = models.CharField(max_length=16, choices=ESTADOS, default="activa")
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m10_actividad"
        ordering = ["titulo"]
        indexes = [models.Index(fields=["activity_type", "estado"], name="ix_m10_actividad_tipo")]
        constraints = [
            models.UniqueConstraint(
                fields=["activity_ref", "version"], name="ux_m10_actividad_ref"
            ),
        ]


class LessonItem(models.Model):
    TIPO_CONTENIDO = "contenido"
    TIPO_ACTIVIDAD = "actividad"
    TIPO_REFERENCIA = "referencia_externa"
    TIPOS = [(TIPO_CONTENIDO, "Contenido"), (TIPO_ACTIVIDAD, "Actividad"), (TIPO_REFERENCIA, "Referencia externa")]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    # m05_leccion_item NO lleva `codigo`: su identidad es (lección, orden).
    leccion = models.ForeignKey(Lesson, related_name="items", on_delete=models.PROTECT)
    orden = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    tipo = models.CharField(max_length=24, choices=TIPOS)
    actividad = models.ForeignKey(Activity, related_name="lesson_items", on_delete=models.PROTECT, null=True, blank=True)
    recurso = models.ForeignKey(LearningResource, related_name="lesson_items", on_delete=models.PROTECT, null=True, blank=True)
    elemento_ref = models.CharField(max_length=500, null=True, blank=True)
    elemento_version = models.CharField(max_length=32, null=True, blank=True)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_leccion_item"
        ordering = ["orden"]
        constraints = [models.UniqueConstraint(fields=["leccion", "orden"], name="ux_m05_item_orden")]
        indexes = [
            models.Index(fields=["actividad"], name="ix_m05_item_actividad"),
            models.Index(fields=["recurso"], name="ix_m05_item_recurso"),
        ]


class AuditLog(models.Model):
    RESULTADOS = [("ok", "OK"), ("denegado", "Denegado"), ("error", "Error")]
    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    actor_id = models.CharField(max_length=64, null=True, blank=True)
    accion = models.CharField(max_length=120)
    objeto_tabla = models.CharField(max_length=120)
    objeto_id = models.CharField(max_length=64)
    valor_anterior = models.TextField(null=True, blank=True)
    valor_nuevo = models.TextField(null=True, blank=True)
    resultado = models.CharField(max_length=16, choices=RESULTADOS, default="ok")
    ocurrido_en = models.BigIntegerField(default=now_ms)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m19_auditoria"
        ordering = ["-ocurrido_en"]
        indexes = [
            models.Index(fields=["actor_id", "ocurrido_en"], name="ix_m19_aud_actor"),
            models.Index(fields=["objeto_tabla", "objeto_id", "ocurrido_en"], name="ix_m19_aud_objeto"),
        ]


# Únicas tablas añadidas al modelo entregado: definición y transacción del quiz.
class QuizQuestion(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    actividad = models.ForeignKey(Activity, related_name="preguntas", on_delete=models.CASCADE)
    categoria = models.CharField(max_length=80)
    texto = models.TextField()
    orden = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    creado_en = models.BigIntegerField(default=now_ms)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m10_quiz_pregunta"
        ordering = ["orden"]
        constraints = [models.UniqueConstraint(fields=["actividad", "orden"], name="ux_m10_quiz_pregunta_orden")]


class QuizOption(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    pregunta = models.ForeignKey(QuizQuestion, related_name="opciones", on_delete=models.CASCADE)
    texto = models.CharField(max_length=400)
    orden = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    es_correcta = models.BooleanField(default=False)
    creado_en = models.BigIntegerField(default=now_ms)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m10_quiz_opcion"
        ordering = ["orden"]
        constraints = [models.UniqueConstraint(fields=["pregunta", "orden"], name="ux_m10_quiz_opcion_orden")]


class QuizAttempt(models.Model):
    ESTADO_EN_PROGRESO = "en_progreso"
    ESTADO_FINALIZADO = "finalizado"
    ESTADOS = [(ESTADO_EN_PROGRESO, "En progreso"), (ESTADO_FINALIZADO, "Finalizado")]
    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    actividad = models.ForeignKey(Activity, related_name="intentos", on_delete=models.CASCADE)
    persona_id = models.CharField(max_length=64)
    nombre_estudiante = models.CharField(max_length=250)
    device_id = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=16, choices=ESTADOS, default=ESTADO_EN_PROGRESO)
    pregunta_actual = models.PositiveIntegerField(default=1)
    puntaje = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_preguntas = models.PositiveIntegerField(default=0)
    iniciado_en = models.BigIntegerField(default=now_ms)
    finalizado_en = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "m10_quiz_intento"
        ordering = ["-iniciado_en"]
        indexes = [
            models.Index(fields=["actividad", "estado"], name="ix_m10_quiz_intento_estado"),
            models.Index(fields=["persona_id", "actividad"], name="ix_m10_quiz_intento_persona"),
        ]


class QuizAnswer(models.Model):
    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    intento = models.ForeignKey(QuizAttempt, related_name="respuestas", on_delete=models.CASCADE)
    pregunta = models.ForeignKey(QuizQuestion, related_name="respuestas", on_delete=models.CASCADE)
    opcion = models.ForeignKey(QuizOption, related_name="respuestas", on_delete=models.CASCADE)
    es_correcta = models.BooleanField(default=False)
    respondido_en = models.BigIntegerField(default=now_ms)

    class Meta:
        db_table = "m10_quiz_respuesta"
        ordering = ["pregunta__orden"]
        constraints = [models.UniqueConstraint(fields=["intento", "pregunta"], name="ux_m10_quiz_respuesta")]


class CourseHost(models.Model):
    """
    PRESENCIA FÍSICA de un curso en un host. Responde una sola pregunta:
    ¿este curso está instalado en ESTA OPS en este momento?

    No representa matrícula, ni progreso, ni propiedad del curso. Esas viven en
    m05_curso_estudiante y cuelgan del CURSO, no del host.

    La regla que justifica esta tabla:
        DESINSTALAR CONTENIDO  ≠  BORRAR ENTIDADES ACADÉMICAS
    Al quitar el paquete de una OPS no se borra el curso ni las inscripciones ni
    las notas: se apagan las banderas de esta fila y se sella retirado_en. El
    estudiante conserva su historial y ve «no disponible en este dispositivo»
    en lugar de que el curso desaparezca sin explicación.

    Y por eso NO se toca m05_curso.estado al desinstalar: el estado del curso es
    editorial —¿está publicado?— mientras que presente_local es material —¿los
    archivos están en este disco?—. El mismo curso puede estar habilitado y
    presente en Bogotá y retirado en Medellín.
    """

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)

    # Identificador del host. Sin FK a propósito: no hay catálogo de hosts en el
    # prototipo, y añadir la tabla sería inventar una entidad que nadie pidió.
    host_id = models.CharField(max_length=64)

    curso = models.ForeignKey(Course, related_name="hosts", on_delete=models.PROTECT)

    # Qué versión concreta está instalada aquí. NULL = el curso está registrado
    # en el host pero todavía no se resolvió su versión.
    curso_version = models.ForeignKey(
        CourseVersion,
        db_column="curso_version_id",
        related_name="hosts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    # ── Procedencia del paquete, NEUTRAL al estándar ──────────────────────────
    # SCORM y CMI5 son formatos de ENTRADA, no modelos distintos de curso: cada
    # parser transforma su formato al mismo árbol
    # curso -> sección -> lección -> lesson item.
    # Por eso aquí no hay columnas scorm_* ni cmi5_*, solo el formato y dónde
    # está su descriptor.
    #
    #   SCORM 2004   formato=scorm_2004  manifest_tipo=imsmanifest  ref=imsmanifest.xml
    #   CMI5         formato=cmi5        manifest_tipo=cmi5         ref=cmi5.xml
    #   nativo       formato=avacom_v1   manifest_tipo=avacom       ref=<archivo>.json
    FORMATO_SCORM_12 = "scorm_12"
    FORMATO_SCORM_2004 = "scorm_2004"
    FORMATO_CMI5 = "cmi5"
    FORMATO_AVACOM_V1 = "avacom_v1"
    FORMATOS = [
        (FORMATO_SCORM_12, "SCORM 1.2"),
        (FORMATO_SCORM_2004, "SCORM 2004"),
        (FORMATO_CMI5, "cmi5"),
        # AÑADIDO a la propuesta: es el único formato que el prototipo instala
        # hoy. Sin él, `formato_contenido NOT NULL` con CHECK restringido a los
        # tres estándares dejaría fuera el camino que ya funciona.
        (FORMATO_AVACOM_V1, "AVACOM course package v1"),
    ]

    formato_contenido = models.CharField(
        max_length=16, choices=FORMATOS, default=FORMATO_AVACOM_V1
    )

    # Identificador externo del paquete, tal como lo declara su propio formato:
    # el `identifier` del manifest en SCORM, el IRI del curso en CMI5, el
    # `package_id` en el nuestro.
    package_identifier = models.CharField(max_length=500, null=True, blank=True)
    # Versión que declara el paquete. Se guarda aquí, y no solo en
    # m05_curso_version, porque es lo que este host recibió.
    package_version = models.CharField(max_length=32, null=True, blank=True)

    # Descriptor: qué tipo es y dónde está dentro del paquete.
    manifest_tipo = models.CharField(max_length=32, null=True, blank=True)
    manifest_ref = models.CharField(max_length=500, null=True, blank=True)

    # Dónde están los archivos y con qué huella llegaron. El binario pesado vive
    # fuera de la base, igual que en m05_recurso_aprendizaje.
    package_ref = models.CharField(max_length=500, null=True, blank=True)
    package_huella = models.CharField(max_length=64, null=True, blank=True)

    # ── Las dos banderas, que son distintas a propósito ──────────────────────
    # presente_local        los archivos están en este disco
    # disponible_estudiante los estudiantes ya pueden usarlo
    # Recién importado y en validación: presente=1, disponible=0.
    presente_local = models.BooleanField(default=True)
    disponible_estudiante = models.BooleanField(default=False)

    instalado_en = models.BigIntegerField(default=now_ms)
    retirado_en = models.BigIntegerField(null=True, blank=True)
    verificado_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_curso_host"
        ordering = ["host_id", "curso_id"]
        indexes = [
            models.Index(fields=["host_id", "presente_local"], name="ix_m05_ch_host"),
            models.Index(fields=["curso", "presente_local"], name="ix_m05_ch_curso"),
            models.Index(fields=["formato_contenido"], name="ix_m05_ch_formato"),
        ]
        constraints = [
            # Una fila por (host, curso, versión). Ahora sí queda el historial de
            # QUÉ versión estuvo instalada en este host, que con la clave anterior
            # —(host, curso)— se perdía al sobrescribir curso_version_id.
            models.UniqueConstraint(
                fields=["host_id", "curso", "curso_version"], name="ux_m05_ch_host_curso_version"
            ),

            # AÑADIDO · tapa el hueco de los NULL. En SQLite y en Postgres, un
            # UNIQUE trata dos NULL como distintos, así que la clave de arriba
            # dejaría insertar (host, curso, NULL) tantas veces como se quiera y
            # se rompería la idempotencia de register_install().
            models.UniqueConstraint(
                fields=["host_id", "curso"],
                condition=Q(curso_version__isnull=True),
                name="ux_m05_ch_sin_version",
            ),

            # AÑADIDO · con filas por versión, dos versiones del mismo curso
            # podrían quedar ofrecidas a la vez en el mismo host, y el estudiante
            # vería el curso duplicado. Solo una disponible por (host, curso).
            # Mismo idiom que ux_m05_cv_una_activa.
            models.UniqueConstraint(
                fields=["host_id", "curso"],
                condition=Q(disponible_estudiante=True),
                name="ux_m05_ch_una_disponible",
            ),

            # AÑADIDO a la propuesta · no se puede ofrecer a los estudiantes
            # contenido que no está en el disco. Los ejemplos de la propuesta
            # siempre respetaban esta regla, pero nada la imponía.
            models.CheckConstraint(
                condition=Q(presente_local=True) | Q(disponible_estudiante=False),
                name="ck_m05_ch_disponible_requiere_presente",
            ),

            # AÑADIDO · si ya no está presente, se sabe cuándo dejó de estarlo.
            # Mismo patrón que ck_m05_cv_retirada_con_fecha.
            models.CheckConstraint(
                condition=Q(presente_local=True) | Q(retirado_en__isnull=False),
                name="ck_m05_ch_retirado_con_fecha",
            ),
        ]

    # NOTA · la invariante «la versión instalada pertenece a ESTE curso» necesita
    # una FK compuesta (curso_version_id, curso_id) que el ORM de Django no puede
    # expresar, igual que en m05_curso.version_activa_id. Se impone en
    # exams.hosts.register_install() y está cubierta por pruebas.

    @property
    def estado_legible(self):
        if not self.presente_local:
            return "desinstalado"
        return "disponible" if self.disponible_estudiante else "instalado"


class LessonProgress(models.Model):
    """
    PROGRESO del estudiante en una lección.

    Se indexa por el CÓDIGO LÓGICO de la lección, no por su fila física.
    Es la decisión que hace que el progreso sobreviva a lo que exige el spec:

      · desinstalar y reinstalar el mismo paquete  (§13, §21 pasos 5-9)
      · subir de versión: la V2 tiene filas m05_leccion nuevas, pero la misma
        lección conceptual conserva su `codigo`, así que el progreso la sigue

    Si se indexara por m05_leccion.id, un cambio de versión dejaría el progreso
    huérfano. Ese es justamente el problema que `codigo` existe para resolver.

    La nota del quiz NO se duplica aquí: vive en m10_quiz_intento.puntaje, que es
    su registro autoritativo. El porcentaje de una lección con actividad
    calificable se deriva de ahí.
    """

    ESTADO_NO_INICIADA = "no_iniciada"
    ESTADO_EN_CURSO = "en_curso"
    ESTADO_COMPLETADA = "completada"
    ESTADOS = [
        (ESTADO_NO_INICIADA, "No iniciada"),
        (ESTADO_EN_CURSO, "En curso"),
        (ESTADO_COMPLETADA, "Completada"),
    ]

    id = models.CharField(primary_key=True, max_length=40, default=new_document_id, editable=False)
    # Cuelga del CURSO, no de la versión: el progreso es del estudiante en el
    # curso, y sobrevive a que el contenido se reemplace.
    curso = models.ForeignKey(Course, related_name="progresos", on_delete=models.PROTECT)
    persona_id = models.CharField(max_length=64)
    # Identidad LÓGICA de la lección ('lesson.fracciones-equivalentes').
    leccion_codigo = models.CharField(max_length=120)
    # Se guarda el título con el que se registró para poder mostrar el historial
    # aunque el contenido ya no esté instalado (§12: el estudiante ve el nombre).
    leccion_titulo = models.CharField(max_length=250, blank=True)

    porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    estado = models.CharField(max_length=16, choices=ESTADOS, default=ESTADO_NO_INICIADA)
    iniciado_en = models.BigIntegerField(default=now_ms)
    actualizado_en = models.BigIntegerField(default=now_ms)
    completado_en = models.BigIntegerField(null=True, blank=True)
    creado_en = models.BigIntegerField(default=now_ms)
    creado_por = models.CharField(max_length=64, null=True, blank=True)
    secuencia = models.BigIntegerField(default=sequence_value)

    class Meta:
        db_table = "m05_progreso_leccion"
        ordering = ["curso_id", "persona_id", "leccion_codigo"]
        indexes = [
            models.Index(fields=["persona_id", "curso"], name="ix_m05_prog_persona"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["curso", "persona_id", "leccion_codigo"], name="ux_m05_prog_leccion"
            ),
            # El porcentaje es un porcentaje. En el motor, para que ningún cliente
            # pueda dejar un 340 % en la base.
            models.CheckConstraint(
                condition=Q(porcentaje__gte=0) & Q(porcentaje__lte=100),
                name="ck_m05_prog_porcentaje",
            ),
            # Coherencia del ciclo: completada implica 100 y con fecha.
            models.CheckConstraint(
                condition=~Q(estado="completada")
                | (Q(porcentaje=100) & Q(completado_en__isnull=False)),
                name="ck_m05_prog_completada",
            ),
        ]

    @property
    def porcentaje_entero(self):
        return int(self.porcentaje)
