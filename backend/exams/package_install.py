"""
Instalación de un paquete de curso, en UNA transacción.

Réplica del flujo de install_course_version.py: mismos pasos, mismos ids
deterministas y las mismas tres propiedades no negociables.

  - Los pasos 3 y 4 RESUELVEN O CREAN, nunca sobrescriben. Si dos versiones del
    curso usan la misma versión de un material, comparten la fila física.
  - IDEMPOTENCIA: instalar el mismo paquete dos veces no duplica nada. Es lo que
    hace inofensiva una reconexión.
  - IDS DETERMINISTAS derivados de (curso, versión, orden). El mismo paquete
    instalado en dos nodos sin conexión produce los mismos ids, o la
    sincronización posterior genera duplicados.

Ante cualquier error: ROLLBACK, y el fallo queda en m19_auditoria con
resultado='error'. La versión que estuviera publicada SIGUE publicada: nunca se
activa una fotografía incompleta.
"""

import re

from django.db import transaction

from .catalog import activate_version
from .models import (
    Activity,
    AuditLog,
    Course,
    CourseVersion,
    CurriculumFramework,
    LearningResource,
    Lesson,
    LessonItem,
    Section,
    now_ms,
    sequence_value,
)

PACKAGE_SCHEMA = "avacom-course-package/v1"


class PackageError(Exception):
    """Cualquier fallo que deba provocar ROLLBACK."""


def _slug_curso(curso_id):
    """
    CURSO-MAT6 -> MAT6. Para armar ids legibles.

    Se recorta a 24 caracteres porque el slug entra en los ids de secciones,
    lecciones e items, y esos son CharField(40): 'ITEM-' + slug + '-V99-99'
    tiene que caber.
    """
    base = curso_id.split("-", 1)[1] if "-" in curso_id else curso_id
    return base[:24]


def _titulo_desde_paquete(package):
    """
    El paquete no trae título de curso; trae package_id. De
    'avacom.men.co.math6.fracciones' se saca 'Fracciones', que es un punto de
    partida razonable para que el docente lo confirme o lo corrija.
    """
    package_id = (package.get("package") or {}).get("package_id") or ""
    ultimo = package_id.split(".")[-1] if package_id else ""
    ultimo = re.sub(r"[-_]+", " ", ultimo).strip()
    return ultimo.capitalize() if ultimo else "Curso importado"


# ── PASO 1 · validar el paquete ────────────────────────────────────────────
def validate_package(package):
    """Comprueba la forma antes de tocar la base. Devuelve (course_id, version)."""
    if not isinstance(package, dict):
        raise PackageError("El archivo no contiene un objeto JSON.")

    schema = package.get("schema")
    if schema != PACKAGE_SCHEMA:
        raise PackageError(
            f"Schema no reconocido: {schema!r}. Se esperaba {PACKAGE_SCHEMA!r}."
        )

    for clave in ("package", "course", "sections"):
        if clave not in package:
            raise PackageError(f"Al paquete le falta la sección '{clave}'.")

    curso = package["course"]
    course_id = (curso.get("course_id") or "").strip()
    if not course_id:
        raise PackageError("El paquete no declara course.course_id.")
    if len(course_id) > 40:
        raise PackageError("course_id no puede pasar de 40 caracteres.")

    try:
        version = int(curso.get("version"))
    except (TypeError, ValueError):
        raise PackageError("course.version debe ser un entero.") from None
    if version < 1:
        raise PackageError("course.version debe ser 1 o mayor.")

    secciones = package.get("sections") or []
    if not secciones:
        raise PackageError("El paquete no trae ninguna sección.")

    ordenes = [s.get("orden") for s in secciones]
    if len(set(ordenes)) != len(ordenes):
        raise PackageError("Hay secciones con el mismo 'orden'.")

    for seccion in secciones:
        if not seccion.get("codigo"):
            raise PackageError("Cada sección necesita su 'codigo' (identidad lógica).")
        lecciones = seccion.get("lessons") or []
        if not lecciones:
            raise PackageError(f"La sección '{seccion['codigo']}' no trae lecciones.")
        for leccion in lecciones:
            if not leccion.get("codigo"):
                raise PackageError("Cada lección necesita su 'codigo'.")
            if not (leccion.get("items") or []):
                raise PackageError(f"La lección '{leccion['codigo']}' no trae items.")

    return course_id, version


