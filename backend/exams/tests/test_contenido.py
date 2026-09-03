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

from exams.models import Course, ExamenPregunta, LessonProgress, RepartoActivo, UnidadMaterial
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
