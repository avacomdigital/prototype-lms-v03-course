"""
Presencia física de un curso en un host (una OPS).

La regla de oro que gobierna este módulo:

    DESINSTALAR CONTENIDO  ≠  BORRAR ENTIDADES ACADÉMICAS

Desinstalar apaga banderas y sella fechas. No borra el curso, ni las
inscripciones, ni las notas, ni los intentos.

Este módulo es NEUTRAL al estándar. SCORM y CMI5 son formatos de ENTRADA: cada
parser transforma su paquete al mismo árbol curso -> sección -> lección ->
lesson item. Aquí solo se registra qué formato llegó y dónde está su descriptor.
"""

from django.db import transaction

from .models import AuditLog, Course, CourseHost, CourseVersion, now_ms, sequence_value


class HostError(Exception):
    """Cualquier fallo que deba rechazar la operación sin tocar la base."""


def _audit(actor, accion, objeto_id, anterior, nuevo, resultado="ok"):
    AuditLog.objects.create(
        actor_id=actor,
        accion=accion,
        objeto_tabla="m05_curso_host",
        objeto_id=objeto_id,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        resultado=resultado,
        ocurrido_en=now_ms(),
        secuencia=sequence_value(),
    )


def _descripcion(fila):
    return (
        f"formato={fila.formato_contenido} "
        f"version={fila.curso_version_id or 'sin versión'} "
        f"presente={int(fila.presente_local)} "
        f"disponible={int(fila.disponible_estudiante)}"
    )


def _filas(host_id, course_id):
    return CourseHost.objects.filter(host_id=(host_id or "").strip(), curso_id=course_id)


def _resolver(host_id, course_id, version_id=None):
    """
    Encuentra LA fila sobre la que actuar.

    Con la clave por (host, curso, versión) puede haber varias versiones del
    mismo curso instaladas en el host. Si no se indica cuál y hay más de una, se
    rechaza en lugar de adivinar: elegir por el agente equivocado dejaría al
    estudiante viendo otra versión.
    """
    consulta = _filas(host_id, course_id)
    if version_id:
        fila = consulta.filter(curso_version_id=version_id).first()
        if fila is None:
            raise HostError(
                f"La versión {version_id} del curso {course_id} no está registrada "
                f"en el host {host_id}."
            )
        return fila

    encontradas = list(consulta)
    if not encontradas:
        raise HostError(f"El curso {course_id} no está registrado en el host {host_id}.")
    if len(encontradas) > 1:
        versiones = ", ".join(str(f.curso_version_id or "sin versión") for f in encontradas)
        raise HostError(
            f"Hay {len(encontradas)} versiones de {course_id} en el host {host_id} "
            f"({versiones}). Indica curso_version_id."
        )
    return encontradas[0]


