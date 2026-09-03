"""
Poner al día lo que el LMS cree disponible con lo que la biblioteca ofrece hoy.

El catálogo del componente cambia sin avisar: el administrador desactiva una
asignatura por política, alguien desinstala un paquete, o la biblioteca se
reinicia con menos contenido. El LMS no lo puede cachear —artículo 8— pero sí
tiene que poder CONTARLO, porque una tableta puede preguntar «¿por qué no se abre
esto?» justo cuando la biblioteca está cerrada y no hay a quién consultar.

Qué hace y qué NO hace, que es la parte importante:

    SE ACTUALIZA   la disponibilidad de cada referencia, con la fecha en que
                   desapareció y la fecha en que volvió.
    SE CIERRA      el reparto de lo que ya no está: si una tableta lo tiene en
                   pantalla, deja de ofrecérselo. Es estado de la clase en
                   curso, efímero por diseño.
    NO SE BORRA    ni la referencia, ni la matrícula, ni el progreso, ni la
                   nota, ni el examen. Nada del expediente.

Esa última línea es el criterio A-9 del spec del LMS, y es la razón de que esto
sea una reconciliación y no una limpieza.
"""

from django.db import transaction

from . import contenido as componente
from .models import AuditLog, CourseHost, RepartoActivo, UnidadMaterial, now_ms


def _refs_del_catalogo():
    """
    Las referencias que la biblioteca ofrece AHORA.

    Devuelve (refs, versiones, paquetes). Si la biblioteca no está, se lanza: reconciliar
    contra un catálogo que no se pudo leer marcaría todo como desaparecido, que
    es exactamente el error que arruinaría una clase con la biblioteca cerrada.
    """
    respuesta = componente.catalogo()
    elementos = respuesta if isinstance(respuesta, list) else (
        respuesta.get("elementos") or respuesta.get("items") or []
    )
    refs = set()
    versiones = {}
    paquetes = set()
    for elemento in elementos:
        referencia = elemento.get("ref")
        if not referencia:
            continue
        refs.add(referencia)
        versiones[referencia] = str(elemento.get("version") or "")
        if elemento.get("paquete"):
            paquetes.add(elemento["paquete"])
    return refs, versiones, paquetes


def _audit(accion, objeto_id, anterior, nuevo, actor):
    AuditLog.objects.create(
        actor_id=actor,
        accion=accion,
        objeto_tabla=UnidadMaterial._meta.db_table,
        objeto_id=objeto_id,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
    )


@transaction.atomic
def reconciliar(actor="docente-ops", host_id=None):
    """
    Compara lo guardado con el catálogo y deja constancia de las diferencias.

    Es idempotente: correrla dos veces seguidas no cambia nada la segunda vez, y
    por eso se puede colgar del botón «Actualizar» y de la apertura de una
    pantalla sin pensar en cuántas veces se dispara.
    """
    ahora = now_ms()
    refs, versiones, paquetes = _refs_del_catalogo()

    desaparecidos = []
    reaparecidos = []
    cambio_version = []

    for fila in UnidadMaterial.objects.select_related("leccion").all():
        presente = fila.elemento_ref in refs
        campos = ["disponible_ultima_revision", "revisado_en"]

        if presente and not fila.disponible_ultima_revision:
            # Volvió. Se limpia la fecha de ausencia para que no quede
            # contando un tiempo que ya terminó.
            fila.disponible_ultima_revision = True
            fila.desaparecido_en = None
            campos.append("desaparecido_en")
            reaparecidos.append(fila.elemento_ref)
            _audit("material.reaparecio", fila.pk, "ausente", "disponible", actor)

        elif not presente and fila.disponible_ultima_revision:
            fila.disponible_ultima_revision = False
            fila.desaparecido_en = ahora
            campos.append("desaparecido_en")
            desaparecidos.append(fila.elemento_ref)
            _audit("material.desaparecio", fila.pk, "disponible", "ausente", actor)

        if presente:
            actual = versiones.get(fila.elemento_ref) or ""
            if actual and actual != fila.version_elemento:
                # NO se reescribe la versión guardada. Es una decisión del
                # docente actualizar la referencia; el LMS solo lo señala.
                cambio_version.append({
                    "elemento_ref": fila.elemento_ref,
                    "version_guardada": fila.version_elemento,
                    "version_disponible": actual,
                })

        fila.revisado_en = ahora
        fila.save(update_fields=campos)

    # Las filas de presencia de los cursos que viven en la biblioteca se ponen
    # de acuerdo con el catálogo. Sin esto, reinstalar un paquete dejaba el
    # registro del LMS diciendo que el contenido no estaba, y la tableta se lo
    # creía: el cartel de «desinstalado» se quedaba pegado.
    presencia_saneada = []
    for fila in CourseHost.objects.select_related("curso").filter(
        formato_contenido=CourseHost.FORMATO_AVACOM_CONTENIDO
    ):
        if not fila.package_identifier:
            continue
        deberia_estar = fila.package_identifier in paquetes
        if sanear_presencia(fila, deberia_estar, actor=actor):
            presencia_saneada.append({
                "curso": fila.curso_id,
                "titulo": fila.curso.titulo,
                "paquete": fila.package_identifier,
                "presente": deberia_estar,
            })

    # El reparto de algo que ya no está se cierra: una tableta no debe seguir
    # con material en pantalla que el equipo ya no puede servir.
    repartos_cerrados = []
    abiertos = RepartoActivo.objects.filter(cerrado_en__isnull=True)
    if host_id:
        abiertos = abiertos.filter(host_id=host_id)
    for fila in abiertos:
        if fila.elemento_ref not in refs:
            fila.cerrado_en = ahora
            fila.save(update_fields=["cerrado_en"])
            repartos_cerrados.append(fila.elemento_ref)

    return {
        "revisado_en": ahora,
        "catalogo": len(refs),
        "referencias": UnidadMaterial.objects.count(),
        "disponibles": UnidadMaterial.objects.filter(disponible_ultima_revision=True).count(),
        "no_disponibles": UnidadMaterial.objects.filter(disponible_ultima_revision=False).count(),
        "desaparecidos": desaparecidos,
        "reaparecidos": reaparecidos,
        "cambio_version": cambio_version,
        "repartos_cerrados": repartos_cerrados,
        "presencia_saneada": presencia_saneada,
        "hubo_cambios": bool(
            desaparecidos or reaparecidos or repartos_cerrados or presencia_saneada
        ),
    }


