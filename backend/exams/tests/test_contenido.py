"""
La integración con AVACOM-Contenido.

El componente es otro producto y no está en la máquina donde corren estas
pruebas, así que se levanta un servidor mínimo que responde las cinco rutas
reales con la MISMA forma que devuelve el componente —campos `ref`, `tipo`,
`titulo`, `version`, `taxonomia_ref`, `paquete`—, y se apunta a él con un
enlace.json de mentira.

Lo que se protege aquí, en orden de importancia:

  1. Que desinstalar contenido NO toque nada del LMS. Es la razón de ser de este
     diseño y es lo primero que hay que romper si alguien mete un `titulo` en
     m05_unidad_material.
  2. Que sin componente el LMS siga funcionando (artículo 9).
  3. Que las rutas que dependen de capacidades todavía no publicadas digan que
     faltan, en vez de fallar de forma que parezca un error del LMS.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse

from exams.models import (
    Course,
    CourseHost,
    ExamenPregunta,
    LessonProgress,
    RepartoActivo,
    UnidadMaterial,
)
from exams.progress import record_lesson_progress
from .factories import make_course

FICHA = "f" * 64

# Dos elementos de dos paquetes distintos, con la forma exacta del componente.
CATALOGO = [
    {
        "ref": "co-sec-mat-doc-funcion", "tipo": "documento", "titulo": "La función lineal",
        "nivel": "secundaria", "grado": "8", "asignatura": "Matemáticas", "idioma": "es",
        "taxonomia_ref": "co-sec-mat-var-e1-dba1", "version": "1",
        "duracion_seg": None, "paquete": "co-secundaria-8-matematicas", "huella": None,
    },
    {
        "ref": "co-sec-mat-video-pendiente", "tipo": "video", "titulo": "Qué significa la pendiente",
        "nivel": "secundaria", "grado": "8", "asignatura": "Matemáticas", "idioma": "es",
        "taxonomia_ref": "co-sec-mat-var-e1-dba2", "version": "1",
        "duracion_seg": 180, "paquete": "co-secundaria-8-matematicas", "huella": None,
    },
    {
        "ref": "co-pre-em-lam-granja", "tipo": "imagen", "titulo": "Lámina de la granja",
        "nivel": "preescolar", "grado": "transicion", "asignatura": "Exploración del medio",
        "idioma": "es", "taxonomia_ref": "co-pre-p3-em-vivos", "version": "1",
        "duracion_seg": None, "paquete": "co-preescolar-transicion-exploracion", "huella": None,
    },
]


class ComponenteDeMentira:
    """
    Un componente que responde como el de verdad.

    `retirados` es lo que hace útil esta clase: quitar una clave de paquete
    simula desinstalarlo, que es exactamente el escenario que hay que proteger.
    """

    def __init__(self):
        self.retirados = set()
        self.capacidades = []
        self.huella = None
        self.exige_ficha = True
        self.fichas_recibidas = []
        self._servidor = None
        self._hilo = None

    @property
    def vivos(self):
        return [e for e in CATALOGO if e["paquete"] not in self.retirados]

    def arrancar(self):
        prueba = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _responder(self, codigo, cuerpo):
                crudo = json.dumps(cuerpo, ensure_ascii=False).encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(crudo)))
                self.end_headers()
                self.wfile.write(crudo)

            def do_GET(self):
                prueba.fichas_recibidas.append(self.headers.get("X-Avacom-Ficha"))
                if prueba.exige_ficha and self.headers.get("X-Avacom-Ficha") != FICHA:
                    return self._responder(401, {"error": "sin ficha"})

                partes = urlparse(self.path)
                if partes.path == "/v1/salud":
                    cuerpo = {
                        "componente": "avacom-contenido", "contrato": 1,
                        "elementos": len(prueba.vivos),
                        "paquetes": len({e["paquete"] for e in prueba.vivos}),
                        "politicas": 0,
                    }
                    if prueba.capacidades:
                        cuerpo["capacidades"] = prueba.capacidades
                        cuerpo["generacion"] = 47
                    if prueba.huella:
                        # El componente real ya publica esto aunque no publique
                        # generacion todavia.
                        cuerpo["huella_catalogo"] = prueba.huella
                    return self._responder(200, cuerpo)

                if partes.path == "/v1/catalogo":
                    q = parse_qs(partes.query)
                    salida = prueba.vivos
                    for clave in ("nivel", "grado", "asignatura", "tipo"):
                        if clave in q:
                            salida = [e for e in salida if e.get(clave) == q[clave][0]]
                    return self._responder(200, {"elementos": salida})

                if partes.path == "/v1/taxonomia":
                    return self._responder(200, {"nodos": [
                        {"ref": "co-sec-area-mat", "padre": None, "tipo": "area",
                         "codigo": "L115-A8", "nombre": "Matemáticas", "orden": 8,
                         "pais": "CO", "nivel": "secundaria"},
                    ]})

                if partes.path.startswith("/v1/elemento/"):
                    referencia = unquote(partes.path[len("/v1/elemento/"):])
                    encontrado = next((e for e in prueba.vivos if e["ref"] == referencia), None)
                    if encontrado is None:
                        return self._responder(404, {"error": "no instalado"})
                    return self._responder(200, encontrado)

                return self._responder(404, {"error": "ruta desconocida"})

            def do_POST(self):
                if prueba.exige_ficha and self.headers.get("X-Avacom-Ficha") != FICHA:
                    return self._responder(401, {"error": "sin ficha"})
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = json.loads(self.rfile.read(largo) or b"{}")
                camino = urlparse(self.path).path
                if camino == "/v1/mostrar":
                    return self._responder(200, {"aceptado": True})
                if camino == "/v1/comprobar":
                    # El de verdad compara contra el manifiesto cifrado y devuelve
                    # un booleano. Nunca la clave: por eso aquí tampoco.
                    return self._responder(200, {"acierta": cuerpo.get("respuesta") == "3"})
                return self._responder(404, {"error": "ruta desconocida"})

        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self._hilo = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._hilo.start()
        return self._servidor.server_address[1]

    def parar(self):
        if self._servidor:
            self._servidor.shutdown()
            self._servidor.server_close()


class BaseContenido(TestCase):
    """Levanta el componente de mentira y escribe su enlace.json."""

    def setUp(self):
        self.componente = ComponenteDeMentira()
        puerto = self.componente.arrancar()
        self.addCleanup(self.componente.parar)

        import tempfile, os

        carpeta = tempfile.mkdtemp()
        self.enlace = os.path.join(carpeta, "enlace.json")
        self._escribir_enlace(puerto)

        ajuste = override_settings(AVACOM_CONTENIDO_ENLACE=self.enlace)
        ajuste.enable()
        self.addCleanup(ajuste.disable)

        self.curso, _ = make_course(title="Curso con material")
        self.leccion = self.curso.version_activa.secciones.first().lecciones.first()

    def _escribir_enlace(self, puerto, contrato=1):
        with open(self.enlace, "w", encoding="utf-8") as archivo:
            json.dump({"Contrato": contrato, "Puerto": puerto, "Ficha": FICHA, "Proceso": 1}, archivo)

    def colgar(self, referencia):
        return self.client.post(
            reverse("leccion-materiales", args=[self.leccion.id]),
            {"elemento_ref": referencia, "actor": "docente-ops"},
            content_type="application/json",
        )

    def materiales(self):
        respuesta = self.client.get(reverse("leccion-materiales", args=[self.leccion.id]))
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return respuesta.json()


class DescubrimientoTests(BaseContenido):
    def test_el_lms_encuentra_el_componente(self):
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertTrue(datos["disponible"])
        self.assertEqual(datos["componente"], "avacom-contenido")
        self.assertEqual(datos["contrato"], 1)
        self.assertEqual(datos["conteos"]["elementos"], 3)

    def test_cada_llamada_lleva_la_ficha(self):
        self.client.get(reverse("contenido-catalogo"))
        self.assertTrue(self.componente.fichas_recibidas)
        self.assertTrue(all(f == FICHA for f in self.componente.fichas_recibidas))

    def test_un_contrato_mas_nuevo_se_rechaza_con_explicacion(self):
        """
        Si el componente habla un contrato que este LMS no entiende, no se
        adivina: se dice que hay que actualizar el LMS.
        """
        self._escribir_enlace(1, contrato=99)
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertFalse(datos["disponible"])
        self.assertIn("contrato 99", datos["motivo"])

    def test_las_capacidades_llegan_cuando_el_componente_las_publica(self):
        self.componente.capacidades = ["leccion", "evaluacion", "comprobar"]
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertEqual(datos["capacidades"], ["leccion", "evaluacion", "comprobar"])
        self.assertEqual(datos["generacion"], 47)
        self.assertFalse(datos["generacion_derivada"])

    def test_sin_generacion_se_deriva_una_huella(self):
        """Mientras el componente no publique `generacion`, algo hay que comparar."""
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertTrue(datos["generacion_derivada"])
        self.assertEqual(datos["huella_catalogo"], "c3-2-0")


class CatalogoTests(BaseContenido):
    def test_el_catalogo_pasa_por_el_backend(self):
        datos = self.client.get(reverse("contenido-catalogo")).json()
        self.assertEqual(datos["count"], 3)
        self.assertEqual(datos["elementos"][0]["ref"], "co-sec-mat-doc-funcion")

    def test_los_filtros_viajan_al_componente(self):
        datos = self.client.get(reverse("contenido-catalogo"), {"nivel": "preescolar"}).json()
        self.assertEqual([e["ref"] for e in datos["elementos"]], ["co-pre-em-lam-granja"])

    def test_la_taxonomia_se_navega_por_padre(self):
        """Su profundidad varía: preescolar tiene cuatro niveles y no tiene asignatura."""
        datos = self.client.get(reverse("contenido-taxonomia")).json()
        self.assertEqual(datos["count"], 1)
        self.assertIsNone(datos["nodos"][0]["padre"])


class MaterialTests(BaseContenido):
    def test_colgar_guarda_referencia_y_version_nada_mas(self):
        respuesta = self.colgar("co-sec-mat-doc-funcion")
        self.assertEqual(respuesta.status_code, 201, respuesta.content)

        fila = UnidadMaterial.objects.get()
        self.assertEqual(fila.elemento_ref, "co-sec-mat-doc-funcion")
        self.assertEqual(fila.version_elemento, "1")
        self.assertEqual(fila.taxonomia_ref, "co-sec-mat-var-e1-dba1")
        # La comprobación que sostiene todo el diseño: el título NO está en la
        # tabla. Si algún día lo está, el LMS es un segundo catálogo.
        self.assertFalse(hasattr(fila, "titulo"))

    def test_el_titulo_se_resuelve_en_vivo(self):
        self.colgar("co-sec-mat-doc-funcion")
        material = self.materiales()["materiales"][0]
        self.assertEqual(material["titulo"], "La función lineal")
        self.assertTrue(material["disponible"])

    def test_no_se_puede_colgar_lo_que_el_equipo_no_tiene(self):
        respuesta = self.colgar("no-existe")
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(UnidadMaterial.objects.count(), 0)

    def test_colgar_dos_veces_lo_mismo_se_rechaza(self):
        self.colgar("co-sec-mat-doc-funcion")
        self.assertEqual(self.colgar("co-sec-mat-doc-funcion").status_code, 409)
        self.assertEqual(UnidadMaterial.objects.count(), 1)

    def test_quitar_la_referencia_no_desinstala_nada(self):
        """El LMS no instala ni desinstala contenido, y tampoco se lo pide."""
        self.colgar("co-sec-mat-doc-funcion")
        fila = UnidadMaterial.objects.get()
        respuesta = self.client.delete(reverse("material-detalle", args=[fila.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(UnidadMaterial.objects.count(), 0)
        # El elemento sigue en el catálogo del componente.
        self.assertEqual(self.client.get(reverse("contenido-catalogo")).json()["count"], 3)


class EliminarContenidoTests(BaseContenido):
    """
    La razón de ser de todo esto: el contenido va y viene, los registros del LMS
    se quedan.
    """

    def setUp(self):
        super().setUp()
        self.colgar("co-sec-mat-doc-funcion")
        self.colgar("co-sec-mat-video-pendiente")
        record_lesson_progress(self.curso.id, "juan", "lec-uno", 100, actor="juan")
        record_lesson_progress(self.curso.id, "juan", "lec-dos", 40, actor="juan")

    def retirar_paquete(self):
        self.componente.retirados.add("co-secundaria-8-matematicas")

    def test_al_desinstalar_las_referencias_siguen(self):
        antes = self.materiales()
        self.retirar_paquete()
        despues = self.materiales()

        self.assertEqual(despues["count"], antes["count"])
        self.assertEqual(despues["disponibles"], 0)
        self.assertEqual(UnidadMaterial.objects.count(), 2)

    def test_al_desinstalar_el_progreso_no_se_toca(self):
        antes = list(LessonProgress.objects.filter(curso=self.curso).values_list(
            "leccion_codigo", "porcentaje"))
        self.retirar_paquete()
        self.materiales()
        despues = list(LessonProgress.objects.filter(curso=self.curso).values_list(
            "leccion_codigo", "porcentaje"))
        self.assertEqual(antes, despues)

    def test_al_desinstalar_se_explica_por_que(self):
        self.retirar_paquete()
        for material in self.materiales()["materiales"]:
            self.assertFalse(material["disponible"])
            self.assertTrue(material["motivo"])
            # Sin componente que lo diga, no hay título. Inventarlo sería
            # empezar a mantener un catálogo paralelo.
            self.assertIsNone(material["titulo"])

    def test_al_reinstalar_vuelve_solo(self):
        self.retirar_paquete()
        self.assertEqual(self.materiales()["disponibles"], 0)

        self.componente.retirados.clear()
        vuelto = self.materiales()
        self.assertEqual(vuelto["disponibles"], 2)
        self.assertEqual(vuelto["materiales"][0]["titulo"], "La función lineal")
        # Y nadie tuvo que volver a colgarlo.
        self.assertEqual(UnidadMaterial.objects.count(), 2)

    def test_lo_de_otro_paquete_no_se_ve_afectado(self):
        self.colgar("co-pre-em-lam-granja")
        self.retirar_paquete()
        por_ref = {m["elemento_ref"]: m for m in self.materiales()["materiales"]}
        self.assertFalse(por_ref["co-sec-mat-doc-funcion"]["disponible"])
        self.assertTrue(por_ref["co-pre-em-lam-granja"]["disponible"])


class SinComponenteTests(BaseContenido):
    """Artículo 9 · sin contenido, el LMS sigue funcionando."""

    def apagar(self):
        self.componente.parar()

    def test_el_estado_lo_dice_sin_reventar(self):
        self.apagar()
        respuesta = self.client.get(reverse("contenido-estado"))
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertFalse(datos["disponible"])
        self.assertTrue(datos["motivo"])
        self.assertEqual(datos["capacidades"], [])

    def test_sin_nota_de_enlace_tampoco_revienta(self):
        import os

        os.unlink(self.enlace)
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertFalse(datos["disponible"])
        self.assertIn("biblioteca", datos["motivo"].lower())

    def test_la_leccion_se_sigue_dibujando(self):
        self.colgar("co-sec-mat-doc-funcion")
        self.apagar()
        datos = self.materiales()
        self.assertEqual(datos["count"], 1)
        self.assertFalse(datos["componente_disponible"])
        self.assertFalse(datos["materiales"][0]["disponible"])

    def test_el_catalogo_responde_503_no_500(self):
        """503 dice «vuelve luego»; un 500 dice «el LMS está roto», y no lo está."""
        self.apagar()
        self.assertEqual(self.client.get(reverse("contenido-catalogo")).status_code, 503)


class RepartoTests(BaseContenido):
    def repartir(self, referencia):
        return self.client.post(reverse("contenido-reparto"), {
            "host_id": "OPS-1", "sesion_clase_id": "clase-1",
            "elemento_ref": referencia, "curso": self.curso.id, "actor": "docente-ops",
        }, content_type="application/json")

    def test_repartir_y_que_la_tableta_lo_vea(self):
        self.assertEqual(self.repartir("co-sec-mat-video-pendiente").status_code, 201)
        datos = self.client.get(
            reverse("student-contenido", args=["juan"]), {"host_id": "OPS-1"}).json()
        self.assertEqual(datos["count"], 1)
        self.assertTrue(datos["materiales"][0]["disponible"])
        self.assertEqual(datos["materiales"][0]["titulo"], "Qué significa la pendiente")

    def test_no_se_reparte_lo_que_no_esta(self):
        self.assertEqual(self.repartir("no-existe").status_code, 404)
        self.assertEqual(RepartoActivo.objects.count(), 0)

    def test_repartir_dos_veces_no_duplica(self):
        self.repartir("co-sec-mat-video-pendiente")
        segunda = self.repartir("co-sec-mat-video-pendiente")
        self.assertEqual(segunda.status_code, 200)
        self.assertTrue(segunda.json()["ya_estaba"])
        self.assertEqual(RepartoActivo.objects.filter(cerrado_en__isnull=True).count(), 1)

    def test_cerrar_lo_retira_pero_deja_constancia(self):
        self.repartir("co-sec-mat-video-pendiente")
        fila = RepartoActivo.objects.get()
        self.client.post(reverse("contenido-reparto-cerrar", args=[fila.id]))
        fila.refresh_from_db()
        self.assertIsNotNone(fila.cerrado_en)
        # Se conserva para poder explicar qué se mostró en esa clase.
        self.assertEqual(RepartoActivo.objects.count(), 1)
        datos = self.client.get(
            reverse("student-contenido", args=["juan"]), {"host_id": "OPS-1"}).json()
        self.assertEqual(datos["count"], 0)

    def test_si_desinstalan_lo_repartido_la_tableta_lo_dice(self):
        self.repartir("co-sec-mat-video-pendiente")
        self.componente.retirados.add("co-secundaria-8-matematicas")
        datos = self.client.get(
            reverse("student-contenido", args=["juan"]), {"host_id": "OPS-1"}).json()
        self.assertEqual(datos["count"], 1)
        self.assertFalse(datos["materiales"][0]["disponible"])
        self.assertTrue(datos["materiales"][0]["motivo"])


class CapacidadesTests(BaseContenido):
    """Las seis rutas del D-2 todavía no existen. El LMS degrada, no se rompe."""

    def test_comprobar_sin_capacidad_responde_501(self):
        respuesta = self.client.post(reverse("contenido-examen-comprobar"), {
            "pregunta_ref": "co-sec-q-01", "respuesta": "3"}, content_type="application/json")
        self.assertEqual(respuesta.status_code, 501)
        self.assertIn("comprobar", respuesta.json()["detail"])

    def test_con_la_capacidad_publicada_se_usa(self):
        self.componente.capacidades = ["comprobar"]
        respuesta = self.client.post(reverse("contenido-examen-comprobar"), {
            "pregunta_ref": "co-sec-q-01", "respuesta": "3"}, content_type="application/json")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertTrue(respuesta.json()["acierta"])

    def test_la_clave_de_respuesta_no_aparece_en_la_respuesta(self):
        """
        Artículo 3 · la clave no sale del componente. Lo que vuelve es un
        veredicto; si algún día apareciera la clave aquí, esta prueba cae.
        """
        self.componente.capacidades = ["comprobar"]
        respuesta = self.client.post(reverse("contenido-examen-comprobar"), {
            "pregunta_ref": "co-sec-q-01", "respuesta": "9"}, content_type="application/json")
        crudo = respuesta.content.decode().lower()
        self.assertNotIn("clave", crudo)
        self.assertNotIn("clave_respuesta", crudo)
        self.assertFalse(respuesta.json()["acierta"])

    def test_montar_examen_sin_capacidad_responde_501(self):
        actividad = self.curso.version_activa.secciones.first().lecciones.first() \
            .items.filter(actividad__isnull=False).first()
        if actividad is None:
            self.skipTest("el curso de prueba no trae actividad")
        respuesta = self.client.post(reverse("contenido-examen-montar"), {
            "elemento_ref": "co-sec-mat-eval", "actividad": actividad.actividad_id,
            "persona_id": "juan"}, content_type="application/json")
        self.assertEqual(respuesta.status_code, 501)
        self.assertEqual(ExamenPregunta.objects.count(), 0)


class ReconciliacionTests(BaseContenido):
    """
    Poner al día qué material sigue disponible.

    Es lo que corre al abrir el resumen del panel y al pulsar «Actualizar». Lo
    que estas pruebas protegen, en orden: que actualice la disponibilidad, que
    retire de las tabletas lo que ya no se puede servir, y que NO toque nada del
    expediente académico. Si algún día alguien hace que esto borre una
    referencia o una nota, aquí se cae.
    """

    def setUp(self):
        super().setUp()
        self.colgar("co-sec-mat-doc-funcion")
        self.colgar("co-sec-mat-video-pendiente")
        self.colgar("co-pre-em-lam-granja")
        record_lesson_progress(self.curso.id, "juan", "lec-uno", 100, actor="juan")

    def reconciliar(self, host="OPS-1"):
        return self.client.post(
            reverse("contenido-reconciliar"),
            {"host_id": host, "actor": "docente-ops"},
            content_type="application/json",
        )

    def test_sin_cambios_no_cambia_nada(self):
        datos = self.reconciliar().json()
        self.assertFalse(datos["hubo_cambios"])
        self.assertEqual(datos["disponibles"], 3)
        self.assertEqual(datos["no_disponibles"], 0)

    def test_al_desaparecer_se_marca_con_fecha(self):
        self.componente.retirados.add("co-secundaria-8-matematicas")
        datos = self.reconciliar().json()

        self.assertTrue(datos["hubo_cambios"])
        self.assertCountEqual(
            datos["desaparecidos"],
            ["co-sec-mat-doc-funcion", "co-sec-mat-video-pendiente"])
        self.assertEqual(datos["disponibles"], 1)

        for fila in UnidadMaterial.objects.filter(elemento_ref__startswith="co-sec"):
            self.assertFalse(fila.disponible_ultima_revision)
            # Un «no está» sin fecha no se puede explicar.
            self.assertIsNotNone(fila.desaparecido_en)

    def test_lo_de_otro_paquete_sigue_disponible(self):
        self.componente.retirados.add("co-secundaria-8-matematicas")
        self.reconciliar()
        granja = UnidadMaterial.objects.get(elemento_ref="co-pre-em-lam-granja")
        self.assertTrue(granja.disponible_ultima_revision)
        self.assertIsNone(granja.desaparecido_en)

    def test_no_borra_nada_del_expediente(self):
        """La comprobación que sostiene todo: el contenido va y viene, el LMS se queda."""
        referencias = UnidadMaterial.objects.count()
        progreso = list(LessonProgress.objects.values_list("leccion_codigo", "porcentaje"))
        cursos = Course.objects.count()

        self.componente.retirados.add("co-secundaria-8-matematicas")
        self.componente.retirados.add("co-preescolar-transicion-exploracion")
        self.reconciliar()

        self.assertEqual(UnidadMaterial.objects.count(), referencias)
        self.assertEqual(
            list(LessonProgress.objects.values_list("leccion_codigo", "porcentaje")), progreso)
        self.assertEqual(Course.objects.count(), cursos)

    def test_al_volver_se_limpia_la_fecha(self):
        self.componente.retirados.add("co-secundaria-8-matematicas")
        self.reconciliar()
        self.componente.retirados.clear()
        datos = self.reconciliar().json()

        self.assertCountEqual(
            datos["reaparecidos"],
            ["co-sec-mat-doc-funcion", "co-sec-mat-video-pendiente"])
        for fila in UnidadMaterial.objects.all():
            self.assertTrue(fila.disponible_ultima_revision)
            # La fecha se limpia: si no, seguiría contando una ausencia terminada.
            self.assertIsNone(fila.desaparecido_en)

    def test_retira_de_las_tabletas_lo_que_ya_no_se_puede_servir(self):
        self.client.post(reverse("contenido-reparto"), {
            "host_id": "OPS-1", "sesion_clase_id": "clase-1",
            "elemento_ref": "co-sec-mat-video-pendiente", "actor": "docente-ops",
        }, content_type="application/json")
        self.assertEqual(RepartoActivo.objects.filter(cerrado_en__isnull=True).count(), 1)

        self.componente.retirados.add("co-secundaria-8-matematicas")
        datos = self.reconciliar().json()

        self.assertEqual(datos["repartos_cerrados"], ["co-sec-mat-video-pendiente"])
        self.assertEqual(RepartoActivo.objects.filter(cerrado_en__isnull=True).count(), 0)
        # Se conserva cerrado, para poder explicar qué se mostró en esa clase.
        self.assertEqual(RepartoActivo.objects.count(), 1)

    def test_es_idempotente(self):
        """Se cuelga de la apertura de una pantalla y de un botón: se dispara mucho."""
        self.componente.retirados.add("co-secundaria-8-matematicas")
        primera = self.reconciliar().json()
        segunda = self.reconciliar().json()
        self.assertTrue(primera["hubo_cambios"])
        self.assertFalse(segunda["hubo_cambios"])
        self.assertEqual(segunda["desaparecidos"], [])

    def test_sin_biblioteca_no_marca_nada_como_desaparecido(self):
        """
        El error que arruinaría una clase: si la biblioteca está cerrada y se
        reconcilia contra un catálogo vacío, todo el material del curso quedaría
        marcado como ausente. Por eso sin biblioteca no se escribe.
        """
        self.componente.parar()
        respuesta = self.reconciliar()
        self.assertEqual(respuesta.status_code, 503)
        for fila in UnidadMaterial.objects.all():
            self.assertTrue(fila.disponible_ultima_revision)
            self.assertIsNone(fila.desaparecido_en)

    def test_una_version_mas_nueva_se_avisa_pero_no_se_cambia_sola(self):
        fila = UnidadMaterial.objects.get(elemento_ref="co-sec-mat-doc-funcion")
        fila.version_elemento = "0"
        fila.save(update_fields=["version_elemento"])

        datos = self.reconciliar().json()
        self.assertEqual(len(datos["cambio_version"]), 1)
        aviso = datos["cambio_version"][0]
        self.assertEqual(aviso["version_guardada"], "0")
        self.assertEqual(aviso["version_disponible"], "1")

        # La referencia NO se reescribe: actualizarla es decisión del docente.
        fila.refresh_from_db()
        self.assertEqual(fila.version_elemento, "0")

    def test_el_resumen_por_curso_marca_lo_que_falta(self):
        self.componente.retirados.add("co-secundaria-8-matematicas")
        datos = self.reconciliar().json()
        por_curso = {c["curso"]: c for c in datos["por_curso"]}
        mio = por_curso[self.curso.id]
        self.assertEqual(mio["materiales"], 3)
        self.assertEqual(mio["ausentes"], 2)
        self.assertIsNotNone(mio["ausentes_desde"])

    def test_el_get_no_escribe(self):
        """La consulta sirve para pintar sin decidir; escribir es del POST."""
        self.componente.retirados.add("co-secundaria-8-matematicas")
        respuesta = self.client.get(reverse("contenido-reconciliar"))
        self.assertEqual(respuesta.status_code, 200)
        for fila in UnidadMaterial.objects.all():
            self.assertTrue(fila.disponible_ultima_revision)

    def test_el_material_de_la_leccion_dice_desde_cuando_falta(self):
        self.componente.retirados.add("co-secundaria-8-matematicas")
        self.reconciliar()
        por_ref = {m["elemento_ref"]: m for m in self.materiales()["materiales"]}
        ausente = por_ref["co-sec-mat-doc-funcion"]
        self.assertFalse(ausente["disponible_ultima_revision"])
        self.assertIsNotNone(ausente["desaparecido_en"])
        self.assertIsNotNone(ausente["revisado_en"])


class PuertoQueCambiaTests(BaseContenido):
    """
    El componente escoge un puerto nuevo en cada arranque y reescribe la nota.
    El LMS tiene que seguirlo sin reiniciarse.
    """

    def test_el_cliente_relee_la_nota_en_cada_llamada(self):
        primero = self.client.get(reverse("contenido-catalogo")).json()
        self.assertEqual(primero["count"], 3)

        # La biblioteca se reinicia: otro puerto, misma nota reescrita.
        self.componente.parar()
        nuevo = ComponenteDeMentira()
        puerto = nuevo.arrancar()
        self.addCleanup(nuevo.parar)
        self.componente = nuevo
        self._escribir_enlace(puerto)

        segundo = self.client.get(reverse("contenido-catalogo")).json()
        self.assertEqual(segundo["count"], 3, "el LMS siguio al puerto nuevo sin reiniciarse")

    def test_el_estado_dice_quien_atiende(self):
        """
        La nota es un archivo y sobrevive al proceso. Saber de quién es el puerto
        convierte «dos componentes peleándose el enlace» en algo que se ve.
        """
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertEqual(datos["proceso"], 1)
        self.assertIn(datos["proceso_vivo"], (True, False, None))

    def test_preguntar_por_un_proceso_no_lo_mata(self):
        """
        En Windows os.kill(pid, 0) NO es una consulta: CPython lo traduce a
        TerminateProcess. Esta prueba fija que el diagnóstico use un handle de
        solo consulta, porque la alternativa es cerrar la biblioteca en mitad de
        una clase.
        """
        import subprocess
        import sys
        import time

        from exams.contenido import proceso_vivo

        cobaya = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(cobaya.kill)
        try:
            time.sleep(0.5)
            self.assertTrue(proceso_vivo(cobaya.pid))
            for _ in range(5):
                proceso_vivo(cobaya.pid)
            self.assertIsNone(cobaya.poll(), "preguntar por el proceso lo termino")
        finally:
            cobaya.kill()


class ContenidoDelCursoTests(BaseContenido):
    """
    El veredicto de un curso: si su contenido sigue en el equipo.

    Es lo que decide si el panel muestra la estructura o el aviso de contenido
    desinstalado, así que estas pruebas fijan los cuatro caminos por los que un
    curso puede quedarse sin contenido, y —lo que más importa— los dos casos en
    los que NO hay que decir que falta.
    """

    def veredicto(self, curso=None):
        respuesta = self.client.get(
            reverse("curso-contenido", args=[(curso or self.curso).id]))
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return respuesta.json()

    def declarar_origen(self, paquete, formato=CourseHost.FORMATO_AVACOM_CONTENIDO,
                        presente=True):
        """Deja el curso registrado como venido de un paquete de la biblioteca."""
        return CourseHost.objects.create(
            host_id="OPS-1", curso=self.curso,
            curso_version=self.curso.version_activa,
            formato_contenido=formato,
            package_identifier=paquete,
            presente_local=presente,
            disponible_estudiante=presente,
            retirado_en=None if presente else 1_700_000_000_000,
            creado_por="docente-ops",
        )

    # ── Cuando NO hay que decir que falta ────────────────────────────────────
    def test_un_curso_hecho_a_mano_no_depende_de_la_biblioteca(self):
        """
        Sin fila en m05_curso_host el curso se creó en el LMS. Juzgarlo contra
        el catálogo lo marcaría como retirado sin que nadie haya quitado nada.
        """
        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])
        self.assertFalse(datos["origen"]["depende_de_biblioteca"])
        self.assertIsNone(datos["origen"]["paquete_presente"])

    def test_un_curso_SCORM_no_se_juzga_contra_el_catalogo(self):
        """
        Su contenido se copió al LMS al importarlo y su paquete nunca estuvo en
        /v1/catalogo. Compararlo ahí lo declararía desinstalado siempre.
        """
        self.declarar_origen("com.scorm.plantilla", formato=CourseHost.FORMATO_SCORM_12)
        datos = self.veredicto()
        self.assertFalse(datos["origen"]["depende_de_biblioteca"])
        self.assertIsNone(datos["origen"]["paquete_presente"])
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])

    def test_sin_biblioteca_no_se_afirma_que_falte(self):
        """
        La biblioteca cerrada no es contenido borrado. Se dice «no se pudo
        comprobar» y la estructura se sigue mostrando.
        """
        self.declarar_origen("co-secundaria-8-matematicas")
        self.componente.parar()
        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])
        self.assertFalse(datos["componente_disponible"])
        self.assertIsNone(datos["origen"]["paquete_presente"])
        self.assertIn("comprobar", datos["motivo"])

    # ── Los cuatro caminos a «retirado» ──────────────────────────────────────
    def test_su_paquete_ya_no_esta_en_el_catalogo(self):
        """El caso de «Exploración del medio»: el paquete salió de la biblioteca."""
        self.declarar_origen("co-preescolar-transicion-exploracion")
        self.componente.retirados.add("co-preescolar-transicion-exploracion")

        datos = self.veredicto()
        self.assertTrue(datos["contenido_retirado"])
        self.assertFalse(datos["estructura_visible"])
        self.assertFalse(datos["origen"]["paquete_presente"])
        self.assertIn("co-preescolar-transicion-exploracion", datos["motivo"])

    def test_su_paquete_sigue_y_lista_sus_elementos(self):
        self.declarar_origen("co-secundaria-8-matematicas")
        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])
        self.assertEqual(datos["conteos"]["elementos_del_paquete"], 2)
        titulos = [e["titulo"] for e in datos["elementos"]]
        self.assertIn("La función lineal", titulos)

    def test_lo_desinstalaron_de_esta_OPS(self):
        """
        `presente_local` es la fuente de verdad para el contenido que el LMS
        copió al importarlo: sus archivos son suyos.
        """
        self.declarar_origen("com.scorm.plantilla",
                             formato=CourseHost.FORMATO_SCORM_12, presente=False)
        datos = self.veredicto()
        self.assertTrue(datos["contenido_retirado"])
        self.assertFalse(datos["estructura_visible"])
        self.assertIn("desinstaló de esta OPS", datos["motivo"])
        self.assertIsNotNone(datos["origen"]["retirado_en"])

    def test_para_un_curso_de_biblioteca_el_catalogo_manda(self):
        """
        Antes esta prueba esperaba lo contrario, y era el defecto: reinstalar el
        paquete no quitaba el cartel porque el veredicto miraba primero una
        bandera del LMS que cachea un hecho que vive en la biblioteca.
        """
        self.declarar_origen("co-secundaria-8-matematicas", presente=False)
        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])
        self.assertTrue(datos["origen"]["paquete_presente"])

    def test_si_todo_su_material_colgado_esta_ausente(self):
        """Sin fila de origen, el veredicto sale de las referencias colgadas."""
        self.colgar("co-sec-mat-doc-funcion")
        self.colgar("co-sec-mat-video-pendiente")
        self.assertFalse(self.veredicto()["contenido_retirado"])

        self.componente.retirados.add("co-secundaria-8-matematicas")
        datos = self.veredicto()
        self.assertTrue(datos["contenido_retirado"])
        self.assertEqual(datos["conteos"]["materiales_ausentes"], 2)
        self.assertEqual(datos["conteos"]["materiales_disponibles"], 0)

    def test_si_queda_algo_disponible_no_esta_retirado(self):
        """Un curso a medias sigue teniendo algo que abrir."""
        self.colgar("co-sec-mat-doc-funcion")
        self.colgar("co-pre-em-lam-granja")
        self.componente.retirados.add("co-secundaria-8-matematicas")

        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])
        self.assertEqual(datos["conteos"]["materiales_disponibles"], 1)
        self.assertEqual(datos["conteos"]["materiales_ausentes"], 1)

    # ── Lo que el veredicto NO debe tocar ────────────────────────────────────
    def test_el_veredicto_no_escribe_nada(self):
        """Es una consulta. Marcar disponibilidad es de la reconciliación."""
        self.colgar("co-sec-mat-doc-funcion")
        self.componente.retirados.add("co-secundaria-8-matematicas")
        self.veredicto()
        fila = UnidadMaterial.objects.get()
        self.assertTrue(fila.disponible_ultima_revision)
        self.assertIsNone(fila.desaparecido_en)

    def test_retirado_no_borra_el_expediente(self):
        record_lesson_progress(self.curso.id, "juan", "lec-uno", 100, actor="juan")
        self.declarar_origen("co-preescolar-transicion-exploracion")
        self.componente.retirados.add("co-preescolar-transicion-exploracion")

        self.assertTrue(self.veredicto()["contenido_retirado"])
        self.assertEqual(LessonProgress.objects.filter(curso=self.curso).count(), 1)
        self.assertTrue(Course.objects.filter(pk=self.curso.id).exists())

    def test_al_reinstalar_vuelve_a_estar_vigente(self):
        self.declarar_origen("co-preescolar-transicion-exploracion")
        self.componente.retirados.add("co-preescolar-transicion-exploracion")
        self.assertTrue(self.veredicto()["contenido_retirado"])

        self.componente.retirados.clear()
        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])

    def test_un_curso_que_no_existe_da_404(self):
        self.assertEqual(
            self.client.get(reverse("curso-contenido", args=["no-existe"])).status_code, 404)


class ReinstalarQuitaElCartelTests(BaseContenido):
    """
    Reinstalar el paquete tiene que quitar el cartel de «contenido desinstalado».

    El defecto que estas pruebas fijan: el veredicto consultaba primero
    `m05_curso_host.presente_local`, que es una bandera del LMS cacheando un
    hecho que vive en la biblioteca. Reinstalar el paquete no la cambiaba, así
    que el cartel se quedaba pegado y solo desaparecía si alguien reinstalaba
    también desde el panel del LMS.

    La regla que quedó: cuando el contenido de un curso vive en la biblioteca, el
    catálogo manda sobre lo que el LMS tenga guardado. Un curso SCORM o CMI5 no,
    porque sus archivos son del LMS.
    """

    PAQUETE = "co-preescolar-transicion-exploracion"

    def setUp(self):
        super().setUp()
        # El catálogo de prueba trae un elemento de preescolar; se retira para
        # empezar desde el estado que reportó Gabriel.
        self.fila = CourseHost.objects.create(
            host_id="OPS-1", curso=self.curso,
            curso_version=self.curso.version_activa,
            formato_contenido=CourseHost.FORMATO_AVACOM_CONTENIDO,
            package_identifier=self.PAQUETE,
            presente_local=False, disponible_estudiante=False,
            retirado_en=1_700_000_000_000, creado_por="docente-ops",
        )

    def veredicto(self):
        respuesta = self.client.get(reverse("curso-contenido", args=[self.curso.id]))
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return respuesta.json()

    def test_con_el_paquete_fuera_el_cartel_aparece(self):
        self.componente.retirados.add(self.PAQUETE)
        datos = self.veredicto()
        self.assertTrue(datos["contenido_retirado"])
        self.assertFalse(datos["estructura_visible"])

    def test_al_reinstalar_el_cartel_desaparece(self):
        """El caso exacto del informe: presente_local viejo, paquete de vuelta."""
        self.componente.retirados.add(self.PAQUETE)
        self.assertTrue(self.veredicto()["contenido_retirado"])

        # El paquete vuelve a la biblioteca. presente_local sigue en False.
        self.componente.retirados.clear()
        datos = self.veredicto()

        self.assertFalse(datos["contenido_retirado"])
        self.assertTrue(datos["estructura_visible"])
        self.assertTrue(datos["origen"]["paquete_presente"])

    def test_al_reinstalar_se_sanea_el_registro(self):
        """
        Y la base deja de mentir, que es lo que permite decírselo a la tableta:
        si `presente_local` se quedara en false, el catálogo del estudiante
        seguiría escondiendo el curso.
        """
        datos = self.veredicto()
        self.assertFalse(datos["contenido_retirado"])

        self.fila.refresh_from_db()
        self.assertTrue(self.fila.presente_local)
        self.assertTrue(self.fila.disponible_estudiante)
        self.assertIsNone(self.fila.retirado_en)

    def test_un_curso_SCORM_no_se_sanea_solo(self):
        """
        Sus archivos son del LMS: `presente_local` es la fuente de verdad y
        tocarla sería sobrescribir la decisión del docente de desinstalarlo.
        """
        self.fila.formato_contenido = CourseHost.FORMATO_SCORM_12
        self.fila.save(update_fields=["formato_contenido"])

        datos = self.veredicto()
        self.assertTrue(datos["contenido_retirado"])
        self.fila.refresh_from_db()
        self.assertFalse(self.fila.presente_local)

    def test_la_reconciliacion_tambien_lo_sanea(self):
        """El botón «Actualizar» arregla el registro sin abrir el curso."""
        respuesta = self.client.post(
            reverse("contenido-reconciliar"),
            {"host_id": "OPS-1", "actor": "docente-ops"},
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        datos = respuesta.json()
        self.assertEqual(len(datos["presencia_saneada"]), 1)
        self.assertTrue(datos["presencia_saneada"][0]["presente"])
        self.assertTrue(datos["hubo_cambios"])

        self.fila.refresh_from_db()
        self.assertTrue(self.fila.presente_local)

    def test_la_reconciliacion_tambien_marca_la_ausencia(self):
        self.fila.presente_local = True
        self.fila.disponible_estudiante = True
        self.fila.retirado_en = None
        self.fila.save()

        self.componente.retirados.add(self.PAQUETE)
        datos = self.client.post(
            reverse("contenido-reconciliar"),
            {"host_id": "OPS-1"}, content_type="application/json",
        ).json()
        self.assertEqual(len(datos["presencia_saneada"]), 1)
        self.assertFalse(datos["presencia_saneada"][0]["presente"])

        self.fila.refresh_from_db()
        self.assertFalse(self.fila.presente_local)
        # El CHECK exige fecha cuando no está presente.
        self.assertIsNotNone(self.fila.retirado_en)

    def test_sanear_es_idempotente(self):
        self.client.post(reverse("contenido-reconciliar"), {"host_id": "OPS-1"},
                         content_type="application/json")
        segunda = self.client.post(reverse("contenido-reconciliar"), {"host_id": "OPS-1"},
                                   content_type="application/json").json()
        self.assertEqual(segunda["presencia_saneada"], [])

    def test_sin_biblioteca_no_se_sanea_nada(self):
        """Sin catálogo que comparar, la bandera se queda como estaba."""
        self.componente.parar()
        self.assertEqual(
            self.client.post(reverse("contenido-reconciliar"), {"host_id": "OPS-1"},
                             content_type="application/json").status_code, 503)
        self.fila.refresh_from_db()
        self.assertFalse(self.fila.presente_local)


class HuellaDelCatalogoTests(BaseContenido):
    """Con qué se detecta que el catálogo cambió, en orden de preferencia."""

    def test_se_prefiere_la_generacion(self):
        self.componente.capacidades = ["leccion"]   # publica generacion=47
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertEqual(datos["huella_catalogo"], "g47")
        self.assertFalse(datos["generacion_derivada"])

    def test_se_usa_la_huella_que_publica_el_componente(self):
        """
        El componente ya publica `huella_catalogo` en /v1/salud aunque todavía no
        publique `generacion`. Vale igual: cambia cuando cambia el catálogo.
        """
        self.componente.huella = "675d25df86c03a1e"
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertEqual(datos["huella_catalogo"], "h675d25df86c03a1e")

    def test_los_contadores_son_el_ultimo_recurso(self):
        """No detecta un cambio que deje los totales iguales, y por eso es el último."""
        datos = self.client.get(reverse("contenido-estado")).json()
        self.assertTrue(datos["huella_catalogo"].startswith("c"))
        self.assertTrue(datos["generacion_derivada"])
