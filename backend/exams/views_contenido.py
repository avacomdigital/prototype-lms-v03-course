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
