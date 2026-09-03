"""
La cara del LMS hacia AVACOM-Contenido.

Todo lo de aquí pasa por exams.contenido, que es el único que habla con el
componente. Estas vistas no abren sockets: traducen entre lo que el componente
publica y lo que el OPS Master y las tabletas necesitan.

Dos cosas que conviene tener presentes al leer:

  · El título NUNCA se guarda. Cuando una pantalla muestra «Lámina del bosque»,
    ese texto se acaba de pedir al componente. Lo que el LMS guarda es
    `elemento_ref` y `version_elemento`, y nada más.

  · Por eso desinstalar contenido no rompe nada. La fila de m05_unidad_material
    sigue donde estaba; lo que cambia es que `disponible` pasa a false y la
    pantalla lo dice. Las notas, los intentos y el curso ni se enteran.
"""

from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import contenido as componente
from .models import (
    Activity,
    Course,
    CourseHost,
    ExamenPregunta,
    Lesson,
    RepartoActivo,
    UnidadMaterial,
    now_ms,
)


# ── Utilidades compartidas ───────────────────────────────────────────────────
def _lista(respuesta, *claves):
    """
    El componente devuelve a veces una lista y a veces un objeto que la envuelve.
    Se normaliza aquí para que ninguna vista tenga que adivinarlo.
    """
    if isinstance(respuesta, list):
        return respuesta
    if isinstance(respuesta, dict):
        for clave in claves:
            if isinstance(respuesta.get(clave), list):
                return respuesta[clave]
        for valor in respuesta.values():
            if isinstance(valor, list):
                return valor
    return []


def _indice_del_catalogo():
    """
    Lo que el componente ofrece AHORA, indexado por referencia.

    Se pide entero y en cada llamada. Es deliberado: cachearlo haría que el LMS
    ofreciera material que la escuela acaba de desactivar, que es justo lo que el
    artículo 8 de su constitución existe para evitar. Son diez elementos en un
    equipo local; el coste no es el problema que hay que optimizar.
    """
    return {e["ref"]: e for e in _lista(componente.catalogo(), "elementos", "items")}


def _resolver(referencias):
    """
    Da, para cada referencia guardada, lo que el componente sabe de ella hoy.

    Cuando el componente no está, o la referencia ya no está instalada, devuelve
    `disponible: False` y el LMS lo muestra atenuado. Nunca lanza: una lección no
    puede dejar de dibujarse porque la biblioteca esté cerrada.
    """
    try:
        vivo = _indice_del_catalogo()
        hay_componente = True
        motivo = ""
    except componente.ContenidoNoDisponible as exc:
        vivo, hay_componente, motivo = {}, False, str(exc)
    except componente.ContenidoError as exc:
        vivo, hay_componente, motivo = {}, False, str(exc)

    resuelto = {}
    for referencia in referencias:
        actual = vivo.get(referencia)
        resuelto[referencia] = {
            "disponible": actual is not None,
            # El título viaja, no se guarda. Si no hay componente, no hay título:
            # inventar uno sería empezar a mantener un catálogo paralelo.
            "titulo": (actual or {}).get("titulo"),
            "tipo": (actual or {}).get("tipo"),
            "version_actual": (actual or {}).get("version"),
            "duracion_seg": (actual or {}).get("duracion_seg"),
            "paquete": (actual or {}).get("paquete"),
            "motivo": (
                ""
                if actual is not None
                else (motivo or "Este material no está instalado en este equipo ahora mismo.")
            ),
        }
    return resuelto, hay_componente, motivo


def _material_json(fila, resuelto):
    vivo = resuelto.get(fila.elemento_ref, {})
    return {
        "id": fila.id,
        "leccion": fila.leccion_id,
        "elemento_ref": fila.elemento_ref,
        "version_elemento": fila.version_elemento,
        "taxonomia_ref": fila.taxonomia_ref,
        "tipo": fila.tipo,
        "orden": fila.orden,
        "creado_en": fila.creado_en,
        # Lo de abajo NO está en la tabla: se acaba de preguntar.
        "disponible": vivo.get("disponible", False),
        "titulo": vivo.get("titulo"),
        "version_actual": vivo.get("version_actual"),
        "duracion_seg": vivo.get("duracion_seg"),
        "paquete": vivo.get("paquete"),
        "motivo": vivo.get("motivo", ""),
        # La última revisión: sirve para poder decir «desde cuándo» y para poder
        # contestarle a una tableta cuando la biblioteca esté cerrada.
        "disponible_ultima_revision": fila.disponible_ultima_revision,
        "revisado_en": fila.revisado_en,
        "desaparecido_en": fila.desaparecido_en,
        # Que la versión referenciada ya no sea la instalada es información, no
        # un error: el docente decide si actualiza la referencia o la deja.
        "version_cambio": bool(
            vivo.get("version_actual")
            and vivo["version_actual"] != fila.version_elemento
        ),
    }