def inspect_package(package):
    """
    Vista previa SIN escribir nada. Es lo que la OPS muestra al docente después
    de elegir el archivo y antes de confirmar la importación.
    """
    course_id, version = validate_package(package)
    secciones = package["sections"]
    lecciones = [l for s in secciones for l in (s.get("lessons") or [])]
    items = [i for l in lecciones for i in (l.get("items") or [])]

    curso = Course.objects.filter(pk=course_id).first()
    version_existente = CourseVersion.objects.filter(curso_id=course_id, version=version).first()
    meta = package.get("version_meta") or {}

    return {
        "course_id": course_id,
        "version": version,
        "package_version": (package.get("package") or {}).get("package_version"),
        "huella": meta.get("huella"),
        "notas": meta.get("notas"),
        "activate_after_install": bool(
            (package.get("publication") or {}).get("activate_after_install", False)
        ),
        "secciones": len(secciones),
        "lecciones": len(lecciones),
        "items": len(items),
        "recursos": len(package.get("resources") or []),
        "actividades": len(package.get("activities") or []),
        "curso_existe": curso is not None,
        "curso_titulo": curso.titulo if curso else None,
        "titulo_sugerido": curso.titulo if curso else _titulo_desde_paquete(package),
        "version_ya_instalada": version_existente is not None,
        "misma_huella": bool(
            version_existente and version_existente.huella == (meta.get("huella") or "")
        ),
    }


# ── PASOS 3 y 4 · resolver o crear ─────────────────────────────────────────
def _registrar_recursos(package):
    """
    La identidad de un material es (content_ref, content_version). Si ya existe
    se REUTILIZA la fila física; nunca se sobrescribe, porque versiones
    anteriores del curso dependen de ella.
    """
    resueltos = {}
    creados = 0
    for r in package.get("resources") or []:
        llave = (r["content_ref"], str(r["content_version"]))
        fila = LearningResource.objects.filter(
            content_ref=llave[0], content_version=llave[1]
        ).first()
        if fila is not None:
            resueltos[llave] = fila.pk
            continue
        # El id físico viaja en el paquete para que todos los nodos offline
        # resuelvan el mismo registro. Si no viene, se deja el default del
        # modelo: pasar id=None intentaría insertar NULL.
        campos = {"id": r["id"]} if r.get("id") else {}
        fila = LearningResource.objects.create(
            **campos,
            titulo=r["titulo"],
            content_type=r["content_type"],
            content_ref=llave[0],
            content_version=llave[1],
            content_huella=r.get("content_huella"),
            duracion_seg=r.get("duracion_seg"),
            autor_id=r.get("autor_id"),
            creado_por=r.get("autor_id"),
        )
        resueltos[llave] = fila.pk
        creados += 1
    return resueltos, creados


def _registrar_actividades(package):
    """Mismo criterio, con (activity_ref, version)."""
    resueltos = {}
    creadas = 0
    for a in package.get("activities") or []:
        llave = (a["activity_ref"], int(a["version"]))
        fila = Activity.objects.filter(activity_ref=llave[0], version=llave[1]).first()
        if fila is not None:
            resueltos[llave] = fila.pk
            continue
        campos = {"id": a["id"]} if a.get("id") else {}
        fila = Activity.objects.create(
            **campos,
            activity_ref=llave[0],
            version=llave[1],
            titulo=a["titulo"],
            descripcion=a.get("descripcion"),
            activity_type=a["activity_type"],
            submission_type=a["submission_type"],
            grading_type=a["grading_type"],
            max_score=a.get("max_score", 100),
            autor_id=a.get("autor_id"),
            creado_por=a.get("autor_id"),
        )
        resueltos[llave] = fila.pk
        creadas += 1
    return resueltos, creadas


