import logging
from decimal import Decimal, ROUND_HALF_UP

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

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
    now_ms,
)
from .serializers import (
    ActivityDetailSerializer,
    CourseHostSerializer,
    ActivitySerializer,
    AuditLogSerializer,
    CourseDetailSerializer,
    CourseEnrollmentSerializer,
    CourseSerializer,
    CourseVersionSerializer,
    CurriculumFrameworkSerializer,
    LearningResourceSerializer,
    LessonItemSerializer,
    LessonSerializer,
    QuizAnswerResultSerializer,
    QuizAnswerWriteSerializer,
    QuizAttemptSerializer,
    QuizFinishSerializer,
    QuizOptionAdminSerializer,
    QuizProgressSerializer,
    QuizQuestionAdminSerializer,
    QuizStartSerializer,
    SectionSerializer,
)

logger = logging.getLogger(__name__)


def broadcast_activity(activity_id, event_type, staff_only=False, **data):
    payload = {"type": event_type, "activity_id": str(activity_id), **data}
    group = f"activity_staff_{activity_id}" if staff_only else f"activity_{activity_id}"
    async_to_sync(get_channel_layer().group_send)(group, {"type": "activity.event", "payload": payload})


def course_queryset():
    # Las secciones cuelgan de la VERSIÓN, así que el prefetch entra por el
    # puntero version_activa. Un curso sin versión publicada trae la lista vacía.
    return Course.objects.select_related("curriculum_framework", "version_activa").prefetch_related(
        "inscripciones",
        "version_activa__secciones__lecciones__items__recurso",
        "version_activa__secciones__lecciones__items__actividad__preguntas__opciones",
    )