def _sin_componente(motivo):
    return Response(
        {
            "disponible": False,
            "detail": motivo,
            "sugerencia": "Abre AVACOM-Contenido en este equipo y vuelve a intentarlo.",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# ── Estado y catálogo ────────────────────────────────────────────────────────
class ContenidoEstadoView(APIView):
    """
    GET /api/contenido/estado/

    Lo primero que consulta cualquier pantalla antes de ofrecer nada del
    componente. Nunca falla: si la biblioteca no está, dice que no está y por
    qué. Es el artículo 9 —sin contenido el LMS sigue funcionando— hecho ruta.
    """

    def get(self, _request):
        return Response(componente.estado())


class ContenidoReconciliarView(APIView):
    """
    GET  /api/contenido/reconciliar/  · qué diría una reconciliación, sin escribir
    POST /api/contenido/reconciliar/  · ponerlo al día y dejar constancia

    Es lo que el panel llama al abrir «Resumen» y al pulsar «Actualizar». Pone la
    disponibilidad guardada de acuerdo con el catálogo de hoy, cierra el reparto
    de lo que ya no está, y NO borra nada del expediente académico.

    Si la biblioteca no responde, devuelve 503 y no escribe: reconciliar contra
    un catálogo que no se pudo leer marcaría todo como desaparecido, que es el
    error que arruinaría una clase con la biblioteca cerrada.
    """

    def get(self, _request):
        from .reconciliacion import resumen_por_curso

        estado_actual = componente.estado()
        return Response({
            "componente": estado_actual,
            "por_curso": resumen_por_curso(),
        })

    def post(self, request):
        from .reconciliacion import reconciliar, resumen_por_curso

        try:
            resultado = reconciliar(
                actor=request.data.get("actor") or "docente-ops",
                host_id=(request.data.get("host_id") or "").strip() or None,
            )
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        resultado["por_curso"] = resumen_por_curso()
        resultado["mensaje"] = _mensaje_de_reconciliacion(resultado)
        return Response(resultado)


def _mensaje_de_reconciliacion(resultado):
    """Una frase para el docente. «3 cambios» no dice nada; esto sí."""
    if not resultado["hubo_cambios"]:
        return (
            f"Todo al día: {resultado['disponibles']} de {resultado['referencias']} "
            f"materiales disponibles."
        )
    partes = []
    if resultado["desaparecidos"]:
        cuantos = len(resultado["desaparecidos"])
        partes.append(
            f"{cuantos} material(es) ya no están en el equipo y quedaron marcados "
            f"como no disponibles"
        )
    if resultado["reaparecidos"]:
        partes.append(f"{len(resultado['reaparecidos'])} volvieron a estar disponibles")
    for entrada in resultado.get("presencia_saneada", []):
        partes.append(
            f"«{entrada['titulo']}» volvió a tener contenido"
            if entrada["presente"]
            else f"«{entrada['titulo']}» se quedó sin contenido en el equipo"
        )
    if resultado["repartos_cerrados"]:
        partes.append(
            f"{len(resultado['repartos_cerrados'])} se retiraron de las tabletas "
            f"porque el equipo ya no los sirve"
        )
    return (". ".join(p.capitalize() if i == 0 else p for i, p in enumerate(partes))
            + ". Las notas y el progreso no se tocaron.")


class ContenidoCatalogoView(APIView):
    """
    GET /api/contenido/catalogo/[?nivel=&grado=&asignatura=&tipo=]

    Pasarela al catálogo del componente. Sin caché y sin guardar nada: lo que se
    ve es lo que hay en el equipo en este instante, con la política de la escuela
    ya aplicada por el propio componente.
    """

    def get(self, request):
        filtros = {
            clave: request.query_params.get(clave)
            for clave in ("nivel", "grado", "asignatura", "tipo", "idioma")
        }
        try:
            elementos = _lista(componente.catalogo(**filtros), "elementos", "items")
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"count": len(elementos), "elementos": elementos})