# ── PASOS 5, 6 y 7 · el árbol de la versión ────────────────────────────────
def _crear_arbol(package, version_row, recursos, actividades):
    """
    Los ids se derivan de (versión, orden), no de un contador global: el mismo
    paquete en dos tabletas sin conexión produce exactamente los mismos ids.
    """
    v = version_row.version
    # El slug del curso TIENE que entrar en el id. Sin él, dos cursos distintos
    # instalados ambos como versión 1 generan el mismo 'SEC-V1-01' y la
    # segunda importación muere con UNIQUE constraint failed.
    slug = _slug_curso(version_row.curso_id)
    autor = (package.get("version_meta") or {}).get("instalada_por")
    ts = now_ms()
    n_sec = n_lec = n_item = 0

    for seccion in sorted(package["sections"], key=lambda s: s["orden"]):
        n_sec += 1
        sec = Section.objects.create(
            id=f"SEC-{slug}-V{v}-{seccion['orden']:02d}",
            curso_version=version_row,
            codigo=seccion["codigo"],
            titulo=seccion["titulo"],
            orden=seccion["orden"],
            creado_en=ts,
            creado_por=autor,
        )

        for leccion in sorted(seccion.get("lessons") or [], key=lambda l: l["orden"]):
            n_lec += 1
            lec = Lesson.objects.create(
                id=f"LEC-{slug}-V{v}-{n_lec:02d}",
                seccion=sec,
                codigo=leccion["codigo"],
                titulo=leccion["titulo"],
                descripcion=leccion.get("descripcion"),
                competency_framework=leccion.get("competency_framework"),
                learning_outcome=leccion.get("learning_outcome"),
                skills=leccion.get("skills"),
                attitudes_values=leccion.get("attitudes_values"),
                orden=leccion["orden"],
                estado=leccion.get("estado", "publicado"),
                creado_en=ts,
                creado_por=autor,
            )

            for item in sorted(leccion.get("items") or [], key=lambda i: i["orden"]):
                n_item += 1
                tipo = item["tipo"]
                act_id = rec_id = elem_ref = elem_ver = None

                if tipo == "contenido":
                    llave = (item["content_ref"], str(item["content_version"]))
                    if llave not in recursos:
                        raise PackageError(
                            f"El item {item['orden']} de la lección {leccion['codigo']} pide "
                            f"el recurso {llave[0]} v{llave[1]}, pero el paquete no lo declara "
                            "en 'resources'."
                        )
                    rec_id = recursos[llave]
                elif tipo == "actividad":
                    llave = (item["activity_ref"], int(item["activity_version"]))
                    if llave not in actividades:
                        raise PackageError(
                            f"El item {item['orden']} de la lección {leccion['codigo']} pide "
                            f"la actividad {llave[0]} v{llave[1]}, pero el paquete no la "
                            "declara en 'activities'."
                        )
                    act_id = actividades[llave]
                elif tipo == "referencia_externa":
                    elem_ref = item.get("elemento_ref")
                    elem_ver = item.get("elemento_version")
                    if not elem_ref:
                        raise PackageError(
                            f"El item {item['orden']} es una referencia externa sin elemento_ref."
                        )
                else:
                    raise PackageError(f"Tipo de item desconocido: {tipo!r}.")

                LessonItem.objects.create(
                    id=f"ITEM-{slug}-V{v}-{n_item:02d}",
                    leccion=lec,
                    orden=item["orden"],
                    tipo=tipo,
                    actividad_id=act_id,
                    recurso_id=rec_id,
                    elemento_ref=elem_ref,
                    elemento_version=elem_ver,
                    creado_en=ts,
                    creado_por=autor,
                )

    return n_sec, n_lec, n_item


# ── PASO 8 · la red de seguridad antes de publicar ─────────────────────────
def _validar_referencias(version_row):
    huerfanos = LessonItem.objects.filter(
        leccion__seccion__curso_version=version_row
    ).filter(
        models_orphan_filter()
    ).count()
    if huerfanos:
        raise PackageError(f"{huerfanos} item(s) de la versión apuntan a algo que no existe.")

    vacias = (
        Lesson.objects.filter(seccion__curso_version=version_row)
        .filter(items__isnull=True)
        .count()
    )
    if vacias:
        raise PackageError(f"{vacias} lección(es) quedaron sin ningún item.")


def models_orphan_filter():
    from django.db.models import Q

    return (
        Q(tipo="contenido", recurso__isnull=True)
        | Q(tipo="actividad", actividad__isnull=True)
        | Q(tipo="referencia_externa", elemento_ref__isnull=True)
    )


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