class NativeCollectionAPIView(APIView):
    """CRUD simple con APIView; no usa ViewSets, routers ni capas adicionales."""

    model = None
    serializer_class = None
    order_by = None

    def get_queryset(self, request):
        queryset = self.model.objects.all()
        if self.order_by:
            queryset = queryset.order_by(*self.order_by)
        return queryset

    def get(self, request):
        return Response(self.serializer_class(self.get_queryset(request), many=True).data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        logger.info("crud_created table=%s id=%s", instance._meta.db_table, instance.pk)
        return Response(self.serializer_class(instance).data, status=status.HTTP_201_CREATED)


class NativeDetailAPIView(APIView):
    model = None
    serializer_class = None

    def get_object(self, pk):
        return get_object_or_404(self.model, pk=pk)

    def get(self, _request, pk):
        return Response(self.serializer_class(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = self.serializer_class(self.get_object(pk), data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.serializer_class(serializer.save()).data)

    def patch(self, request, pk):
        serializer = self.serializer_class(self.get_object(pk), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(self.serializer_class(serializer.save()).data)

    def delete(self, _request, pk):
        instance = self.get_object(pk)
        logger.info("crud_deleted table=%s id=%s", instance._meta.db_table, instance.pk)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurriculumFrameworkCollectionView(NativeCollectionAPIView):
    model = CurriculumFramework
    serializer_class = CurriculumFrameworkSerializer
    order_by = ("orden",)


class CurriculumFrameworkDetailView(NativeDetailAPIView):
    model = CurriculumFramework
    serializer_class = CurriculumFrameworkSerializer


def _cursos_visibles_para_estudiante(queryset, host_id):
    """
    Qué puede abrir un estudiante en ESTA OPS.

    No alcanza con m05_curso.estado: ese es estado editorial y a propósito no lo
    toca desinstalar, porque el mismo curso puede seguir habilitado y presente en
    otra sede. Lo que manda acá es la presencia física en este equipo.

    La regla tiene dos mitades, y la segunda es la que evita una regresión:

        · un curso CON filas en m05_curso_host para esta OPS se ve solo si alguna
          está presente y habilitada — así, al eliminarlo, desaparece;
        · un curso SIN filas para esta OPS se rige por su estado, como antes. Los
          cursos hechos a mano en el asistente del Master no tienen fila de
          presencia y viven únicamente acá: filtrarlos por presencia los borraría
          de la vista sin motivo.
    """
    con_presencia = set(
        CourseHost.objects.filter(host_id=host_id).values_list("curso_id", flat=True)
    )
    abiertos = set(
        CourseHost.objects.filter(
            host_id=host_id, presente_local=True, disponible_estudiante=True
        ).values_list("curso_id", flat=True)
    )
    habilitados = queryset.filter(estado=Course.ESTADO_HABILITADO)
    return [
        curso for curso in habilitados
        if curso.pk not in con_presencia or curso.pk in abiertos
    ]


class CourseCollectionView(APIView):
    def get(self, request):
        queryset = course_queryset()
        if request.query_params.get("student") == "1":
            # El host lo dice la propia OPS; se puede forzar por query para probar.
            host_id = (request.query_params.get("host_id") or "").strip() or settings.AVACOM_HOST_ID
            visibles = _cursos_visibles_para_estudiante(queryset, host_id)
            return Response(CourseDetailSerializer(visibles, many=True).data)
        elif request.query_params.get("estado"):
            queryset = queryset.filter(estado=request.query_params["estado"])
        return Response(CourseDetailSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = CourseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        AuditLog.objects.create(
            actor_id=course.creado_por,
            accion="curso.creado",
            objeto_tabla=course._meta.db_table,
            objeto_id=course.id,
            valor_nuevo=course.estado,
        )
        return Response(CourseSerializer(course).data, status=status.HTTP_201_CREATED)


class CourseDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(course_queryset(), pk=pk)

    def get(self, _request, pk):
        return Response(CourseDetailSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        return self._save(request, pk, partial=False)

    def patch(self, request, pk):
        return self._save(request, pk, partial=True)

    def _save(self, request, pk, partial):
        course = self.get_object(pk)
        previous = course.estado
        serializer = CourseSerializer(course, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        if previous != course.estado:
            AuditLog.objects.create(
                actor_id=course.creado_por,
                accion="curso.estado_actualizado",
                objeto_tabla=course._meta.db_table,
                objeto_id=course.id,
                valor_anterior=previous,
                valor_nuevo=course.estado,
            )
        return Response(CourseDetailSerializer(self.get_object(pk)).data)

    def delete(self, _request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseVersionCollectionView(NativeCollectionAPIView):
    model = CourseVersion
    serializer_class = CourseVersionSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.query_params.get("curso_id"):
            queryset = queryset.filter(curso_id=request.query_params["curso_id"])
        return queryset


class CourseVersionDetailView(NativeDetailAPIView):
    model = CourseVersion
    serializer_class = CourseVersionSerializer


class EnrollmentCollectionView(NativeCollectionAPIView):
    model = CourseEnrollment
    serializer_class = CourseEnrollmentSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.query_params.get("curso_id"):
            queryset = queryset.filter(curso_id=request.query_params["curso_id"])
        return queryset

    def post(self, request):
        response = super().post(request)
        if response.status_code == status.HTTP_201_CREATED:
            AuditLog.objects.create(
                actor_id=request.data.get("creado_por"),
                accion="curso.estudiante_asignado",
                objeto_tabla="m05_curso_estudiante",
                objeto_id=response.data["id"],
                valor_nuevo=response.data["persona_id"],
            )
        return response


class EnrollmentDetailView(NativeDetailAPIView):
    model = CourseEnrollment
    serializer_class = CourseEnrollmentSerializer


class SectionCollectionView(NativeCollectionAPIView):
    model = Section
    serializer_class = SectionSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # ?curso_version_id= es el filtro natural ahora que la sección cuelga de
        # la versión. Se mantiene ?curso_id= por compatibilidad: resuelve a
        # través del puntero, devolviendo las secciones de la versión publicada.
        if request.query_params.get("curso_version_id"):
            queryset = queryset.filter(curso_version_id=request.query_params["curso_version_id"])
        elif request.query_params.get("curso_id"):
            queryset = queryset.filter(
                curso_version__curso__version_activa=F("curso_version_id"),
                curso_version__curso_id=request.query_params["curso_id"],
            )
        return queryset


class SectionDetailView(NativeDetailAPIView):
    model = Section
    serializer_class = SectionSerializer


class LessonCollectionView(NativeCollectionAPIView):
    model = Lesson
    serializer_class = LessonSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.query_params.get("seccion_id"):
            queryset = queryset.filter(seccion_id=request.query_params["seccion_id"])
        return queryset


class LessonDetailView(NativeDetailAPIView):
    model = Lesson
    serializer_class = LessonSerializer


class LearningResourceCollectionView(NativeCollectionAPIView):
    model = LearningResource
    serializer_class = LearningResourceSerializer


class LearningResourceDetailView(NativeDetailAPIView):
    model = LearningResource
    serializer_class = LearningResourceSerializer


class ActivityCollectionView(NativeCollectionAPIView):
    model = Activity
    serializer_class = ActivitySerializer


class ActivityDetailView(NativeDetailAPIView):
    model = Activity
    serializer_class = ActivitySerializer


class LessonItemCollectionView(NativeCollectionAPIView):
    model = LessonItem
    serializer_class = LessonItemSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.query_params.get("leccion_id"):
            queryset = queryset.filter(leccion_id=request.query_params["leccion_id"])
        return queryset


class LessonItemDetailView(NativeDetailAPIView):
    model = LessonItem
    serializer_class = LessonItemSerializer


class AuditLogCollectionView(NativeCollectionAPIView):
    model = AuditLog
    serializer_class = AuditLogSerializer


class AuditLogDetailView(NativeDetailAPIView):
    model = AuditLog
    serializer_class = AuditLogSerializer


class QuizQuestionCollectionView(NativeCollectionAPIView):
    model = QuizQuestion
    serializer_class = QuizQuestionAdminSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request).prefetch_related("opciones")
        if request.query_params.get("actividad_id"):
            queryset = queryset.filter(actividad_id=request.query_params["actividad_id"])
        return queryset


class QuizQuestionDetailView(NativeDetailAPIView):
    model = QuizQuestion
    serializer_class = QuizQuestionAdminSerializer


class QuizOptionCollectionView(NativeCollectionAPIView):
    model = QuizOption
    serializer_class = QuizOptionAdminSerializer

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.query_params.get("pregunta_id"):
            queryset = queryset.filter(pregunta_id=request.query_params["pregunta_id"])
        return queryset


class QuizOptionDetailView(NativeDetailAPIView):
    model = QuizOption
    serializer_class = QuizOptionAdminSerializer


class QuizPublicView(APIView):
    def get(self, _request, activity_id):
        activity = get_object_or_404(
            Activity.objects.prefetch_related("preguntas__opciones"),
            pk=activity_id,
            activity_type="quiz",
            estado="activa",
        )
        return Response(ActivityDetailSerializer(activity).data)


class QuizStartView(APIView):
    def post(self, request):
        serializer = QuizStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = serializer.save()
        payload = QuizAttemptSerializer(attempt).data
        broadcast_activity(
            attempt.actividad_id,
            "student_progress",
            staff_only=True,
            attempt=payload,
        )
        return Response(payload, status=status.HTTP_201_CREATED)


class QuizAnswerView(APIView):
    def post(self, request):
        serializer = QuizAnswerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer = serializer.save()
        attempt = answer.intento
        attempt.pregunta_actual = max(attempt.pregunta_actual, answer.pregunta.orden)
        attempt.save(update_fields=["pregunta_actual"])
        payload = QuizAttemptSerializer(attempt).data
        broadcast_activity(attempt.actividad_id, "student_progress", staff_only=True, attempt=payload)
        return Response({"saved": True, "answer_id": answer.id}, status=status.HTTP_201_CREATED)


class QuizProgressView(APIView):
    def post(self, request):
        serializer = QuizProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = serializer.validated_data["intento"]
        attempt.pregunta_actual = serializer.validated_data["pregunta_actual"]
        attempt.save(update_fields=["pregunta_actual"])
        payload = QuizAttemptSerializer(attempt).data
        broadcast_activity(attempt.actividad_id, "student_progress", staff_only=True, attempt=payload)
        return Response(payload)


class QuizFinishView(APIView):
    @transaction.atomic
    def post(self, request):
        serializer = QuizFinishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = get_object_or_404(
            QuizAttempt.objects.select_for_update().select_related("actividad"),
            pk=serializer.validated_data["intento_id"],
        )
        if attempt.estado != QuizAttempt.ESTADO_FINALIZADO:
            correct = attempt.respuestas.filter(es_correcta=True).count()
            total = max(attempt.total_preguntas, 1)
            attempt.puntaje = (Decimal(correct) * attempt.actividad.max_score / Decimal(total)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            attempt.estado = QuizAttempt.ESTADO_FINALIZADO
            attempt.pregunta_actual = attempt.total_preguntas
            attempt.finalizado_en = now_ms()
            attempt.save(update_fields=["puntaje", "estado", "pregunta_actual", "finalizado_en"])

        # La nota alimenta el progreso de la lección que contiene esta actividad.
        # Se hace aquí y no en el cliente para que el avance no dependa de que la
        # tableta lo reporte aparte: si se apaga justo después de responder, el
        # progreso ya quedó guardado.
        from .progress import record_quiz_completion

        record_quiz_completion(attempt)

        payload = QuizAttemptSerializer(attempt).data
        broadcast_activity(attempt.actividad_id, "attempt_finished", staff_only=True, attempt=payload)
        return Response(payload)


class QuizResultsView(APIView):
    def get(self, request):
        queryset = QuizAttempt.objects.select_related("actividad").prefetch_related("respuestas").all()
        if request.query_params.get("actividad_id"):
            queryset = queryset.filter(actividad_id=request.query_params["actividad_id"])
        return Response(QuizAttemptSerializer(queryset, many=True).data)


class QuizResultDetailView(APIView):
    def get(self, _request, attempt_id):
        attempt = get_object_or_404(
            QuizAttempt.objects.select_related("actividad").prefetch_related(
                "respuestas__pregunta__opciones", "respuestas__opcion"
            ),
            pk=attempt_id,
        )
        return Response(
            {
                "summary": QuizAttemptSerializer(attempt).data,
                "answers": QuizAnswerResultSerializer(attempt.respuestas.all(), many=True).data,
            }
        )


# ═══════════════════════════════════════════════════════════════════════════
# CATÁLOGO VERSIONADO
#
# Django decide QUÉ VERSIÓN ESTÁ PUBLICADA; el cliente decide si PUEDE activar
# lo que tiene. Por eso la activación y el rollback son operaciones de servidor
# y transaccionales, y viven en exams.catalog.
# ═══════════════════════════════════════════════════════════════════════════


class CourseVersionListView(APIView):
    """GET · las versiones del curso con su estado y sus conteos."""

    def get(self, request, course_id):
        from .serializers import CourseVersionSummarySerializer

        curso = get_object_or_404(Course.objects.select_related("version_activa"), pk=course_id)
        versiones = CourseVersion.objects.filter(curso=curso).order_by("version")
        datos = CourseVersionSummarySerializer(versiones, many=True, context={}).data
        return Response({"course_id": curso.id, "titulo": curso.titulo, "versiones": datos})


class CourseManifestView(APIView):
    """
    GET · qué versión debería tener el cliente, con su huella.

    Deliberadamente pequeño: se consulta seguido por la Wi-Fi del aula. El
    cliente compara la huella con lo instalado y solo entonces baja el paquete.
    """

    def get(self, request, course_id):
        from .serializers import CourseManifestSerializer, CourseVersionSummarySerializer

        curso = get_object_or_404(Course.objects.select_related("version_activa"), pk=course_id)
        versiones = CourseVersion.objects.filter(curso=curso).order_by("version")
        resumen = CourseVersionSummarySerializer(versiones, many=True, context={}).data
        return Response(CourseManifestSerializer.build(curso, resumen))


class CourseVersionPackageView(APIView):
    """GET · el paquete completo de una versión, en el schema avacom-course-package/v1."""

    def get(self, request, version_id):
        from .serializers import build_version_package

        version = get_object_or_404(CourseVersion, pk=version_id)
        return Response(build_version_package(version))


class CourseVersionActivateView(APIView):
    """POST · publica una versión ya instalada. Transaccional."""

    def post(self, request, version_id):
        from .catalog import CatalogError, activate_version
        from .serializers import CourseVersionSummarySerializer

        actor = request.data.get("actor") or "docente-ops"
        try:
            version, saliente_id = activate_version(version_id, actor=actor)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "activada": CourseVersionSummarySerializer(version, context={}).data,
            "version_saliente_id": saliente_id,
        })


class CourseRollbackView(APIView):
    """POST · vuelve a publicar una versión anterior. Son UPDATE, ni un DELETE."""

    def post(self, request, course_id):
        from .catalog import CatalogError, rollback_version
        from .serializers import CourseVersionSummarySerializer

        actor = request.data.get("actor") or "docente-ops"
        destino = request.data.get("version_id")
        try:
            version, saliente_id = rollback_version(course_id, destino, actor=actor)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "activada": CourseVersionSummarySerializer(version, context={}).data,
            "version_saliente_id": saliente_id,
        })


class CoursePackageInspectView(APIView):
    """
    POST · vista previa del paquete SIN escribir nada.

    Es lo que la OPS muestra al docente después de elegir el archivo: cuántas
    secciones trae, si el curso ya existe, si esa versión ya está instalada.
    Confirmar es un segundo paso deliberado.
    """

    def post(self, request):
        from .package_install import PackageError, inspect_package

        try:
            return Response(inspect_package(request.data))
        except PackageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CoursePackageImportView(APIView):
    """
    POST · instala el paquete en una transacción y lo deja disponible.

    El cuerpo es el JSON del paquete tal cual, más tres campos opcionales que
    solo se usan si el curso todavía no existe —el paquete declara su course_id
    pero no su título ni su marco curricular—:
        _titulo, _curriculum_framework, _docente_id
    y dos de control:
        _actor, _activar   (por omisión se respeta publication.activate_after_install)
    """

    def post(self, request):
        from .package_install import PackageError, install_package

        cuerpo = dict(request.data or {})
        titulo = cuerpo.pop("_titulo", None)
        marco = cuerpo.pop("_curriculum_framework", None)
        docente = cuerpo.pop("_docente_id", None)
        actor = cuerpo.pop("_actor", None)
        activar = cuerpo.pop("_activar", None)

        try:
            resumen = install_package(
                cuerpo,
                titulo=titulo,
                curriculum_framework=marco,
                docente_id=docente,
                actor=actor,
                activate=activar,
            )
        except PackageError as exc:
            # La base quedó como estaba: el fallo ya se auditó con resultado='error'.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        codigo = status.HTTP_200_OK if resumen["idempotente"] else status.HTTP_201_CREATED
        return Response(resumen, status=codigo)


# ═══════════════════════════════════════════════════════════════════════════
# PRESENCIA FÍSICA EN UN HOST · m05_curso_host
#
# CRUD directo, más cuatro acciones que preservan las invariantes. La regla que
# gobierna todo esto:
#
#     DESINSTALAR CONTENIDO  ≠  BORRAR ENTIDADES ACADÉMICAS
#
# Por eso DELETE sobre una fila está permitido pero desaconsejado: borra el
# rastro de que ese curso estuvo instalado. Para desinstalar se usa /retire/.
#
# Neutral al estándar: SCORM y CMI5 se distinguen solo por formato_contenido y
# el descriptor. El parser de cada formato los transforma al mismo árbol.
# ═══════════════════════════════════════════════════════════════════════════


class CourseHostCollectionView(NativeCollectionAPIView):
    """
    GET  · lista. Filtros: ?host_id= ?curso_id= ?curso_version_id=
           ?formato_contenido= ?presente_local= ?disponible_estudiante=
    POST · crea una fila a mano. Para el caso normal usa /install/, que además audita.
    """

    model = CourseHost
    serializer_class = CourseHostSerializer

    def get_queryset(self, request):
        queryset = CourseHost.objects.select_related("curso", "curso_version").all()
        for campo in ("host_id", "curso_id", "curso_version_id", "formato_contenido"):
            valor = request.query_params.get(campo)
            if valor:
                queryset = queryset.filter(**{campo: valor.strip()})
        for campo in ("presente_local", "disponible_estudiante"):
            crudo = request.query_params.get(campo)
            if crudo is not None:
                queryset = queryset.filter(**{campo: crudo.lower() in ("1", "true", "si")})
        return queryset


class CourseHostDetailView(NativeDetailAPIView):
    model = CourseHost
    serializer_class = CourseHostSerializer

    def get_object(self, pk):
        return get_object_or_404(
            CourseHost.objects.select_related("curso", "curso_version"), pk=pk
        )


class CourseHostFormatsView(APIView):
    """GET · qué formatos de paquete reconoce el prototipo, para poblar un desplegable."""

    def get(self, _request):
        return Response([
            {
                "clave": clave,
                "nombre": nombre,
                "manifest_tipo": {
                    "scorm_12": "imsmanifest",
                    "scorm_2004": "imsmanifest",
                    "cmi5": "cmi5",
                    "avacom_v1": "avacom",
                }.get(clave),
                "manifest_ref_habitual": {
                    "scorm_12": "imsmanifest.xml",
                    "scorm_2004": "imsmanifest.xml",
                    "cmi5": "cmi5.xml",
                    "avacom_v1": "<paquete>.json",
                }.get(clave),
            }
            for clave, nombre in CourseHost.FORMATOS
        ])


class CourseHostInstallView(APIView):
    """
    POST · registra una versión de un curso como presente en un host.

    Idempotente por (host, curso, versión): reinstalar el mismo paquete no crea
    otro registro. Instalar una versión distinta sí crea una fila nueva, y así
    queda el historial de qué estuvo instalado en este equipo.
    """

    def post(self, request):
        from .hosts import HostError, register_install
        from .serializers import CourseHostInstallSerializer

        entrada = CourseHostInstallSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        try:
            fila, creada = register_install(
                host_id=d["host_id"],
                course_id=d["curso_id"],
                version_id=d.get("curso_version_id"),
                formato_contenido=d.get("formato_contenido"),
                package_identifier=d.get("package_identifier"),
                package_version=d.get("package_version"),
                manifest_tipo=d.get("manifest_tipo"),
                manifest_ref=d.get("manifest_ref"),
                package_ref=d.get("package_ref"),
                package_huella=d.get("package_huella"),
                disponible_estudiante=d.get("disponible_estudiante"),
                actor=d.get("actor") or "docente-ops",
            )
        except HostError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"creada": creada, "host": CourseHostSerializer(fila).data},
            status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK,
        )


class CourseHostRetireView(APIView):
    """
    POST · desinstala el paquete de este host.

    Sin curso_version_id quita TODAS las versiones del curso en ese host, que es
    lo que se espera de «quitar el curso de esta OPS».

    Apaga las banderas y sella retirado_en. NO borra el curso, ni las
    inscripciones, ni las notas, ni los intentos, y NO toca m05_curso.estado.
    """

    def post(self, request):
        from .hosts import HostError, retire
        from .serializers import CourseHostTargetSerializer

        entrada = CourseHostTargetSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        try:
            filas, afectadas = retire(
                d["host_id"], d["curso_id"],
                version_id=d.get("curso_version_id"),
                actor=d.get("actor") or "docente-ops",
            )
        except HostError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        mensaje = (
            f"{len(afectadas)} version(es) desinstalada(s) de este host. "
            "El curso y las inscripciones siguen intactos."
            if afectadas else "Ya estaba desinstalado en este host."
        )
        return Response({
            "cambio": bool(afectadas),
            "desinstaladas": len(afectadas),
            "mensaje": mensaje,
            "hosts": CourseHostSerializer(filas, many=True).data,
        })


class CourseHostAvailabilityView(APIView):
    """
    POST · abre o cierra el curso a los estudiantes de este host.

    Solo una versión puede estar ofrecida por (host, curso): al abrir una, se
    cierra la otra primero.
    """

    def post(self, request):
        from .hosts import HostError, set_availability
        from .serializers import CourseHostAvailabilitySerializer

        entrada = CourseHostAvailabilitySerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        try:
            fila, cambio = set_availability(
                d["host_id"], d["curso_id"], d["disponible_estudiante"],
                version_id=d.get("curso_version_id"),
                actor=d.get("actor") or "docente-ops",
            )
        except HostError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"cambio": cambio, "host": CourseHostSerializer(fila).data})