@transaction.atomic
def register_install(
    host_id,
    course_id,
    version_id=None,
    formato_contenido=None,
    package_identifier=None,
    package_version=None,
    manifest_tipo=None,
    manifest_ref=None,
    package_ref=None,
    package_huella=None,
    disponible_estudiante=None,
    actor="docente-ops",
):
    """
    Registra —o vuelve a registrar— una versión de un curso como presente en un host.

    Es IDEMPOTENTE por (host, curso, versión): reinstalar el mismo paquete no crea
    otro registro. Instalar una versión DISTINTA sí crea una fila nueva, y así
    queda el historial de qué estuvo instalado aquí.

    `disponible_estudiante` se deja en False por omisión: recién instalado el
    paquete todavía no se validó.
    """
    host_id = (host_id or "").strip()
    if not host_id:
        raise HostError("Falta el host_id.")

    try:
        curso = Course.objects.get(pk=course_id)
    except Course.DoesNotExist as exc:
        raise HostError(f"El curso {course_id} no existe.") from exc

    version = None
    if version_id:
        try:
            version = CourseVersion.objects.get(pk=version_id)
        except CourseVersion.DoesNotExist as exc:
            raise HostError(f"La versión {version_id} no existe.") from exc
        # INVARIANTE que el ORM no puede expresar: haría falta una FK compuesta
        # (curso_version_id, curso_id). Se comprueba aquí, en el único camino que
        # asigna la versión.
        if version.curso_id != curso.pk:
            raise HostError(
                f"La versión {version_id} pertenece al curso {version.curso_id}, "
                f"no a {curso.pk}."
            )

    if formato_contenido is not None:
        validos = {clave for clave, _ in CourseHost.FORMATOS}
        if formato_contenido not in validos:
            raise HostError(
                f"Formato de contenido desconocido: {formato_contenido!r}. "
                f"Válidos: {', '.join(sorted(validos))}."
            )

    ahora = now_ms()
    fila = _filas(host_id, course_id).filter(curso_version=version).first()
    creada = fila is None
    anterior = None if creada else _descripcion(fila)

    if creada:
        fila = CourseHost(
            host_id=host_id, curso=curso, curso_version=version,
            creado_por=actor, creado_en=ahora,
        )

    if formato_contenido is not None:
        fila.formato_contenido = formato_contenido
    if package_identifier is not None:
        fila.package_identifier = package_identifier
    if package_version is not None:
        fila.package_version = package_version
    if manifest_tipo is not None:
        fila.manifest_tipo = manifest_tipo
    if manifest_ref is not None:
        fila.manifest_ref = manifest_ref
    if package_ref is not None:
        fila.package_ref = package_ref
    if package_huella is not None:
        fila.package_huella = package_huella

    fila.presente_local = True
    if disponible_estudiante is not None:
        # Solo una versión disponible por (host, curso): hay que liberar la otra
        # ANTES, porque ux_m05_ch_una_disponible es un único parcial. El orden
        # inverso falla, igual que al activar una versión del catálogo.
        if disponible_estudiante:
            _liberar_disponible(host_id, course_id, excepto=fila.pk)
        fila.disponible_estudiante = bool(disponible_estudiante)
    elif creada:
        fila.disponible_estudiante = False

    fila.instalado_en = ahora
    fila.retirado_en = None
    fila.verificado_en = ahora
    fila.save()

    _audit(
        actor,
        "curso.host.instalado" if creada else "curso.host.reinstalado",
        fila.pk,
        anterior,
        _descripcion(fila),
    )
    return fila, creada


def _liberar_disponible(host_id, course_id, excepto=None):
    """Apaga la bandera de disponibilidad de las otras versiones de este curso."""
    otras = _filas(host_id, course_id).filter(disponible_estudiante=True)
    if excepto:
        otras = otras.exclude(pk=excepto)
    for otra in otras:
        otra.disponible_estudiante = False
        otra.save(update_fields=["disponible_estudiante"])


@transaction.atomic
def retire(host_id, course_id, version_id=None, actor="docente-ops"):
    """
    Desinstala el paquete de este host. Son UPDATE, ni un solo DELETE.

    Sin `version_id` desinstala TODAS las versiones del curso presentes en el
    host, que es lo que se espera de «quitar el curso de esta OPS». Con
    `version_id` quita solo esa.

    NO se toca m05_curso.estado: el estado del curso es editorial y el mismo
    curso puede seguir habilitado y presente en otra sede.
    """
    consulta = _filas(host_id, course_id)
    if version_id:
        objetivo = consulta.filter(curso_version_id=version_id)
        if not objetivo.exists():
            raise HostError(
                f"La versión {version_id} del curso {course_id} no está registrada "
                f"en el host {host_id}."
            )
    else:
        if not consulta.exists():
            raise HostError(f"El curso {course_id} no está registrado en el host {host_id}.")
        objetivo = consulta

    ahora = now_ms()
    afectadas = []
    for fila in objetivo:
        if not fila.presente_local:
            continue
        anterior = _descripcion(fila)
        fila.presente_local = False
        fila.disponible_estudiante = False
        fila.retirado_en = ahora
        fila.save(update_fields=["presente_local", "disponible_estudiante", "retirado_en"])
        _audit(actor, "curso.host.desinstalado", fila.pk, anterior, _descripcion(fila))
        afectadas.append(fila)

    # Repetir la operación es inofensivo, que es lo que hace segura una reconexión.
    return list(objetivo), afectadas


@transaction.atomic
def set_availability(host_id, course_id, disponible, version_id=None, actor="docente-ops"):
    """
    Abre o cierra el curso a los estudiantes de este host.

    Abrirlo exige que esté presente: no se puede ofrecer contenido que no está en
    el disco. Y libera antes cualquier otra versión que estuviera ofrecida, para
    que el estudiante nunca vea el mismo curso dos veces.
    """
    fila = _resolver(host_id, course_id, version_id)
    disponible = bool(disponible)

    if disponible and not fila.presente_local:
        raise HostError(
            "No se puede habilitar un curso que no está presente en el host. "
            "Instálalo primero."
        )
    if fila.disponible_estudiante == disponible:
        return fila, False

    anterior = _descripcion(fila)
    if disponible:
        _liberar_disponible(host_id, course_id, excepto=fila.pk)
    fila.disponible_estudiante = disponible
    fila.save(update_fields=["disponible_estudiante"])
    _audit(
        actor,
        "curso.host.habilitado" if disponible else "curso.host.deshabilitado",
        fila.pk,
        anterior,
        _descripcion(fila),
    )
    return fila, True


