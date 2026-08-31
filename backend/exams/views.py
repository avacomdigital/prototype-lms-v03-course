import logging
from decimal import Decimal, ROUND_HALF_UP

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Activity,
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


class CourseCollectionView(APIView):
    def get(self, request):
        queryset = course_queryset()
        if request.query_params.get("student") == "1":
            queryset = queryset.filter(estado=Course.ESTADO_HABILITADO)
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