class CourseHostVerifyView(APIView):
    """
    POST · sella la comprobación física del paquete.

    Si la huella recibida no coincide con la registrada, el curso se cierra a los
    estudiantes y responde 409: los archivos del disco no son los que se
    instalaron.
    """

    def post(self, request):
        from .hosts import HostError, mark_verified
        from .serializers import CourseHostVerifySerializer

        entrada = CourseHostVerifySerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        try:
            fila = mark_verified(
                d["host_id"], d["curso_id"],
                package_huella=d.get("package_huella"),
                version_id=d.get("curso_version_id"),
                actor=d.get("actor") or "docente-ops",
            )
        except HostError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(CourseHostSerializer(fila).data)


class HostCourseListView(APIView):
    """GET · qué cursos hay en este host, con su estado de presencia y su formato."""

    def get(self, request, host_id):
        filas = list(
            CourseHost.objects.select_related("curso", "curso_version")
            .filter(host_id=host_id.strip())
            .order_by("curso__titulo", "curso_version__version")
        )
        por_formato = {}
        for f in filas:
            por_formato[f.formato_contenido] = por_formato.get(f.formato_contenido, 0) + 1
        return Response({
            "host_id": host_id,
            "filas": len(filas),
            "cursos_distintos": len({f.curso_id for f in filas}),
            "instalados": sum(1 for f in filas if f.presente_local),
            "disponibles": sum(1 for f in filas if f.disponible_estudiante),
            "desinstalados": sum(1 for f in filas if not f.presente_local),
            "por_formato": por_formato,
            "cursos": CourseHostSerializer(filas, many=True).data,
        })


