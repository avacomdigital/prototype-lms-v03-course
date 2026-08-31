"""
Operaciones del catálogo versionado. Django es la fuente de verdad de QUÉ
VERSIÓN ESTÁ PUBLICADA: esa decisión es académica, no del dispositivo, y por eso
no se toma en el cliente.

Todo lo que mueve el puntero pasa por aquí. Ninguna vista ni comando debe
escribir `curso.version_activa` directamente: el orden de los UPDATE importa y
la invariante de la FK compuesta se impone en este módulo.
"""

from django.db import transaction

from .models import AuditLog, Course, CourseVersion, now_ms, sequence_value


class CatalogError(Exception):
    """Cualquier fallo que deba provocar ROLLBACK y quedar auditado."""


def _audit(actor, accion, tabla, objeto_id, anterior, nuevo, resultado="ok"):
    AuditLog.objects.create(
        actor_id=actor,
        accion=accion,
        objeto_tabla=tabla,
        objeto_id=objeto_id,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        resultado=resultado,
        ocurrido_en=now_ms(),
        secuencia=sequence_value(),
    )


@transaction.atomic
def activate_version(version_id, actor="sistema"):
    """
    Publica una fotografía ya instalada. Devuelve (version, saliente_id).

    El ORDEN es obligatorio: primero se libera el estado 'activa' de la versión
    saliente y solo después se asigna a la entrante, porque el índice único
    parcial ux_m05_cv_una_activa no admite dos activas del mismo curso. Al
    revés falla con UNIQUE constraint.

    La saliente pasa a 'instalada', NO a 'retirada': queda íntegra y disponible
    para un rollback.
    """
    try:
        version = CourseVersion.objects.select_related("curso").get(pk=version_id)
    except CourseVersion.DoesNotExist as exc:
        raise CatalogError(f"La versión {version_id} no existe.") from exc

    # Solo se publica lo que está completo e íntegro. Una fotografía en 'staged'
    # o en 'error' llegó a medias: activarla mostraría un curso roto.
    if version.estado not in (CourseVersion.ESTADO_INSTALADA, CourseVersion.ESTADO_RETIRADA):
        if version.estado == CourseVersion.ESTADO_ACTIVA:
            return version, None
        raise CatalogError(
            f"La versión {version_id} está en estado '{version.estado}'. "
            "Solo se puede activar una versión instalada o retirada."
        )

    curso = version.curso
    saliente = (
        CourseVersion.objects.filter(curso=curso, estado=CourseVersion.ESTADO_ACTIVA)
        .exclude(pk=version.pk)
        .first()
    )
    saliente_id = saliente.pk if saliente else None

    if saliente is not None:
        saliente.estado = CourseVersion.ESTADO_INSTALADA
        saliente.save(update_fields=["estado"])

    ahora = now_ms()
    version.estado = CourseVersion.ESTADO_ACTIVA
    version.activada_en = version.activada_en or ahora
    if version.activada_en < version.instalada_en:
        version.activada_en = version.instalada_en
    version.retirada_en = None
    version.save(update_fields=["estado", "activada_en", "retirada_en"])

    # INVARIANTE que el ORM no puede expresar: en el SQLite de referencia existe
    # la FK compuesta (version_activa_id, id) -> m05_curso_version (id, curso_id),
    # que garantiza en el motor que la versión activa pertenece a ESTE curso.
    # ForeignKey de Django apunta a una sola columna, así que la comprobación
    # vive aquí, en el único camino por el que se mueve el puntero.
    if version.curso_id != curso.id:
        raise CatalogError(
            f"La versión {version_id} pertenece al curso {version.curso_id}, "
            f"no a {curso.id}."
        )

    curso.version_activa = version
    curso.estado = Course.ESTADO_HABILITADO
    curso.save(update_fields=["version_activa", "estado"])

    _audit(actor, "curso.version.activada", "m05_curso", curso.id, saliente_id, version.pk)
    return version, saliente_id


@transaction.atomic
def rollback_version(course_id, target_version_id=None, actor="sistema"):
    """
    Vuelve a publicar una versión anterior. Son UPDATE, ni un solo DELETE.

    Sin `target_version_id` se elige la versión instalada más reciente distinta
    de la activa, que es lo que se espera de un «deshacer».
    """
    try:
        curso = Course.objects.get(pk=course_id)
    except Course.DoesNotExist as exc:
        raise CatalogError(f"El curso {course_id} no existe.") from exc

    actual_id = curso.version_activa_id

    if target_version_id is None:
        destino = (
            CourseVersion.objects.filter(
                curso=curso,
                estado__in=(CourseVersion.ESTADO_INSTALADA, CourseVersion.ESTADO_RETIRADA),
            )
            .exclude(pk=actual_id)
            .order_by("-version")
            .first()
        )
        if destino is None:
            raise CatalogError(
                f"El curso {course_id} no tiene otra versión instalada a la que volver."
            )
        target_version_id = destino.pk

    if target_version_id == actual_id:
        raise CatalogError("La versión destino del rollback ya es la activa.")

    version, saliente_id = activate_version(target_version_id, actor=actor)
    _audit(actor, "curso.version.rollback", "m05_curso", curso.id, actual_id, version.pk)
    return version, saliente_id


@transaction.atomic
def retire_version(version_id, actor="sistema"):
    """
    Retira una versión que ya no se publicará. Conserva TODO su contenido: la
    fila solo cambia de estado. Una versión activa no se puede retirar sin antes
    publicar otra, porque dejaría el curso habilitado sin nada que mostrar.
    """
    try:
        version = CourseVersion.objects.get(pk=version_id)
    except CourseVersion.DoesNotExist as exc:
        raise CatalogError(f"La versión {version_id} no existe.") from exc

    if version.estado == CourseVersion.ESTADO_ACTIVA:
        raise CatalogError(
            "No se puede retirar la versión activa: publica otra antes, o el "
            "curso quedaría habilitado sin contenido."
        )

    anterior = version.estado
    version.estado = CourseVersion.ESTADO_RETIRADA
    version.retirada_en = max(now_ms(), version.instalada_en)
    version.save(update_fields=["estado", "retirada_en"])
    _audit(actor, "curso.version.retirada", "m05_curso_version", version.pk, anterior, "retirada")
    return version


def version_counts(version):
    """Conteo de filas por versión. Es lo que sostiene la demostración: no baja nunca."""
    from .models import Lesson, LessonItem, Section

    secciones = Section.objects.filter(curso_version=version)
    lecciones = Lesson.objects.filter(seccion__curso_version=version)
    items = LessonItem.objects.filter(leccion__seccion__curso_version=version)
    return {
        "secciones": secciones.count(),
        "lecciones": lecciones.count(),
        "items": items.count(),
    }


def active_content(course_id):
    """
    El árbol de la versión activa. No menciona ningún número de versión: parte
    del curso y sigue el puntero. El día que se haga rollback devuelve la otra
    versión sin cambiarle una línea.
    """
    from .models import Section

    curso = Course.objects.select_related("version_activa").get(pk=course_id)
    if curso.version_activa_id is None:
        return curso, None, []

    secciones = (
        Section.objects.filter(curso_version_id=curso.version_activa_id)
        .prefetch_related("lecciones__items__recurso", "lecciones__items__actividad")
        .order_by("orden")
    )
    return curso, curso.version_activa, list(secciones)