class ContenidoTaxonomiaView(APIView):
    """
    GET /api/contenido/taxonomia/[?padre=]

    La estructura curricular la define el CONTENIDO, no el LMS, y su profundidad
    varía: preescolar de Colombia tiene cuatro niveles y no tiene asignatura. Por
    eso se navega por `padre` en vez de asumir una forma.
    """

    def get(self, request):
        try:
            nodos = _lista(
                componente.taxonomia(request.query_params.get("padre")), "nodos", "items"
            )
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"count": len(nodos), "nodos": nodos})


class ContenidoElementoView(APIView):
    """GET /api/contenido/elemento/{ref}/ · un elemento suelto, con su política aplicada."""

    def get(self, _request, referencia):
        try:
            return Response(componente.elemento(referencia))
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            codigo = exc.estado if exc.estado in (403, 404) else status.HTTP_502_BAD_GATEWAY
            return Response({"detail": str(exc)}, status=codigo)


class ContenidoMostrarView(APIView):
    """
    POST /api/contenido/mostrar/ · proyecta un material en la pantalla del aula.

    Lo abre el componente en su propia ventana: el LMS pide, no muestra. Es la
    frontera del artículo 4 —el LMS no lee su base ni dibuja su contenido—.
    """

    def post(self, request):
        referencia = (request.data.get("elemento_ref") or "").strip()
        if not referencia:
            return Response({"detail": "Indica elemento_ref."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(componente.mostrar(referencia, request.data.get("persona_id")))
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            codigo = exc.estado if exc.estado in (403, 404) else status.HTTP_502_BAD_GATEWAY
            return Response({"detail": str(exc)}, status=codigo)


# ── Material de una lección ──────────────────────────────────────────────────
class CursoContenidoView(APIView):
    """
    GET /api/courses/{id}/contenido/

    Si el contenido de este curso sigue en el equipo, y por qué no si no está.
    Es lo que dibuja la subsección «Contenido del curso» del panel, y lo que
    decide si la estructura se muestra o se sustituye por un aviso.

    El veredicto sale de TRES fuentes, y hacen falta las tres porque un curso
    puede haber llegado por caminos distintos:

      1. `m05_curso_host.presente_local` — lo desinstalaron desde esta OPS con
         la pantalla «Eliminar curso».
      2. El PAQUETE de origen, cuando el curso vino de AVACOM-Contenido: si
         `/v1/catalogo` ya no ofrece nada de ese `package_identifier`, su
         contenido salió del equipo aunque el curso siga aquí.
      3. Las referencias colgadas en las lecciones: si están todas ausentes, no
         hay nada que abrir.

    Y una distinción que importa: un curso SCORM o CMI5 NO depende de la
    biblioteca. Su contenido se copió al LMS al importarlo y su presencia la
    gobierna `presente_local`. Juzgarlo contra `/v1/catalogo` lo marcaría como
    retirado sin serlo, porque su paquete nunca estuvo en ese catálogo.
    """

    def get(self, request, course_id):
        curso = get_object_or_404(Course, pk=course_id)
        # Sanear escribe, y un GET no debe mutar por defecto. El panel lo pide
        # con ?sanear=1 porque le conviene arreglarlo al pasar; una tableta NO
        # lo pide, y así una tableta nunca puede tocar las banderas de presencia
        # aunque conozca la ruta.
        sanear = str(request.query_params.get("sanear") or "").lower() in ("1", "true", "si", "sí")

        # ── Lo que la biblioteca ofrece ahora ────────────────────────────────
        try:
            elementos = _lista(componente.catalogo(), "elementos", "items")
            hay_componente, motivo_componente = True, ""
        except (componente.ContenidoNoDisponible, componente.ContenidoError) as exc:
            elementos, hay_componente, motivo_componente = [], False, str(exc)

        refs_vivas = {e["ref"] for e in elementos if e.get("ref")}
        paquetes_vivos = {e["paquete"] for e in elementos if e.get("paquete")}

        # ── De dónde vino este curso ─────────────────────────────────────────
        fila = (
            CourseHost.objects.filter(curso=curso)
            .order_by("-presente_local", "-instalado_en")
            .first()
        )
        depende_de_biblioteca = (
            fila is not None and fila.formato_contenido == CourseHost.FORMATO_AVACOM_CONTENIDO
        )
        paquete = fila.package_identifier if fila else None
        # Sin componente no se puede afirmar que el paquete no está: solo que no
        # se pudo comprobar. Marcarlo como ausente sería el mismo error que
        # reconciliar a ciegas.
        paquete_presente = (
            None if (not hay_componente or not depende_de_biblioteca or not paquete)
            else paquete in paquetes_vivos
        )

        # ── Las referencias colgadas de sus lecciones ────────────────────────
        materiales = list(
            UnidadMaterial.objects.filter(
                leccion__seccion__curso_version__curso=curso
            ).select_related("leccion")
        )
        resuelto, _, _ = _resolver([m.elemento_ref for m in materiales])
        disponibles = sum(1 for m in materiales if resuelto[m.elemento_ref]["disponible"])

        # ── El veredicto ─────────────────────────────────────────────────────
        # El orden importa, y esta es la regla: cuando el contenido de un curso
        # vive en la BIBLIOTECA, el catálogo manda sobre lo que el LMS tenga
        # guardado. `presente_local` es una bandera del LMS que cachea un hecho
        # que no le pertenece; si el paquete volvió y esa bandera sigue en false,
        # la que se equivoca es la bandera. Consultarla primero era lo que dejaba
        # el cartel de «desinstalado» pegado tras reinstalar.
        retirado = False
        motivo = ""
        registro_desfasado = False

        if depende_de_biblioteca and paquete_presente is False:
            retirado = True
            motivo = (
                f"La biblioteca del aula ya no ofrece el paquete «{paquete}». El "
                f"contenido de este curso fue desinstalado o lo deshabilitó la "
                f"política de la escuela."
            )
        elif depende_de_biblioteca and paquete_presente is True:
            # Está en el catálogo: hay contenido que abrir, punto.
            retirado = False
            if fila is not None and not fila.presente_local:
                registro_desfasado = True
                motivo = (
                    "El paquete volvió a la biblioteca del aula. El registro del "
                    "LMS decía lo contrario y se saneó al revisar."
                )
        elif fila is not None and not fila.presente_local:
            # Contenido que el LMS copió al importarlo (SCORM, CMI5, .json): su
            # presencia sí la gobierna esta bandera, porque los archivos son suyos.
            retirado = True
            motivo = (
                "El contenido de este curso se desinstaló de esta OPS. Los "
                "estudiantes, el progreso y las calificaciones se conservaron."
            )
        elif materiales and disponibles == 0:
            retirado = True
            motivo = (
                "Ninguno de los materiales de este curso está disponible en el "
                "equipo ahora mismo."
            )
        elif not hay_componente and depende_de_biblioteca:
            motivo = (
                f"No se pudo comprobar el contenido: {motivo_componente} Se muestra "
                f"lo último que se sabía."
            )

        # Se sanea aquí mismo para que la siguiente pantalla —y la tableta— no
        # tengan que esperar a que alguien pulse «Actualizar».
        if registro_desfasado and sanear:
            from .reconciliacion import sanear_presencia

            sanear_presencia(fila, presente=True, actor="panel")

        # ── Qué elementos del paquete siguen vivos ───────────────────────────
        # Sirve para que la subsección liste el contenido real del curso y no
        # solo las referencias que alguien colgó a mano.
        del_paquete = [e for e in elementos if e.get("paquete") == paquete] if paquete else []

        return Response({
            "curso": curso.pk,
            "titulo": curso.titulo,
            "componente_disponible": hay_componente,
            "motivo_componente": motivo_componente,
            "origen": {
                "formato_contenido": fila.formato_contenido if fila else None,
                "formato_legible": fila.get_formato_contenido_display() if fila else None,
                "package_identifier": paquete,
                "depende_de_biblioteca": depende_de_biblioteca,
                "paquete_presente": paquete_presente,
                "presente_local": fila.presente_local if fila else None,
                "retirado_en": fila.retirado_en if fila else None,
            },
            "contenido_retirado": retirado,
            "motivo": motivo,
            # Si el registro del LMS no coincide con la biblioteca. El panel lo
            # arregla pidiendo ?sanear=1; una tableta solo lo informa.
            "registro_desfasado": registro_desfasado,
            "registro_saneado": registro_desfasado and sanear,
            # La estructura se esconde cuando no hay nada que abrir: enseñar
            # secciones y lecciones cuyo material no existe promete algo que la
            # tableta no puede cumplir.
            "estructura_visible": not retirado,
            "elementos": [{
                "ref": e.get("ref"),
                "tipo": e.get("tipo"),
                "titulo": e.get("titulo"),
                "nivel": e.get("nivel"),
                "grado": e.get("grado"),
                "asignatura": e.get("asignatura"),
                "duracion_seg": e.get("duracion_seg"),
                "disponible": True,
            } for e in del_paquete],
            "materiales": [_material_json(m, resuelto) for m in materiales],
            "conteos": {
                "elementos_del_paquete": len(del_paquete),
                "materiales": len(materiales),
                "materiales_disponibles": disponibles,
                "materiales_ausentes": len(materiales) - disponibles,
            },
        })


class LeccionMaterialView(APIView):
    """
    GET  /api/lecciones/{id}/materiales/  · qué material del componente cuelga aquí
    POST /api/lecciones/{id}/materiales/  · colgar uno más

    El GET resuelve cada referencia contra el componente EN VIVO. Por eso una
    lección se sigue dibujando entera con la biblioteca cerrada: se ven las
    referencias, marcadas como no disponibles, en vez de desaparecer sin
    explicación.
    """

    def get(self, _request, leccion_id):
        leccion = get_object_or_404(Lesson, pk=leccion_id)
        filas = list(leccion.materiales.all())
        resuelto, hay_componente, motivo = _resolver([f.elemento_ref for f in filas])
        return Response({
            "leccion": leccion.id,
            "componente_disponible": hay_componente,
            "motivo": motivo,
            "count": len(filas),
            "disponibles": sum(1 for f in filas if resuelto[f.elemento_ref]["disponible"]),
            "materiales": [_material_json(f, resuelto) for f in filas],
        })

    def post(self, request, leccion_id):
        leccion = get_object_or_404(Lesson, pk=leccion_id)
        referencia = (request.data.get("elemento_ref") or "").strip()
        if not referencia:
            return Response({"detail": "Indica elemento_ref."}, status=status.HTTP_400_BAD_REQUEST)

        # La versión y el tipo se toman del componente, no de quien llama: son
        # datos del paquete y quien los conoce es el manifiesto.
        try:
            actual = componente.elemento(referencia)
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            codigo = exc.estado if exc.estado in (403, 404) else status.HTTP_502_BAD_GATEWAY
            return Response(
                {"detail": f"No se puede colgar material que el equipo no ofrece. {exc}"},
                status=codigo,
            )

        version = str(actual.get("version") or "1")
        if UnidadMaterial.objects.filter(
            leccion=leccion, elemento_ref=referencia, version_elemento=version
        ).exists():
            return Response(
                {"detail": "Ese material ya está en esta lección."},
                status=status.HTTP_409_CONFLICT,
            )

        ultimo = leccion.materiales.order_by("-orden").first()
        fila = UnidadMaterial.objects.create(
            leccion=leccion,
            elemento_ref=referencia,
            version_elemento=version,
            taxonomia_ref=actual.get("taxonomia_ref"),
            tipo=actual.get("tipo"),
            orden=(ultimo.orden + 1) if ultimo else 1,
            creado_por=request.data.get("actor") or "docente-ops",
        )
        resuelto, _, _ = _resolver([referencia])
        return Response(_material_json(fila, resuelto), status=status.HTTP_201_CREATED)


class MaterialDetailView(APIView):
    """
    DELETE /api/materiales/{id}/ · quita la referencia de la lección.

    Quitar la referencia NO desinstala nada en el componente: el LMS no instala
    ni desinstala contenido, y tampoco se lo pide. Es el artículo 11.
    """

    def delete(self, _request, pk):
        fila = get_object_or_404(UnidadMaterial, pk=pk)
        leccion_id = fila.leccion_id
        fila.delete()
        return Response({
            "leccion": leccion_id,
            "message": (
                "El material se quitó de la lección. El paquete sigue instalado en "
                "el equipo: el LMS no instala ni desinstala contenido."
            ),
        })


# ── Reparto a la clase ───────────────────────────────────────────────────────
class RepartoView(APIView):
    """
    GET  /api/contenido/reparto/?host_id=  · qué está repartido ahora
    POST /api/contenido/reparto/           · repartir un material a la clase

    Es lo que decide qué puede abrir una tableta en este momento. Las tabletas no
    alcanzan al componente ni directa ni indirectamente: piden al backend, y el
    backend decide si están autorizadas.
    """

    def get(self, request):
        host_id = (request.query_params.get("host_id") or "").strip()
        filas = RepartoActivo.objects.filter(cerrado_en__isnull=True)
        if host_id:
            filas = filas.filter(host_id=host_id)
        filas = list(filas)
        resuelto, hay_componente, motivo = _resolver([f.elemento_ref for f in filas])
        return Response({
            "componente_disponible": hay_componente,
            "motivo": motivo,
            "count": len(filas),
            "repartos": [{
                "id": f.id,
                "host_id": f.host_id,
                "sesion_clase_id": f.sesion_clase_id,
                "curso": f.curso_id,
                "grupo_id": f.grupo_id,
                "elemento_ref": f.elemento_ref,
                "version_elemento": f.version_elemento,
                "tipo": f.tipo,
                "abierto_en": f.abierto_en,
                "abierto_por": f.abierto_por,
                **{k: resuelto[f.elemento_ref][k] for k in ("disponible", "titulo", "motivo")},
            } for f in filas],
        })

    def post(self, request):
        host_id = (request.data.get("host_id") or "").strip()
        sesion = (request.data.get("sesion_clase_id") or "").strip()
        referencia = (request.data.get("elemento_ref") or "").strip()
        if not (host_id and sesion and referencia):
            return Response(
                {"detail": "Indica host_id, sesion_clase_id y elemento_ref."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            actual = componente.elemento(referencia)
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        except componente.ContenidoError as exc:
            codigo = exc.estado if exc.estado in (403, 404) else status.HTTP_502_BAD_GATEWAY
            return Response(
                {"detail": f"No se puede repartir lo que el equipo no ofrece. {exc}"},
                status=codigo,
            )

        curso_id = (request.data.get("curso") or "").strip() or None
        curso = Course.objects.filter(pk=curso_id).first() if curso_id else None

        fila, creada = RepartoActivo.objects.get_or_create(
            host_id=host_id, sesion_clase_id=sesion, elemento_ref=referencia,
            cerrado_en=None,
            defaults={
                "curso": curso,
                "grupo_id": request.data.get("grupo_id") or None,
                "version_elemento": str(actual.get("version") or "1"),
                "tipo": actual.get("tipo"),
                "abierto_por": request.data.get("actor") or "docente-ops",
                "creado_por": request.data.get("actor") or "docente-ops",
            },
        )
        return Response({
            "id": fila.id,
            "elemento_ref": fila.elemento_ref,
            "titulo": actual.get("titulo"),
            "tipo": fila.tipo,
            "abierto_en": fila.abierto_en,
            "ya_estaba": not creada,
            "message": "Repartido a la clase." if creada else "Ya estaba repartido.",
        }, status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)


class RepartoCerrarView(APIView):
    """POST /api/contenido/reparto/{id}/cerrar/ · retirar de la clase."""

    def post(self, _request, pk):
        fila = get_object_or_404(RepartoActivo, pk=pk)
        if fila.cerrado_en is None:
            fila.cerrado_en = now_ms()
            fila.save(update_fields=["cerrado_en"])
        return Response({
            "id": fila.id, "elemento_ref": fila.elemento_ref,
            "cerrado_en": fila.cerrado_en,
            "message": "Retirado de la clase. Queda el registro de que se mostró.",
        })


# ── Lo que ve una tableta ────────────────────────────────────────────────────
class StudentContenidoView(APIView):
    """
    GET /api/students/{persona_id}/contenido/?host_id=

    Lo que una tableta puede abrir ahora mismo. Sale del REPARTO, no del
    catálogo: el alumno ve lo que el docente proyectó, no la biblioteca entera.

    Un material repartido cuyo paquete se desinstaló aparece con
    `disponible: false` en vez de desvanecerse. Es la misma decisión que en el
    resto del prototipo: preferimos explicar que un material no está a que
    desaparezca sin motivo.
    """

    def get(self, request, persona_id):
        host_id = (request.query_params.get("host_id") or "").strip()
        filas = RepartoActivo.objects.filter(cerrado_en__isnull=True)
        if host_id:
            filas = filas.filter(host_id=host_id)
        filas = list(filas)
        resuelto, hay_componente, motivo = _resolver([f.elemento_ref for f in filas])
        return Response({
            "persona_id": persona_id,
            "componente_disponible": hay_componente,
            "motivo": motivo,
            "count": len(filas),
            "materiales": [{
                "elemento_ref": f.elemento_ref,
                "tipo": f.tipo,
                "abierto_en": f.abierto_en,
                **{k: resuelto[f.elemento_ref][k] for k in
                   ("disponible", "titulo", "duracion_seg", "motivo")},
            } for f in filas],
        })


# ── Exámenes: previsto, y honestamente apagado ───────────────────────────────
class ExamenMontarView(APIView):
    """
    POST /api/contenido/examen/montar/

    Monta un examen del LMS a partir de una evaluación o un banco del
    componente, y registra en m05_examen_pregunta qué preguntas le tocaron a
    cada persona.

    Necesita `GET /v1/evaluacion/{ref}` del componente, que es una de las seis
    rutas previstas y todavía no publicadas. Mientras no exista, esto responde
    501 con el motivo en vez de fingir: la lista de `capacidades` de /v1/salud es
    la que manda, y hoy llega vacía.
    """

    def post(self, request):
        referencia = (request.data.get("elemento_ref") or "").strip()
        actividad_id = (request.data.get("actividad") or "").strip()
        persona_id = (request.data.get("persona_id") or "").strip()
        if not (referencia and actividad_id and persona_id):
            return Response(
                {"detail": "Indica elemento_ref, actividad y persona_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        actividad = get_object_or_404(Activity, pk=actividad_id)

        estado_actual = componente.estado()
        if not estado_actual["disponible"]:
            return _sin_componente(estado_actual["motivo"])

        try:
            visible = componente.evaluacion(referencia, capacidades=estado_actual["capacidades"])
        except componente.ContenidoError as exc:
            return Response(
                {"detail": str(exc), "capacidades": estado_actual["capacidades"]},
                status=status.HTTP_501_NOT_IMPLEMENTED if exc.estado == 501 else status.HTTP_502_BAD_GATEWAY,
            )
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))

        preguntas = _lista(visible, "preguntas", "items")
        creadas = []
        for orden, pregunta in enumerate(preguntas, start=1):
            fila, _ = ExamenPregunta.objects.get_or_create(
                actividad=actividad, persona_id=persona_id,
                pregunta_ref=pregunta.get("ref") or pregunta.get("pregunta_ref"),
                defaults={
                    "elemento_ref": referencia,
                    "version_elemento": str(visible.get("version") or ""),
                    "orden": orden,
                    "creado_por": request.data.get("actor") or "docente-ops",
                },
            )
            creadas.append(fila.pregunta_ref)
        return Response({
            "actividad": actividad.id, "persona_id": persona_id,
            "elemento_ref": referencia, "preguntas": creadas,
        }, status=status.HTTP_201_CREATED)


class ExamenComprobarView(APIView):
    """
    POST /api/contenido/examen/comprobar/

    Califica UNA respuesta. La comparación ocurre dentro del componente: aquí
    solo viaja la respuesta del alumno y vuelve un booleano. La clave nunca entra
    al LMS, ni a una consulta, ni a un registro.

    Depende de `POST /v1/comprobar`, todavía no publicado.
    """

    def post(self, request):
        pregunta_ref = (request.data.get("pregunta_ref") or "").strip()
        if not pregunta_ref:
            return Response({"detail": "Indica pregunta_ref."}, status=status.HTTP_400_BAD_REQUEST)

        estado_actual = componente.estado()
        if not estado_actual["disponible"]:
            return _sin_componente(estado_actual["motivo"])
        try:
            veredicto = componente.comprobar(
                pregunta_ref, request.data.get("respuesta"),
                capacidades=estado_actual["capacidades"],
            )
        except componente.ContenidoError as exc:
            return Response(
                {"detail": str(exc), "capacidades": estado_actual["capacidades"]},
                status=status.HTTP_501_NOT_IMPLEMENTED if exc.estado == 501 else status.HTTP_502_BAD_GATEWAY,
            )
        except componente.ContenidoNoDisponible as exc:
            return _sin_componente(str(exc))
        return Response(veredicto)