class HostInstalledCoursesView(APIView):
    """
    GET /api/hosts/{host_id}/installed/

    Una tarjeta por CURSO presente en esta OPS, no una por fila de
    m05_curso_host: la tabla lleva una fila por (host, curso, versión) y la
    pantalla «Eliminar curso» razona por curso.

    Cada tarjeta trae lo que se CONSERVARÍA al eliminar. Sin esos números la
    advertencia de la interfaz sería una promesa; con ellos el docente ve, antes
    de confirmar, cuántos estudiantes y cuánto progreso sobreviven.
    """

    def get(self, request, host_id):
        host_id = host_id.strip()
        filas = (
            CourseHost.objects.select_related("curso", "curso_version")
            .filter(host_id=host_id, presente_local=True)
            .order_by("curso__titulo", "-curso_version__version")
        )

        # Una fila por curso: la de mayor versión, que es la que el estudiante ve.
        por_curso = {}
        for fila in filas:
            por_curso.setdefault(fila.curso_id, fila)

        salida = []
        for fila in por_curso.values():
            curso = fila.curso
            salida.append({
                "course_id": curso.pk,
                "name": curso.titulo,
                "course_state": curso.estado,
                "version": fila.curso_version.version if fila.curso_version_id else None,
                "content_format": fila.formato_contenido,
                "format_label": fila.get_formato_contenido_display(),
                "package_identifier": fila.package_identifier,
                "manifest_tipo": fila.manifest_tipo,
                "installed": True,
                "available": fila.disponible_estudiante,
                "installed_at": fila.instalado_en,
                # Lo que sobrevive a la eliminación (§11, AC-03 a AC-06).
                "preserved": {
                    "students": curso.inscripciones.count(),
                    "progress_rows": LessonProgress.objects.filter(curso=curso).count(),
                    "quiz_attempts": QuizAttempt.objects.filter(
                        actividad__lesson_items__leccion__seccion__curso_version__curso=curso
                    ).distinct().count(),
                },
            })

        return Response({
            "host_id": host_id,
            "cursos": len(salida),
            "disponibles": sum(1 for c in salida if c["available"]),
            "courses": salida,
        })