def mark_verified(host_id, course_id, package_huella=None, version_id=None, actor="docente-ops"):
    """
    Sella la última comprobación física del paquete.

    Si se pasa una huella distinta a la registrada, la comprobación FALLA: los
    archivos del disco no son los que se instalaron. El curso se cierra a los
    estudiantes y el fallo queda auditado.

    OJO con la transacción: esta función NO lleva @transaction.atomic completo.
    En el caso de huella distinta hay que GUARDAR el cierre y AVISAR con una
    excepción; si el guardado viviera en la misma transacción que la excepción
    aborta, se revertiría justo lo que se quería conservar.
    """
    fila = _resolver(host_id, course_id, version_id)

    if package_huella and fila.package_huella and package_huella != fila.package_huella:
        anterior = _descripcion(fila)
        esperada = fila.package_huella
        with transaction.atomic():
            fila.disponible_estudiante = False
            fila.verificado_en = now_ms()
            fila.save(update_fields=["disponible_estudiante", "verificado_en"])
            _audit(
                actor, "curso.host.verificado", fila.pk, anterior,
                f"huella esperada={esperada} recibida={package_huella}",
                resultado="error",
            )
        # Fuera del atomic: el cierre ya quedó confirmado y sobrevive al aviso.
        raise HostError(
            "La huella del paquete en disco no coincide con la registrada. "
            "El curso se cerró a los estudiantes hasta reinstalarlo."
        )

    with transaction.atomic():
        fila.verificado_en = now_ms()
        if package_huella and not fila.package_huella:
            fila.package_huella = package_huella
            fila.save(update_fields=["verificado_en", "package_huella"])
        else:
            fila.save(update_fields=["verificado_en"])
        _audit(actor, "curso.host.verificado", fila.pk, None, _descripcion(fila))
    return fila


def _mejor_fila(filas):
    """
    De varias versiones del mismo curso en un host, cuál describe su estado.

    Se prefiere la que está ofrecida; si ninguna, la que esté presente; si
    ninguna, la más recientemente retirada. Así el estudiante ve el estado que
    le importa y no una versión vieja al azar.
    """
    if not filas:
        return None
    disponible = next((f for f in filas if f.disponible_estudiante), None)
    if disponible:
        return disponible
    presente = next((f for f in filas if f.presente_local), None)
    if presente:
        return presente
    return sorted(filas, key=lambda f: f.retirado_en or 0)[-1]


def courses_for_student(persona_id, host_id):
    """
    Qué ve un estudiante en ESTE host, incluido lo que ya no está.

    Parte de la MATRÍCULA y no del catálogo, para que un curso desinstalado siga
    apareciendo con su estado en lugar de desvanecerse sin explicación.
    """
    from .models import CourseEnrollment

    inscripciones = (
        CourseEnrollment.objects.filter(persona_id=persona_id)
        .select_related("curso", "curso__version_activa")
        .order_by("curso__titulo")
    )

    presencia = {}
    for fila in CourseHost.objects.filter(host_id=(host_id or "").strip()):
        presencia.setdefault(fila.curso_id, []).append(fila)

    resultado = []
    for inscripcion in inscripciones:
        host = _mejor_fila(presencia.get(inscripcion.curso_id, []))
        resultado.append({
            "curso_id": inscripcion.curso_id,
            "titulo": inscripcion.curso.titulo,
            "version": (
                inscripcion.curso.version_activa.version
                if inscripcion.curso.version_activa_id else None
            ),
            "matricula": inscripcion.estado,
            "formato_contenido": host.formato_contenido if host else None,
            "presente_local": bool(host and host.presente_local),
            "disponible_estudiante": bool(host and host.disponible_estudiante),
            "estado_host": host.estado_legible if host else "no instalado",
            "retirado_en": host.retirado_en if host else None,
            "versiones_en_host": len(presencia.get(inscripcion.curso_id, [])),
        })
    return resultado
