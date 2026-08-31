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