class StudentHostCatalogView(APIView):
    """
    GET · qué ve un estudiante en ESTE host, incluido lo que ya no está.

    Parte de la MATRÍCULA y no del catálogo, para que un curso desinstalado siga
    apareciendo con su estado en lugar de desvanecerse sin explicación.
    """

    def get(self, request, persona_id):
        from .hosts import courses_for_student

        host_id = request.query_params.get("host_id", "").strip()
        if not host_id:
            return Response(
                {"detail": "Indica ?host_id= para saber qué hay instalado en este equipo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            "persona_id": persona_id,
            "host_id": host_id,
            "cursos": courses_for_student(persona_id, host_id),
        })


# ═══════════════════════════════════════════════════════════════════════════
# API DEL SPEC · §19
#
# Las rutas con los nombres que pide el spec. Se apoyan en lo que ya existe
# (exams.hosts, exams.progress, exams.packages, exams.package_install) para que
# haya un solo camino de instalación, venga el paquete de SCORM, de CMI5 o del
# formato nativo.
#
# La regla que gobierna todo:  DESINSTALAR CONTENIDO ≠ BORRAR LO ACADÉMICO
# Por eso NO hay DELETE /api/courses/{id}/ en este bloque, a propósito.
# ═══════════════════════════════════════════════════════════════════════════


