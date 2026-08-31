import re

from rest_framework import serializers

from .models import (
    Activity,
    LessonProgress,
    CourseHost,
    AuditLog,
    Course,
    CourseEnrollment,
    CourseVersion,
    CurriculumFramework,
    LearningResource,
    Lesson,
    LessonItem,
    QuizAnswer,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    Section,
)


class CurriculumFrameworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumFramework
        fields = "__all__"


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia", "retirado_en"]


class CourseVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseVersion
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]


class CourseEnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseEnrollment
        fields = "__all__"
        read_only_fields = ["id", "alta", "creado_en", "secuencia", "baja"]

    def validate_persona_id(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Escribe un nombre o identificador de al menos 2 caracteres.")
        return re.sub(r"\s+", "-", value.lower())[:64]


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]


class LearningResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningResource
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]

    def validate(self, attrs):
        activity_type = attrs.get("activity_type", getattr(self.instance, "activity_type", None))
        submission_type = attrs.get("submission_type", getattr(self.instance, "submission_type", None))
        grading_type = attrs.get("grading_type", getattr(self.instance, "grading_type", None))
        if submission_type == "none" and grading_type != "teacher":
            raise serializers.ValidationError("Una actividad sin entrega debe ser calificada por el docente.")
        if submission_type == "file" and grading_type == "automatic":
            raise serializers.ValidationError("Un archivo no se autocalifica en este prototipo.")
        allowed = {
            "quiz": {"quiz"},
            "exam": {"quiz", "file"},
            "assignment": {"file", "none"},
        }
        if activity_type in allowed and submission_type not in allowed[activity_type]:
            raise serializers.ValidationError("La forma de entrega no corresponde al tipo de actividad.")
        return attrs


class LessonItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonItem
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]

    def validate(self, attrs):
        tipo = attrs.get("tipo", getattr(self.instance, "tipo", None))
        actividad = attrs.get("actividad", getattr(self.instance, "actividad", None))
        recurso = attrs.get("recurso", getattr(self.instance, "recurso", None))
        referencia = attrs.get("elemento_ref", getattr(self.instance, "elemento_ref", None))
        valid = (
            (tipo == LessonItem.TIPO_ACTIVIDAD and actividad and not recurso and not referencia)
            or (tipo == LessonItem.TIPO_CONTENIDO and recurso and not actividad and not referencia)
            or (tipo == LessonItem.TIPO_REFERENCIA and referencia and not actividad and not recurso)
        )
        if not valid:
            raise serializers.ValidationError(
                "El ítem debe apuntar solamente al recurso, actividad o referencia que corresponde a su tipo."
            )
        return attrs


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"
        read_only_fields = ["id", "ocurrido_en", "secuencia"]


class QuizOptionAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]


class QuizOptionPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = ["id", "texto", "orden"]


class QuizQuestionSerializer(serializers.ModelSerializer):
    opciones = QuizOptionPublicSerializer(many=True, read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ["id", "actividad", "categoria", "texto", "orden", "opciones"]
        read_only_fields = ["id"]


class QuizQuestionAdminSerializer(serializers.ModelSerializer):
    opciones = QuizOptionAdminSerializer(many=True, read_only=True)

    class Meta:
        model = QuizQuestion
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]


class ActivityDetailSerializer(ActivitySerializer):
    preguntas = QuizQuestionSerializer(many=True, read_only=True)

    class Meta(ActivitySerializer.Meta):
        fields = [
            "id", "titulo", "descripcion", "activity_type", "submission_type", "grading_type",
            "max_score", "version", "autor_id", "estado", "preguntas",
        ]


