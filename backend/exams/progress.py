"""
Progreso académico del estudiante.

El progreso cuelga del CURSO y se indexa por el CÓDIGO LÓGICO de la lección, no
por su fila física. Es lo que hace que sobreviva a lo que exige el spec:
desinstalar, reinstalar y subir de versión.

Cómo se calcula el porcentaje del curso:

  · Se toman las lecciones de la VERSIÓN ACTIVA del curso. Si el curso no tiene
    versión activa —o su contenido ya no está instalado— se cae a las lecciones
    de las que hay progreso registrado, para que el historial siga visible.
  · Cada lección pesa igual.
  · El porcentaje de una lección es el registrado explícitamente. Si no hay
    ninguno y la lección contiene una actividad calificable, se deriva de la
    mejor nota del estudiante en esa actividad.
  · El porcentaje del curso es la media de las lecciones.

La nota del quiz NO se copia a m05_progreso_leccion: su registro autoritativo es
m10_quiz_intento.puntaje. Duplicarla sería crear dos verdades.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from .models import (
    Course,
    Lesson,
    LessonProgress,
    QuizAttempt,
    now_ms,
    sequence_value,
)


class ProgressError(Exception):
    """Datos que no permiten registrar progreso."""


def _dos(valor):
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def record_lesson_progress(
    course_id, persona_id, leccion_codigo, porcentaje, leccion_titulo=None, actor=None
):
    """
    Registra o actualiza el progreso de una lección. Upsert por
    (curso, persona, código de lección).

    El progreso NO baja por sí solo: si llega un valor menor al ya registrado se
    conserva el mayor. Reabrir una lección ya completada no debe hacerle perder
    lo alcanzado, y una tableta que reenvía un estado viejo tras reconectar
    tampoco.
    """
    try:
        curso = Course.objects.get(pk=course_id)
    except Course.DoesNotExist as exc:
        raise ProgressError(f"El curso {course_id} no existe.") from exc

    persona_id = (persona_id or "").strip()
    leccion_codigo = (leccion_codigo or "").strip()
    if not persona_id or not leccion_codigo:
        raise ProgressError("Hacen falta persona_id y leccion_codigo.")

    try:
        pct = _dos(porcentaje)
    except Exception as exc:
        raise ProgressError(f"Porcentaje inválido: {porcentaje!r}.") from exc
    if pct < 0 or pct > 100:
        raise ProgressError("El porcentaje tiene que estar entre 0 y 100.")

    ahora = now_ms()
    fila = LessonProgress.objects.filter(
        curso=curso, persona_id=persona_id, leccion_codigo=leccion_codigo
    ).first()

    if fila is None:
        fila = LessonProgress(
            curso=curso,
            persona_id=persona_id,
            leccion_codigo=leccion_codigo,
            iniciado_en=ahora,
            creado_por=actor,
            creado_en=ahora,
        )
    elif pct < fila.porcentaje:
        # Llegó un estado más viejo que el guardado. Se ignora el valor pero se
        # sella la fecha: sirve para saber que el dispositivo sigue vivo.
        fila.actualizado_en = ahora
        fila.save(update_fields=["actualizado_en"])
        return fila, False

    if leccion_titulo:
        fila.leccion_titulo = leccion_titulo[:250]
    fila.porcentaje = pct
    fila.actualizado_en = ahora
    if pct >= 100:
        fila.estado = LessonProgress.ESTADO_COMPLETADA
        fila.completado_en = fila.completado_en or ahora
        fila.porcentaje = Decimal("100.00")
    elif pct > 0:
        fila.estado = LessonProgress.ESTADO_EN_CURSO
        fila.completado_en = None
    else:
        fila.estado = LessonProgress.ESTADO_NO_INICIADA
        fila.completado_en = None
    fila.save()
    return fila, True


def _notas_por_leccion(course_id, persona_id):
    """
    Mejor nota del estudiante por código de lección, derivada de los intentos.

    Se recorre la versión activa: item -> actividad -> intentos de esta persona.
    """
    curso = Course.objects.select_related("version_activa").filter(pk=course_id).first()
    if curso is None or curso.version_activa_id is None:
        return {}

    lecciones = (
        Lesson.objects.filter(seccion__curso_version_id=curso.version_activa_id)
        .prefetch_related("items__actividad")
    )
    notas = {}
    for leccion in lecciones:
        actividades = [i.actividad for i in leccion.items.all() if i.actividad_id]
        if not actividades:
            continue
        mejor = None
        for actividad in actividades:
            intento = (
                QuizAttempt.objects.filter(
                    actividad=actividad,
                    persona_id=persona_id,
                    estado=QuizAttempt.ESTADO_FINALIZADO,
                )
                .order_by("-puntaje")
                .first()
            )
            if intento is None:
                continue
            tope = Decimal(actividad.max_score or 100)
            pct = (Decimal(intento.puntaje) / tope * 100) if tope else Decimal(0)
            pct = max(Decimal(0), min(Decimal(100), pct))
            if mejor is None or pct > mejor[0]:
                mejor = (pct, intento)
        if mejor is not None:
            notas[leccion.codigo] = {
                "porcentaje": _dos(mejor[0]),
                "puntaje": mejor[1].puntaje,
                "max_score": actividades[0].max_score,
                "intento_id": mejor[1].pk,
            }
    return notas


def course_progress(course_id, persona_id):
    """
    Detalle del progreso del estudiante en un curso.

    Funciona igual esté el contenido instalado o no: si la versión activa ya no
    tiene contenido accesible, el desglose se arma con lo que hay registrado, y
    por eso el estudiante sigue viendo su historial (§12 del spec).
    """
    curso = Course.objects.select_related("version_activa").filter(pk=course_id).first()
    if curso is None:
        raise ProgressError(f"El curso {course_id} no existe.")

    registrado = {
        p.leccion_codigo: p
        for p in LessonProgress.objects.filter(curso=curso, persona_id=persona_id)
    }
    notas = _notas_por_leccion(course_id, persona_id)

    lecciones_version = []
    if curso.version_activa_id:
        lecciones_version = list(
            Lesson.objects.filter(seccion__curso_version_id=curso.version_activa_id)
            .select_related("seccion")
            .order_by("seccion__orden", "orden")
        )

    detalle = []
    vistos = set()
    for leccion in lecciones_version:
        vistos.add(leccion.codigo)
        detalle.append(_fila_detalle(
            leccion.codigo, leccion.titulo, registrado.get(leccion.codigo),
            notas.get(leccion.codigo), leccion.seccion.titulo,
        ))

    # Lo que ya no está en la versión activa pero tiene progreso: se conserva en
    # el desglose, marcado, para no borrar historial de la vista.
    for codigo, fila in registrado.items():
        if codigo in vistos:
            continue
        detalle.append(_fila_detalle(
            codigo, fila.leccion_titulo or codigo, fila, notas.get(codigo), None,
            en_version_activa=False,
        ))

    if detalle:
        total = sum(Decimal(d["porcentaje"]) for d in detalle)
        general = _dos(total / len(detalle))
    else:
        general = _dos(0)

    return {
        "curso_id": curso.pk,
        "titulo": curso.titulo,
        "persona_id": persona_id,
        "porcentaje": float(general),
        "lecciones": len(detalle),
        "lecciones_completadas": sum(1 for d in detalle if d["porcentaje"] >= 100),
        "detalle": detalle,
    }


def _fila_detalle(codigo, titulo, fila, nota, seccion, en_version_activa=True):
    """
    El porcentaje de una lección: el registrado, o el derivado de su nota.

    Se toma el MAYOR de los dos. Si el estudiante sacó 80 en el quiz de una
    lección y además hay un 50 registrado a mano, lo que alcanzó es 80.
    """
    pct_registrado = Decimal(fila.porcentaje) if fila else Decimal(0)
    pct_nota = Decimal(nota["porcentaje"]) if nota else Decimal(0)
    pct = max(pct_registrado, pct_nota)

    return {
        "leccion_codigo": codigo,
        "titulo": titulo,
        "seccion": seccion,
        "porcentaje": float(_dos(pct)),
        "estado": (
            "completada" if pct >= 100 else ("en_curso" if pct > 0 else "no_iniciada")
        ),
        "origen": "nota" if pct_nota > pct_registrado else ("registro" if fila else "sin_datos"),
        "nota": (
            {"puntaje": float(nota["puntaje"]), "max_score": float(nota["max_score"])}
            if nota else None
        ),
        "en_version_activa": en_version_activa,
        "actualizado_en": fila.actualizado_en if fila else None,
    }


def student_courses(persona_id, host_id):
    """
    Los cursos del estudiante en ESTE host, con la forma que pide el §19 del spec:

        {course_id, name, progress, installed, available}

    Parte de la MATRÍCULA, no del catálogo: un curso desinstalado sigue
    apareciendo con su progreso y marcado como no disponible, en lugar de
    desvanecerse.
    """
    from .hosts import _mejor_fila
    from .models import CourseEnrollment, CourseHost

    inscripciones = (
        CourseEnrollment.objects.filter(persona_id=persona_id)
        .select_related("curso", "curso__version_activa")
        .order_by("curso__titulo")
    )

    presencia = {}
    for fila in CourseHost.objects.filter(host_id=(host_id or "").strip()):
        presencia.setdefault(fila.curso_id, []).append(fila)

    salida = []
    for inscripcion in inscripciones:
        host = _mejor_fila(presencia.get(inscripcion.curso_id, []))
        avance = course_progress(inscripcion.curso_id, persona_id)
        salida.append({
            "course_id": inscripcion.curso_id,
            "name": inscripcion.curso.titulo,
            "progress": round(avance["porcentaje"] / 100, 4),
            "progress_pct": avance["porcentaje"],
            "installed": bool(host and host.presente_local),
            "available": bool(host and host.disponible_estudiante),
            # Extra sobre el spec, para que la UI pueda explicar el estado.
            "enrollment": inscripcion.estado,
            "content_format": host.formato_contenido if host else None,
            "host_state": host.estado_legible if host else "no instalado",
            "retired_at": host.retirado_en if host else None,
            "lessons": avance["lecciones"],
            "lessons_completed": avance["lecciones_completadas"],
        })
    return salida


def record_quiz_completion(attempt):
    """
    Cuando un intento se cierra, la lección que contiene esa actividad queda con
    el porcentaje de la nota, si es mayor al que ya tenía.

    Se llama desde el cierre del quiz para que el progreso no dependa de que el
    cliente lo reporte aparte.
    """
    from .models import LessonItem

    if attempt.estado != QuizAttempt.ESTADO_FINALIZADO:
        return None

    item = (
        LessonItem.objects.filter(actividad_id=attempt.actividad_id)
        .select_related("leccion", "leccion__seccion__curso_version")
        .first()
    )
    if item is None:
        return None

    curso_id = item.leccion.seccion.curso_version.curso_id
    tope = Decimal(attempt.actividad.max_score or 100)
    pct = (Decimal(attempt.puntaje) / tope * 100) if tope else Decimal(0)
    pct = max(Decimal(0), min(Decimal(100), pct))

    fila, _ = record_lesson_progress(
        curso_id,
        attempt.persona_id,
        item.leccion.codigo,
        pct,
        leccion_titulo=item.leccion.titulo,
        actor="quiz",
    )
    return fila