def _host_de(request):
    return (
        request.query_params.get("host_id")
        or request.data.get("host_id") if hasattr(request, "data") else None
    ) or request.query_params.get("host_id") or ""


class AvailableCoursesView(APIView):
    """
    GET /api/courses/available/[?host_id=]

    Los cursos que un estudiante puede abrir HOY en esta OPS. Exige las dos
    banderas, que es el AC-02 del spec:
        presente_local = 1  AND  disponible_estudiante = 1

    Sin ?host_id= responde por la OPS que atiende la petición
    (settings.AVACOM_HOST_ID). Es el endpoint para comprobar de un vistazo qué
    ve la tableta, sin tener que averiguar primero la identidad del equipo; el
    parámetro sigue estando para consultar otra sede.
    """

    def get(self, request):
        host_id = (request.query_params.get("host_id") or "").strip() or settings.AVACOM_HOST_ID

        filas = (
            CourseHost.objects.select_related("curso", "curso_version")
            .filter(host_id=host_id, presente_local=True, disponible_estudiante=True)
            .order_by("curso__titulo")
        )
        salida = []
        for fila in filas:
            salida.append({
                "course_id": fila.curso_id,
                "name": fila.curso.titulo,
                "version": fila.curso_version.version if fila.curso_version_id else None,
                "content_format": fila.formato_contenido,
                "package_identifier": fila.package_identifier,
                "installed": True,
                "available": True,
                "installed_at": fila.instalado_en,
                "students": fila.curso.inscripciones.count(),
            })
        return Response({"host_id": host_id, "count": len(salida), "courses": salida})