class LessonItemDetailSerializer(serializers.ModelSerializer):
    actividad = ActivityDetailSerializer(read_only=True)
    recurso = LearningResourceSerializer(read_only=True)
    titulo = serializers.SerializerMethodField()
    subtitulo = serializers.SerializerMethodField()

    class Meta:
        model = LessonItem
        fields = [
            "id", "orden", "tipo", "actividad", "recurso", "elemento_ref", "elemento_version",
            "titulo", "subtitulo",
        ]

    def get_titulo(self, obj):
        if obj.actividad_id:
            return obj.actividad.titulo
        if obj.recurso_id:
            return obj.recurso.titulo
        return obj.elemento_ref or "Referencia"

    def get_subtitulo(self, obj):
        if obj.actividad_id:
            return "Quiz calificable" if obj.actividad.activity_type == "quiz" else "Actividad"
        if obj.recurso_id:
            labels = {"reading": "Lectura", "video": "Video", "audio": "Audio"}
            return labels.get(obj.recurso.content_type, "Recurso")
        return f"Referencia externa · v{obj.elemento_version or '1'}"


class LessonDetailSerializer(serializers.ModelSerializer):
    items = LessonItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id", "titulo", "descripcion", "competency_framework", "learning_outcome", "skills",
            "attitudes_values", "orden", "estado", "items",
        ]


class SectionDetailSerializer(serializers.ModelSerializer):
    lecciones = LessonDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ["id", "titulo", "orden", "lecciones"]


class CourseDetailSerializer(serializers.ModelSerializer):
    """
    El curso tal como lo consume el cliente.

    `secciones` NO sale del curso: sale de la VERSIÓN ACTIVA. Esta es la misma
    idea que la consulta 3 de consultas_demo.sql — se parte del curso y se sigue
    el puntero, sin mencionar ningún número de versión. El día que se haga
    rollback, este serializer devuelve la otra versión sin cambiar una línea.

    `version` se conserva en el payload por compatibilidad con el cliente .NET,
    pero ya no es una columna: es el número de la versión publicada.
    """

    curriculum_framework = CurriculumFrameworkSerializer(read_only=True)
    secciones = serializers.SerializerMethodField()
    inscripciones = CourseEnrollmentSerializer(many=True, read_only=True)
    version = serializers.SerializerMethodField()
    version_activa_id = serializers.CharField(read_only=True, allow_null=True)
    total_lecciones = serializers.SerializerMethodField()
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id", "titulo", "descripcion", "docente_id", "curriculum_framework", "version",
            "version_activa_id", "estado", "idioma", "creado_en", "secciones", "inscripciones",
            "total_lecciones", "total_items",
        ]

    def _secciones(self, obj):
        if obj.version_activa_id is None:
            return []
        return sorted(obj.version_activa.secciones.all(), key=lambda s: s.orden)

    def get_secciones(self, obj):
        return SectionDetailSerializer(self._secciones(obj), many=True).data

    def get_version(self, obj):
        # 0 = el curso existe pero todavía no publica ninguna versión.
        return obj.version_activa.version if obj.version_activa_id else 0

    def get_total_lecciones(self, obj):
        return sum(len(section.lecciones.all()) for section in self._secciones(obj))

    def get_total_items(self, obj):
        return sum(
            len(lesson.items.all())
            for section in self._secciones(obj)
            for lesson in section.lecciones.all()
        )