def resumen_por_curso():
    """
    Cuánto material de la biblioteca tiene cada curso y cuánto de eso falta.

    Es lo que alimenta el panel: un curso con material ausente se puede señalar
    sin que el docente tenga que abrir sus lecciones una por una.
    """
    por_curso = {}
    filas = UnidadMaterial.objects.select_related(
        "leccion__seccion__curso_version__curso"
    ).all()
    for fila in filas:
        curso = fila.leccion.seccion.curso_version.curso
        entrada = por_curso.setdefault(curso.pk, {
            "curso": curso.pk,
            "titulo": curso.titulo,
            "materiales": 0,
            "disponibles": 0,
            "ausentes": 0,
            "ausentes_desde": None,
        })
        entrada["materiales"] += 1
        if fila.disponible_ultima_revision:
            entrada["disponibles"] += 1
        else:
            entrada["ausentes"] += 1
            if fila.desaparecido_en and (
                entrada["ausentes_desde"] is None
                or fila.desaparecido_en < entrada["ausentes_desde"]
            ):
                entrada["ausentes_desde"] = fila.desaparecido_en
    return list(por_curso.values())


def sanear_presencia(fila, presente, actor="docente-ops"):
    """
    Pone `m05_curso_host` de acuerdo con la biblioteca.

    Solo se aplica a los cursos cuyo contenido vive en la biblioteca. Para un
    curso SCORM o CMI5 esta bandera es la fuente de verdad —los archivos son del
    LMS— y tocarla aquí sería sobrescribir una decisión del docente.

    Por qué `disponible_estudiante` sigue a `presente_local` en este caso: el
    componente ya aplica la política de la escuela ANTES de responder, así que un
    elemento que aparece en el catálogo es uno que la escuela quiere ofrecer.
    Dejarlo presente pero no disponible obligaría al docente a habilitar a mano
    algo que él nunca deshabilitó.
    """
    if fila is None or fila.formato_contenido != CourseHost.FORMATO_AVACOM_CONTENIDO:
        return False
    if fila.presente_local == presente:
        return False

    anterior = f"presente={fila.presente_local} disponible={fila.disponible_estudiante}"
    fila.presente_local = presente
    fila.disponible_estudiante = presente
    # El CHECK exige fecha de retiro cuando no está presente, y no la quiere
    # cuando sí lo está.
    fila.retirado_en = None if presente else (fila.retirado_en or now_ms())
    fila.verificado_en = now_ms()
    fila.save(update_fields=[
        "presente_local", "disponible_estudiante", "retirado_en", "verificado_en"])

    AuditLog.objects.create(
        actor_id=actor,
        accion="curso.host.saneado" if presente else "curso.host.ausente",
        objeto_tabla=CourseHost._meta.db_table,
        objeto_id=fila.pk,
        valor_anterior=anterior,
        valor_nuevo=f"presente={presente} disponible={presente}",
    )
    return True