class CourseHistoryView(APIView):
    """
    GET /api/courses/history/?host_id=

    Todos los cursos que esta OPS conoce, disponibles o no. Es la pantalla 2 del
    spec (§15): sirve para demostrar que la información académica permanece
    aunque el contenido se haya retirado.
    """

    def get(self, request):
        host_id = (request.query_params.get("host_id") or "").strip()

        presencia = {}
        if host_id:
            for fila in CourseHost.objects.select_related("curso_version").filter(host_id=host_id):
                presencia.setdefault(fila.curso_id, []).append(fila)

        salida = []
        for curso in Course.objects.select_related("version_activa").prefetch_related("inscripciones"):
            filas = presencia.get(curso.id, [])
            mejor = _mejor_fila_host(filas)
            inscripciones = list(curso.inscripciones.all())
            con_progreso = (
                LessonProgress.objects.filter(curso=curso, porcentaje__gt=0)
                .values("persona_id").distinct().count()
            )
            salida.append({
                "course_id": curso.id,
                "name": curso.titulo,
                "course_state": curso.estado,
                "version": curso.version_activa.version if curso.version_activa_id else None,
                "content_format": mejor.formato_contenido if mejor else None,
                "installed": bool(mejor and mejor.presente_local),
                "available": bool(mejor and mejor.disponible_estudiante),
                "host_state": mejor.estado_legible if mejor else "no instalado",
                "retired_at": mejor.retirado_en if mejor else None,
                "versions_on_host": len(filas),
                "students": len(inscripciones),
                "students_with_progress": con_progreso,
            })
        return Response({"host_id": host_id or None, "count": len(salida), "courses": salida})


def _mejor_fila_host(filas):
    from .hosts import _mejor_fila

    return _mejor_fila(filas)