class QuizStartSerializer(serializers.Serializer):
    actividad_id = serializers.CharField(max_length=40)
    nombre_estudiante = serializers.CharField(max_length=250)
    persona_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_nombre_estudiante(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("El nombre debe tener al menos 2 caracteres.")
        return value

    def validate(self, attrs):
        try:
            activity = Activity.objects.prefetch_related("preguntas__opciones").get(
                pk=attrs["actividad_id"], activity_type="quiz", estado="activa"
            )
        except Activity.DoesNotExist:
            raise serializers.ValidationError("El quiz no existe o no está activo.")
        attrs["actividad"] = activity
        if not attrs.get("persona_id"):
            attrs["persona_id"] = re.sub(r"[^a-z0-9]+", "-", attrs["nombre_estudiante"].lower()).strip("-")[:64]
        return attrs

    def create(self, validated_data):
        activity = validated_data["actividad"]
        attempt = QuizAttempt.objects.filter(
            actividad=activity,
            persona_id=validated_data["persona_id"],
            device_id=validated_data.get("device_id", ""),
            estado=QuizAttempt.ESTADO_EN_PROGRESO,
        ).first()
        if attempt:
            return attempt
        return QuizAttempt.objects.create(
            actividad=activity,
            persona_id=validated_data["persona_id"],
            nombre_estudiante=validated_data["nombre_estudiante"],
            device_id=validated_data.get("device_id", ""),
            total_preguntas=activity.preguntas.count(),
        )


class QuizAnswerWriteSerializer(serializers.Serializer):
    intento_id = serializers.CharField(max_length=40)
    pregunta_id = serializers.CharField(max_length=40)
    opcion_id = serializers.CharField(max_length=40)
    client_event_id = serializers.CharField(max_length=80, required=False, allow_blank=True)

    def validate(self, attrs):
        try:
            attempt = QuizAttempt.objects.get(pk=attrs["intento_id"], estado=QuizAttempt.ESTADO_EN_PROGRESO)
            question = QuizQuestion.objects.get(pk=attrs["pregunta_id"], actividad=attempt.actividad)
            option = QuizOption.objects.get(pk=attrs["opcion_id"], pregunta=question)
        except (QuizAttempt.DoesNotExist, QuizQuestion.DoesNotExist, QuizOption.DoesNotExist):
            raise serializers.ValidationError("Intento, pregunta u opción inválidos.")
        attrs.update(intento=attempt, pregunta=question, opcion=option)
        return attrs

    def create(self, validated_data):
        answer, _ = QuizAnswer.objects.update_or_create(
            intento=validated_data["intento"],
            pregunta=validated_data["pregunta"],
            defaults={
                "opcion": validated_data["opcion"],
                "es_correcta": validated_data["opcion"].es_correcta,
            },
        )
        return answer


class QuizProgressSerializer(serializers.Serializer):
    intento_id = serializers.CharField(max_length=40)
    pregunta_actual = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        try:
            attempt = QuizAttempt.objects.get(pk=attrs["intento_id"], estado=QuizAttempt.ESTADO_EN_PROGRESO)
        except QuizAttempt.DoesNotExist:
            raise serializers.ValidationError("El intento no existe o ya finalizó.")
        if attrs["pregunta_actual"] > attempt.total_preguntas:
            raise serializers.ValidationError("La pregunta está fuera del rango del quiz.")
        attrs["intento"] = attempt
        return attrs


class QuizFinishSerializer(serializers.Serializer):
    intento_id = serializers.CharField(max_length=40)


class QuizAttemptSerializer(serializers.ModelSerializer):
    actividad_titulo = serializers.CharField(source="actividad.titulo", read_only=True)
    porcentaje = serializers.SerializerMethodField()
    respondidas = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = [
            "id", "actividad", "actividad_titulo", "persona_id", "nombre_estudiante", "device_id", "estado",
            "pregunta_actual", "puntaje", "total_preguntas", "porcentaje", "respondidas", "iniciado_en", "finalizado_en",
        ]

    def get_porcentaje(self, obj):
        max_score = float(obj.actividad.max_score)
        return round(float(obj.puntaje) * 100 / max_score) if max_score else 0

    def get_respondidas(self, obj):
        return obj.respuestas.count()


class QuizAnswerResultSerializer(serializers.ModelSerializer):
    pregunta = serializers.CharField(source="pregunta.texto")
    seleccionada = serializers.CharField(source="opcion.texto")
    correcta = serializers.SerializerMethodField()

    class Meta:
        model = QuizAnswer
        fields = ["pregunta", "seleccionada", "correcta", "es_correcta"]

    def get_correcta(self, obj):
        option = obj.pregunta.opciones.filter(es_correcta=True).first()
        return option.texto if option else ""


# ═══════════════════════════════════════════════════════════════════════════
# CATÁLOGO VERSIONADO · manifiesto y paquete
#
# Django es dueño del catálogo canónico y de QUÉ VERSIÓN ESTÁ PUBLICADA. El
# manifiesto dice qué debería tener el cliente; el paquete es el contenido
# completo de una versión, con la misma forma que curso_fracciones_v4.json
# (schema "avacom-course-package/v1"), para que el mismo instalador sirva.
# ═══════════════════════════════════════════════════════════════════════════

PACKAGE_SCHEMA = "avacom-course-package/v1"


class CourseVersionSummarySerializer(serializers.ModelSerializer):
    """Una versión con su estado y sus conteos. Es lo que pinta la pantalla del catálogo."""

    secciones = serializers.SerializerMethodField()
    lecciones = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    es_la_activa = serializers.SerializerMethodField()

    class Meta:
        model = CourseVersion
        fields = [
            "id", "curso_id", "version", "package_version", "estado", "huella", "notas",
            "instalada_en", "instalada_por", "activada_en", "retirada_en",
            "secciones", "lecciones", "items", "es_la_activa",
        ]

    def _counts(self, obj):
        cache = self.context.setdefault("_counts", {})
        if obj.pk not in cache:
            from .catalog import version_counts

            cache[obj.pk] = version_counts(obj)
        return cache[obj.pk]

    def get_secciones(self, obj):
        return self._counts(obj)["secciones"]

    def get_lecciones(self, obj):
        return self._counts(obj)["lecciones"]

    def get_items(self, obj):
        return self._counts(obj)["items"]

    def get_es_la_activa(self, obj):
        return obj.estado == CourseVersion.ESTADO_ACTIVA


class CourseManifestSerializer(serializers.Serializer):
    """
    Qué versión DEBERÍA tener el cliente, con su huella para verificarla.

    No lleva contenido: es deliberadamente pequeño para poder consultarlo seguido
    por una Wi-Fi de aula. El cliente compara la huella con lo que tiene
    instalado y solo entonces decide si vale la pena bajar el paquete.
    """

    schema = serializers.CharField()
    course_id = serializers.CharField()
    titulo = serializers.CharField()
    estado = serializers.CharField()
    version_publicada = serializers.IntegerField(allow_null=True)
    version_publicada_id = serializers.CharField(allow_null=True)
    huella = serializers.CharField(allow_null=True)
    package_version = serializers.CharField(allow_null=True)
    activada_en = serializers.IntegerField(allow_null=True)
    versiones = CourseVersionSummarySerializer(many=True)

    @staticmethod
    def build(curso, versiones):
        activa = curso.version_activa
        return {
            "schema": "avacom-course-manifest/v1",
            "course_id": curso.id,
            "titulo": curso.titulo,
            "estado": curso.estado,
            "version_publicada": activa.version if activa else None,
            "version_publicada_id": activa.pk if activa else None,
            "huella": activa.huella if activa else None,
            "package_version": activa.package_version if activa else None,
            "activada_en": activa.activada_en if activa else None,
            "versiones": versiones,
        }


def build_version_package(version):
    """
    El paquete completo de una versión, con la forma de curso_fracciones_v4.json.

    Los recursos y actividades llevan su `id` FÍSICO porque todos los nodos
    offline tienen que resolver el mismo registro: si cada tableta inventara un
    id, la sincronización posterior generaría duplicados. Los ids de secciones,
    lecciones e items NO viajan: el instalador los deriva de (curso, versión,
    orden), que es determinista y da el mismo resultado en cada nodo.
    """
    secciones = (
        Section.objects.filter(curso_version=version)
        .prefetch_related("lecciones__items__recurso", "lecciones__items__actividad")
        .order_by("orden")
    )

    recursos = {}
    actividades = {}
    secciones_json = []

    for seccion in secciones:
        lecciones_json = []
        for leccion in sorted(seccion.lecciones.all(), key=lambda l: l.orden):
            items_json = []
            for item in sorted(leccion.items.all(), key=lambda i: i.orden):
                entrada = {"orden": item.orden, "tipo": item.tipo}
                if item.tipo == "contenido" and item.recurso_id:
                    r = item.recurso
                    recursos[r.id] = {
                        "id": r.id,
                        "titulo": r.titulo,
                        "content_type": r.content_type,
                        "content_ref": r.content_ref,
                        "content_version": r.content_version,
                        "content_huella": r.content_huella,
                        "duracion_seg": r.duracion_seg,
                        "autor_id": r.autor_id,
                    }
                    entrada["content_ref"] = r.content_ref
                    entrada["content_version"] = r.content_version
                elif item.tipo == "actividad" and item.actividad_id:
                    a = item.actividad
                    actividades[a.id] = {
                        "id": a.id,
                        "activity_ref": a.activity_ref,
                        "version": a.version,
                        "titulo": a.titulo,
                        "descripcion": a.descripcion,
                        "activity_type": a.activity_type,
                        "submission_type": a.submission_type,
                        "grading_type": a.grading_type,
                        "max_score": float(a.max_score),
                        "autor_id": a.autor_id,
                    }
                    entrada["activity_ref"] = a.activity_ref
                    entrada["activity_version"] = a.version
                else:
                    entrada["elemento_ref"] = item.elemento_ref
                    entrada["elemento_version"] = item.elemento_version
                items_json.append(entrada)

            lecciones_json.append({
                "codigo": leccion.codigo,
                "titulo": leccion.titulo,
                "descripcion": leccion.descripcion,
                "competency_framework": leccion.competency_framework,
                "learning_outcome": leccion.learning_outcome,
                "skills": leccion.skills,
                "attitudes_values": leccion.attitudes_values,
                "orden": leccion.orden,
                "estado": leccion.estado,
                "items": items_json,
            })

        secciones_json.append({
            "codigo": seccion.codigo,
            "titulo": seccion.titulo,
            "orden": seccion.orden,
            "lessons": lecciones_json,
        })

    return {
        "schema": PACKAGE_SCHEMA,
        "package": {
            "package_id": f"avacom.course.{version.curso_id}",
            "package_version": version.package_version or f"{version.version}.0.0",
            "operation": "install",
        },
        "course": {"course_id": version.curso_id, "version": version.version},
        "publication": {"activate_after_install": False},
        "version_meta": {
            "instalada_por": version.instalada_por,
            "huella": version.huella,
            "notas": version.notas,
        },
        "resources": list(recursos.values()),
        "activities": list(actividades.values()),
        "sections": secciones_json,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PRESENCIA FÍSICA EN UN HOST · m05_curso_host
#
# Neutral al estándar: SCORM y CMI5 son formatos de ENTRADA, no modelos
# distintos de curso. Aquí solo se registra qué formato llegó y dónde está su
# descriptor; el parser correspondiente lo transforma al árbol común de AVACOM.
# ═══════════════════════════════════════════════════════════════════════════


class CourseHostSerializer(serializers.ModelSerializer):
    """CRUD directo sobre la fila. Para las transiciones usa los endpoints de acción."""

    curso_titulo = serializers.CharField(source="curso.titulo", read_only=True)
    curso_estado = serializers.CharField(source="curso.estado", read_only=True)
    version = serializers.IntegerField(source="curso_version.version", read_only=True, allow_null=True)
    estado_host = serializers.CharField(source="estado_legible", read_only=True)
    formato_legible = serializers.CharField(source="get_formato_contenido_display", read_only=True)

    class Meta:
        model = CourseHost
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia"]

    def validate(self, attrs):
        def actual(nombre, defecto=None):
            return attrs.get(nombre, getattr(self.instance, nombre, defecto))

        curso = actual("curso")
        version = actual("curso_version")
        presente = actual("presente_local", True)
        disponible = actual("disponible_estudiante", False)
        retirado = actual("retirado_en")

        # La invariante de la FK compuesta que el ORM no puede expresar.
        if version is not None and curso is not None and version.curso_id != curso.pk:
            raise serializers.ValidationError(
                f"La versión {version.pk} pertenece al curso {version.curso_id}, no a {curso.pk}."
            )
        if disponible and not presente:
            raise serializers.ValidationError(
                "No se puede marcar disponible para estudiantes un curso que no está "
                "presente en el host."
            )
        if not presente and retirado is None:
            raise serializers.ValidationError(
                "Si el curso ya no está presente, indica retirado_en. Para desinstalar, "
                "usa POST /api/course-hosts/retire/, que sella la fecha y audita."
            )
        # Solo una versión ofrecida por (host, curso): el motor lo impone con
        # ux_m05_ch_una_disponible, pero un 400 explica mejor que un 500.
        if disponible and curso is not None:
            host_id = actual("host_id")
            otras = CourseHost.objects.filter(
                host_id=host_id, curso=curso, disponible_estudiante=True
            )
            if self.instance is not None:
                otras = otras.exclude(pk=self.instance.pk)
            if otras.exists():
                raise serializers.ValidationError(
                    "Ya hay otra versión de este curso ofrecida a los estudiantes en "
                    "este host. Ciérrala primero, o usa "
                    "POST /api/course-hosts/availability/, que lo hace en el orden correcto."
                )
        return attrs


class CourseHostInstallSerializer(serializers.Serializer):
    """
    Cuerpo de POST /api/course-hosts/install/.

    Ejemplos del bloque de procedencia:
        SCORM 2004  formato_contenido=scorm_2004  manifest_tipo=imsmanifest
                    manifest_ref=imsmanifest.xml
                    package_identifier=AVACOM-MAT-001
        CMI5        formato_contenido=cmi5        manifest_tipo=cmi5
                    manifest_ref=cmi5.xml
                    package_identifier=https://avacom.edu/courses/math-001
    """

    host_id = serializers.CharField(max_length=64)
    curso_id = serializers.CharField(max_length=40)
    curso_version_id = serializers.CharField(max_length=40, required=False, allow_null=True)
    formato_contenido = serializers.ChoiceField(
        choices=CourseHost.FORMATOS, required=False, allow_null=True, default=None
    )
    package_identifier = serializers.CharField(max_length=500, required=False, allow_null=True)
    package_version = serializers.CharField(max_length=32, required=False, allow_null=True)
    manifest_tipo = serializers.CharField(max_length=32, required=False, allow_null=True)
    manifest_ref = serializers.CharField(max_length=500, required=False, allow_null=True)
    package_ref = serializers.CharField(max_length=500, required=False, allow_null=True)
    package_huella = serializers.CharField(max_length=64, required=False, allow_null=True)
    disponible_estudiante = serializers.BooleanField(required=False, allow_null=True, default=None)
    actor = serializers.CharField(max_length=64, required=False, default="docente-ops")


class CourseHostTargetSerializer(serializers.Serializer):
    """
    Identifica la fila y quién actúa.

    curso_version_id es opcional: sin él, retire() quita todas las versiones del
    curso en ese host, y las demás acciones exigen que haya solo una.
    """

    host_id = serializers.CharField(max_length=64)
    curso_id = serializers.CharField(max_length=40)
    curso_version_id = serializers.CharField(max_length=40, required=False, allow_null=True)
    actor = serializers.CharField(max_length=64, required=False, default="docente-ops")


class CourseHostAvailabilitySerializer(CourseHostTargetSerializer):
    disponible_estudiante = serializers.BooleanField()


class CourseHostVerifySerializer(CourseHostTargetSerializer):
    package_huella = serializers.CharField(max_length=64, required=False, allow_null=True)


class LessonProgressSerializer(serializers.ModelSerializer):
    """
    Progreso de una lección. Se indexa por el CÓDIGO lógico, no por la fila
    física de m05_leccion: así sobrevive a reinstalar y a subir de versión.
    """

    curso_titulo = serializers.CharField(source="curso.titulo", read_only=True)

    class Meta:
        model = LessonProgress
        fields = "__all__"
        read_only_fields = ["id", "creado_en", "secuencia", "iniciado_en"]

    def validate_porcentaje(self, valor):
        if valor < 0 or valor > 100:
            raise serializers.ValidationError("El porcentaje tiene que estar entre 0 y 100.")
        return valor