def install_package(
    package,
    titulo=None,
    curriculum_framework=None,
    docente_id=None,
    actor=None,
    activate=None,
):
    """
    Instala el paquete y devuelve un resumen de lo que pasó.

    `titulo`, `curriculum_framework` y `docente_id` solo se usan si el curso NO
    existe todavía: el paquete declara su course_id pero no su título ni su marco
    curricular, así que esos los aporta quien importa.
    """
    course_id, version = validate_package(package)
    meta = package.get("version_meta") or {}
    actor = actor or meta.get("instalada_por") or "docente-ops"
    huella = meta.get("huella") or ""
    if activate is None:
        activate = bool((package.get("publication") or {}).get("activate_after_install", False))

    try:
        with transaction.atomic():
            # ── PASO 1 · el curso: resolver o crear ──────────────────────
            curso = Course.objects.filter(pk=course_id).first()
            curso_creado = False
            if curso is None:
                marco_clave = curriculum_framework or _marco_por_omision()
                marco = CurriculumFramework.objects.filter(pk=marco_clave).first()
                if marco is None:
                    raise PackageError(
                        f"El marco curricular '{marco_clave}' no existe. "
                        "Elige uno de los que ofrece la API."
                    )
                curso = Course.objects.create(
                    id=course_id,
                    titulo=(titulo or _titulo_desde_paquete(package)).strip()[:250],
                    descripcion=meta.get("notas"),
                    docente_id=docente_id or actor,
                    curriculum_framework=marco,
                    estado=Course.ESTADO_BORRADOR,
                    creado_por=actor,
                )
                curso_creado = True

            # ── IDEMPOTENCIA ─────────────────────────────────────────────
            existente = CourseVersion.objects.filter(curso=curso, version=version).first()
            if existente is not None:
                if existente.huella == huella:
                    # El mismo paquete otra vez. No se duplica nada; si venía con
                    # activate y no está publicada, se publica y listo.
                    activada = False
                    if activate and existente.estado != CourseVersion.ESTADO_ACTIVA:
                        activate_version(existente.pk, actor=actor)
                        activada = True
                    return _resumen(
                        curso, existente, 0, 0, 0, 0, 0,
                        curso_creado=False, idempotente=True, activada=activada,
                    )
                raise PackageError(
                    f"La versión {version} del curso {course_id} ya está instalada con otra "
                    f"huella. Instalar encima destruiría una fotografía existente: usa un "
                    f"número de versión nuevo."
                )

            # ── PASO 2 · la fila cabecera, en 'staged' ───────────────────
            ts = now_ms()
            version_row = CourseVersion.objects.create(
                id=f"CV-{_slug_curso(course_id)}-V{version}",
                curso=curso,
                version=version,
                package_version=(package.get("package") or {}).get("package_version"),
                estado=CourseVersion.ESTADO_STAGED,
                instalada_en=ts,
                instalada_por=actor,
                huella=huella,
                notas=meta.get("notas"),
                creado_en=ts,
                creado_por=actor,
            )

            # ── PASOS 3 y 4 · resolver o crear, nunca sobrescribir ───────
            recursos, recursos_nuevos = _registrar_recursos(package)
            actividades, actividades_nuevas = _registrar_actividades(package)

            # ── PASOS 5, 6 y 7 · el árbol ────────────────────────────────
            n_sec, n_lec, n_item = _crear_arbol(package, version_row, recursos, actividades)

            # ── PASO 8 · validar antes de publicar ───────────────────────
            _validar_referencias(version_row)

            # ── PASO 9 · instalada ──────────────────────────────────────
            version_row.estado = CourseVersion.ESTADO_INSTALADA
            version_row.save(update_fields=["estado"])

            # ── PASO 11 · auditar ───────────────────────────────────────
            _audit(
                actor, "curso.version.instalada", "m05_curso_version", version_row.pk,
                None, f"version={version} pkg={version_row.package_version} estado=instalada",
            )

            # ── PASO 10 · activar si corresponde ────────────────────────
            activada = False
            if activate:
                activate_version(version_row.pk, actor=actor)
                version_row.refresh_from_db()
                activada = True

            return _resumen(
                curso, version_row, n_sec, n_lec, n_item,
                recursos_nuevos, actividades_nuevas,
                curso_creado=curso_creado, idempotente=False, activada=activada,
            )

    except Exception as exc:
        # El ROLLBACK ya ocurrió al salir del atomic. La traza del fallo se
        # escribe FUERA de esa transacción, o se iría con ella.
        _audit(
            actor, "curso.version.instalada", "m05_curso_version",
            f"{course_id}#v{version}", None, str(exc)[:500], resultado="error",
        )
        if isinstance(exc, PackageError):
            raise
        raise PackageError(f"La instalación falló y se revirtió: {exc}") from exc


def _marco_por_omision():
    primero = CurriculumFramework.objects.filter(activo=True).order_by("orden").first()
    return primero.pk if primero else "OTRO"


def _resumen(curso, version_row, n_sec, n_lec, n_item, recursos_nuevos, actividades_nuevas,
             curso_creado, idempotente, activada):
    from .catalog import version_counts

    curso.refresh_from_db()
    conteos = version_counts(version_row)
    return {
        "course_id": curso.pk,
        "curso_titulo": curso.titulo,
        "curso_estado": curso.estado,
        "curso_creado": curso_creado,
        "version_id": version_row.pk,
        "version": version_row.version,
        "version_estado": version_row.estado,
        "package_version": version_row.package_version,
        "idempotente": idempotente,
        "activada": activada,
        "version_activa_id": curso.version_activa_id,
        "creados": {
            "secciones": n_sec,
            "lecciones": n_lec,
            "items": n_item,
            "recursos": recursos_nuevos,
            "actividades": actividades_nuevas,
        },
        "totales_version": conteos,
    }