class CoursePackageZipInstallView(APIView):
    """
    POST /api/course-packages/install/

    Instala un paquete SCORM o CMI5. El flujo es el §9 del spec:
        recibir .zip -> detectar formato -> leer descriptor -> obtener
        identificador -> ¿existe el curso? -> ¿existe la versión? -> importar la
        estructura -> registrar en m05_curso_host -> validar -> habilitar

    Acepta el .zip de dos maneras:
        multipart/form-data con el archivo en `package`
        application/json con `package_base64`

    Y con ?preview=1 (o "preview": true) NO escribe nada: solo devuelve lo
    detectado, que es lo que alimenta la pantalla «Agregar contenido» (§16).
    """

    # DEFAULT_PARSER_CLASSES es JSONParser a secas: sin esta línea el multipart
    # se rechaza con 415 y request.FILES nunca se llena. FormParser entra porque
    # el resto del formulario (host_id, titulo, marco) viaja junto al archivo.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        import base64

        from .hosts import HostError, register_install, set_availability
        from .package_install import PackageError, install_package
        from .packages import PackageFormatError, read_package, to_course_package

        archivo = request.FILES.get("package") or request.FILES.get("file")
        if archivo is not None:
            datos = archivo.read()
            nombre = archivo.name
        else:
            crudo = request.data.get("package_base64")
            if not crudo:
                return Response(
                    {"detail": "Envía el .zip en el campo `package` (multipart) o "
                               "`package_base64` (JSON)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                datos = base64.b64decode(crudo)
            except Exception:
                return Response({"detail": "package_base64 no es base64 válido."},
                                status=status.HTTP_400_BAD_REQUEST)
            nombre = request.data.get("package_name") or "paquete.zip"

        try:
            leido = read_package(datos)
        except PackageFormatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        host_id = (request.data.get("host_id") or "").strip()
        course_id = (request.data.get("course_id") or "").strip()
        titulo = request.data.get("titulo") or leido["titulo_curso"]
        marco = request.data.get("curriculum_framework")
        version = int(request.data.get("version") or 1)
        actor = request.data.get("actor") or "docente-ops"

        # El curso se reconoce por su package_identifier: es lo que hace que
        # reinstalar el mismo paquete NO cree otro curso (§13, AC-09, AC-10).
        existente = CourseHost.objects.filter(
            package_identifier=leido["package_identifier"]
        ).select_related("curso").first()
        if not course_id and existente is not None:
            course_id = existente.curso_id
        if not course_id:
            course_id = _course_id_desde_identificador(leido["package_identifier"])

        previo = Course.objects.filter(pk=course_id).first()
        vista_previa = str(
            request.query_params.get("preview") or request.data.get("preview") or ""
        ).lower() in ("1", "true", "si", "sí")

        detectado = {
            "package_name": nombre,
            "content_format": leido["formato_contenido"],
            "manifest_type": leido["manifest_tipo"],
            "manifest_ref": leido["manifest_ref"],
            "package_identifier": leido["package_identifier"],
            "package_version": leido.get("package_version"),
            "package_huella": leido["package_huella"],
            "detected_title": leido["titulo_curso"],
            "course_id": course_id,
            "course_exists": previo is not None,
            "existing_title": previo.titulo if previo else None,
            "version": version,
            "counts": leido["conteos"],
        }

        if vista_previa:
            return Response({"preview": True, "detected": detectado})

        if not host_id:
            return Response(
                {"detail": "Indica host_id: la instalación registra la presencia en una OPS."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paquete = to_course_package(
            leido, course_id, version,
            activate_after_install=True, instalada_por=actor,
        )
        try:
            resumen = install_package(
                paquete, titulo=titulo, curriculum_framework=marco,
                docente_id=actor, actor=actor,
            )
        except PackageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Pasos 13-15 del §9: registrar la presencia, validar y habilitar.
        try:
            fila, creada = register_install(
                host_id=host_id,
                course_id=resumen["course_id"],
                version_id=resumen["version_id"],
                formato_contenido=leido["formato_contenido"],
                package_identifier=leido["package_identifier"],
                package_version=leido.get("package_version"),
                manifest_tipo=leido["manifest_tipo"],
                manifest_ref=leido["manifest_ref"],
                package_ref=nombre,
                package_huella=leido["package_huella"],
                actor=actor,
            )
            fila, _ = set_availability(
                host_id, resumen["course_id"], True,
                version_id=resumen["version_id"], actor=actor,
            )
        except HostError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "detected": detectado,
            "install": resumen,
            "host": CourseHostSerializer(fila).data,
            "message": "Curso instalado correctamente.",
        }, status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)


def _course_id_desde_identificador(identificador):
    """
    Un course_id estable y legible derivado del identificador del paquete.

    Determinista: el mismo paquete produce el mismo id en cualquier nodo, así que
    dos OPS que instalan el mismo .zip sin conexión coinciden.
    """
    import hashlib
    import re

    limpio = re.sub(r"[^A-Za-z0-9]+", "-", identificador or "").strip("-").upper()
    if not limpio:
        limpio = "CURSO"
    if len(limpio) <= 34:
        return f"CURSO-{limpio}"[:40]
    resumen = hashlib.sha256((identificador or "").encode()).hexdigest()[:8].upper()
    return f"CURSO-{limpio[:25]}-{resumen}"[:40]


class CourseUninstallView(APIView):
    """
    POST /api/courses/{course_id}/uninstall/

    El §11 del spec. Apaga las banderas, sella retirado_en y CONSERVA todo lo
    académico. Devuelve explícitamente qué se conservó, para que la advertencia
    de la interfaz pueda ser verificable y no solo una promesa.
    """

    def post(self, request, course_id):
        from .hosts import HostError, retire

        host_id = (request.data.get("host_id") or "").strip()
        if not host_id:
            return Response({"detail": "Indica host_id: se desinstala de una OPS concreta."},
                            status=status.HTTP_400_BAD_REQUEST)

        curso = get_object_or_404(Course, pk=course_id)
        antes = {
            "students": curso.inscripciones.count(),
            "progress_rows": LessonProgress.objects.filter(curso=curso).count(),
            "quiz_attempts": QuizAttempt.objects.filter(
                actividad__lesson_items__leccion__seccion__curso_version__curso=curso
            ).distinct().count(),
        }

        try:
            filas, afectadas = retire(
                host_id, course_id,
                version_id=request.data.get("curso_version_id"),
                actor=request.data.get("actor") or "docente-ops",
            )
        except HostError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        despues = {
            "students": curso.inscripciones.count(),
            "progress_rows": LessonProgress.objects.filter(curso=curso).count(),
            "quiz_attempts": QuizAttempt.objects.filter(
                actividad__lesson_items__leccion__seccion__curso_version__curso=curso
            ).distinct().count(),
        }
        curso.refresh_from_db()

        return Response({
            "course_id": course_id,
            "uninstalled_versions": len(afectadas),
            "course_state": curso.estado,
            "message": (
                "El contenido se retiró de esta OPS. Los estudiantes, el progreso, "
                "las calificaciones y el historial se conservaron."
            ),
            "preserved": {"before": antes, "after": despues, "intact": antes == despues},
            "hosts": CourseHostSerializer(filas, many=True).data,
        })


class StudentCoursesView(APIView):
    """
    GET /api/students/{student_id}/courses/?host_id=

    La respuesta del §19 del spec:
        {course_id, name, progress, installed, available}

    Parte de la MATRÍCULA y no del catálogo: un curso desinstalado sigue
    apareciendo con su progreso (§12, AC-08).
    """

    def get(self, request, student_id):
        from .progress import student_courses

        host_id = (request.query_params.get("host_id") or "").strip()
        if not host_id:
            return Response(
                {"detail": "Indica ?host_id= para distinguir lo asignado de lo disponible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cursos = student_courses(student_id, host_id)
        return Response({
            "student_id": student_id,
            "host_id": host_id,
            "available": [c for c in cursos if c["available"]],
            "unavailable": [c for c in cursos if not c["available"]],
            "courses": cursos,
        })


class StudentCourseProgressView(APIView):
    """
    GET  /api/students/{student_id}/courses/{course_id}/progress/
    POST igual ruta · registra el avance de una lección.

    El POST espera:
        {"leccion_codigo": "lesson.suma", "porcentaje": 50}

    El progreso se indexa por el CÓDIGO de la lección, no por su fila física:
    así sobrevive a desinstalar, reinstalar y subir de versión.
    """

    def get(self, _request, student_id, course_id):
        from .progress import ProgressError, course_progress

        try:
            return Response(course_progress(course_id, student_id))
        except ProgressError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, student_id, course_id):
        from .progress import ProgressError, course_progress, record_lesson_progress

        try:
            fila, cambio = record_lesson_progress(
                course_id,
                student_id,
                request.data.get("leccion_codigo"),
                request.data.get("porcentaje"),
                leccion_titulo=request.data.get("leccion_titulo"),
                actor=request.data.get("actor") or student_id,
            )
        except ProgressError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "updated": cambio,
            "lesson": {
                "leccion_codigo": fila.leccion_codigo,
                "porcentaje": float(fila.porcentaje),
                "estado": fila.estado,
            },
            "course": course_progress(course_id, student_id),
        })
