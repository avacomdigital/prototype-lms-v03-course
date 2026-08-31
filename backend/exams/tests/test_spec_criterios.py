"""
Los 12 criterios de aceptación del spec (§22), como pruebas permanentes.

Cada clase se llama por su AC para que un fallo diga inmediatamente qué criterio
se rompió. El escenario completo del §21 vive aparte, en
packages/escenario_spec_21.py, y corre contra la API en marcha; esto son las
pruebas de unidad e integración que protegen los mismos invariantes.
"""

import base64
import io
import os
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from exams.hosts import register_install, retire, set_availability
from exams.models import (
    Course,
    CourseEnrollment,
    CourseHost,
    LessonProgress,
    QuizAttempt,
)
from exams.packages import PackageFormatError, detect_format, read_package, to_course_package
from exams.package_install import install_package
from exams.progress import course_progress, record_lesson_progress, student_courses
from .factories import correct_option, make_course

HOST = "OPS-SPEC-01"
JUAN = "juan"


# ── Constructores de paquetes mínimos ────────────────────────────────────────
IMSMANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="SPEC-MAT6" version="1.0"
          xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3">
  <metadata><schema>ADL SCORM</schema><schemaversion>2004 4th Edition</schemaversion></metadata>
  <organizations default="ORG">
    <organization identifier="ORG">
      <title>Matematicas 6 spec</title>
      <item identifier="SEC1">
        <title>Unidad 1</title>
        <item identifier="LEC1">
          <title>Leccion 1</title>
          <item identifier="I1" identifierref="R1"><title>Lectura</title></item>
        </item>
        <item identifier="LEC2">
          <title>Leccion 2</title>
          <item identifier="I2" identifierref="R2"><title>Video</title></item>
        </item>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="R1" type="webcontent" adlcp:scormType="asset" href="a.html">
      <file href="a.html"/></resource>
    <resource identifier="R2" type="webcontent" adlcp:scormType="asset" href="b.mp4">
      <file href="b.mp4"/></resource>
  </resources>
</manifest>
"""

CMI5_XML = """<?xml version="1.0" encoding="UTF-8"?>
<courseStructure>
  <course id="https://spec.avacom/mat6">
    <title><langstring lang="es">Matematicas 6 spec cmi5</langstring></title>
  </course>
  <block id="https://spec.avacom/b1">
    <title><langstring lang="es">Unidad 1</langstring></title>
    <au id="https://spec.avacom/au1" moveOn="Completed" url="a.html">
      <title><langstring lang="es">Leccion 1</langstring></title></au>
    <au id="https://spec.avacom/au2" moveOn="Passed" masteryScore="0.8" url="b.html">
      <title><langstring lang="es">Leccion 2</langstring></title></au>
  </block>
</courseStructure>
"""


def zip_paquete(descriptor_nombre, descriptor_xml):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, texto in [
            (descriptor_nombre, descriptor_xml),
            ("a.html", "<h1>a</h1>"),
            ("b.mp4", "video"),
            ("b.html", "<h1>b</h1>"),
        ]:
            info = zipfile.ZipInfo(nombre, date_time=(2026, 1, 1, 0, 0, 0))
            zf.writestr(info, texto)
    return buffer.getvalue()


def zip_scorm():
    return zip_paquete("imsmanifest.xml", IMSMANIFEST)


def zip_cmi5():
    return zip_paquete("cmi5.xml", CMI5_XML)


def instalar(datos, host=HOST, course_id="CURSO-SPEC", version=1, titulo="Matematicas 6"):
    """Lee el .zip e instala, como hace el endpoint del §19."""
    from exams.models import CurriculumFramework

    # La base de pruebas arranca vacía: el marco lo crea el seed, no las migraciones.
    CurriculumFramework.objects.get_or_create(
        clave="MEN_CO", defaults={"nombre": "MEN Colombia", "pais": "CO", "orden": 1}
    )
    leido = read_package(datos)
    paquete = to_course_package(leido, course_id, version, activate_after_install=True)
    resumen = install_package(
        paquete, titulo=titulo, curriculum_framework="MEN_CO",
        docente_id="profesor", actor="profesor",
    )
    fila, creada = register_install(
        host, resumen["course_id"], resumen["version_id"],
        formato_contenido=leido["formato_contenido"],
        package_identifier=leido["package_identifier"],
        manifest_tipo=leido["manifest_tipo"],
        manifest_ref=leido["manifest_ref"],
        package_huella=leido["package_huella"],
        actor="profesor",
    )
    set_availability(host, resumen["course_id"], True, version_id=resumen["version_id"])
    return resumen, leido


class AC01Instalacion(TestCase):
    """Un paquete SCORM o CMI5 válido crea o actualiza su presencia en m05_curso_host."""

    def test_scorm_crea_la_presencia(self):
        resumen, leido = instalar(zip_scorm())
        fila = CourseHost.objects.get(host_id=HOST, curso_id=resumen["course_id"])
        self.assertEqual(fila.formato_contenido, "scorm_2004")
        self.assertEqual(fila.package_identifier, "SPEC-MAT6")
        self.assertTrue(fila.presente_local)

    def test_cmi5_crea_la_presencia(self):
        resumen, leido = instalar(zip_cmi5(), course_id="CURSO-SPEC-CMI5")
        fila = CourseHost.objects.get(host_id=HOST, curso_id=resumen["course_id"])
        self.assertEqual(fila.formato_contenido, "cmi5")
        self.assertEqual(fila.manifest_tipo, "cmi5")

    def test_un_zip_que_no_es_paquete_se_rechaza(self):
        basura = zip_paquete("cualquiera.txt", "hola")
        with self.assertRaises(PackageFormatError):
            read_package(basura)

    def test_el_formato_se_detecta_del_descriptor(self):
        self.assertEqual(detect_format(zip_scorm())[0], "scorm_2004")
        self.assertEqual(detect_format(zip_cmi5())[0], "cmi5")

    def test_la_estructura_llega_al_arbol_de_avacom(self):
        """SCORM y CMI5 producen el MISMO árbol: es el punto del §24."""
        resumen, _ = instalar(zip_scorm())
        self.assertEqual(resumen["totales_version"]["secciones"], 1)
        self.assertEqual(resumen["totales_version"]["lecciones"], 2)


class AC02Disponibilidad(TestCase):
    def setUp(self):
        self.resumen, _ = instalar(zip_scorm())
        self.course_id = self.resumen["course_id"]

    def test_solo_se_abre_con_las_dos_banderas(self):
        r = self.client.get(reverse("courses-available"), {"host_id": HOST})
        self.assertEqual(len(r.json()["courses"]), 1)

        # Cerrar solo la disponibilidad: sigue instalado pero no se puede abrir.
        set_availability(HOST, self.course_id, False)
        r = self.client.get(reverse("courses-available"), {"host_id": HOST})
        self.assertEqual(len(r.json()["courses"]), 0)
        fila = CourseHost.objects.get(host_id=HOST, curso_id=self.course_id)
        self.assertTrue(fila.presente_local, "sigue en el disco")

    def test_available_sin_host_responde_por_esta_OPS(self):
        """
        Antes exigía ?host_id= y devolvía 400. Ahora la OPS conoce su identidad,
        así que el endpoint sirve para comprobar de un vistazo qué ve la tableta.
        """
        from django.test import override_settings

        with override_settings(AVACOM_HOST_ID=HOST):
            r = self.client.get(reverse("courses-available"))
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json()["host_id"], HOST)
            self.assertEqual(
                [c["course_id"] for c in r.json()["courses"]], [self.course_id]
            )

        # El parámetro sigue sirviendo para preguntar por otra sede.
        with override_settings(AVACOM_HOST_ID=HOST):
            r = self.client.get(reverse("courses-available"), {"host_id": "OTRA-OPS"})
            self.assertEqual(r.json()["courses"], [])


class AC03a06Desinstalacion(TestCase):
    """AC-03 desinstalación · AC-04 matrícula · AC-05 progreso · AC-06 notas."""

    def setUp(self):
        self.resumen, _ = instalar(zip_scorm())
        self.course_id = self.resumen["course_id"]
        CourseEnrollment.objects.create(curso_id=self.course_id, persona_id=JUAN)
        avance = course_progress(self.course_id, JUAN)
        self.codigos = [d["leccion_codigo"] for d in avance["detalle"]]
        record_lesson_progress(self.course_id, JUAN, self.codigos[0], 100)
        record_lesson_progress(self.course_id, JUAN, self.codigos[1], 50)
        self.antes = course_progress(self.course_id, JUAN)["porcentaje"]

    def test_ac03_presente_local_pasa_a_cero(self):
        retire(HOST, self.course_id)
        fila = CourseHost.objects.get(host_id=HOST, curso_id=self.course_id)
        self.assertFalse(fila.presente_local)
        self.assertFalse(fila.disponible_estudiante)
        self.assertIsNotNone(fila.retirado_en)

    def test_ac04_la_matricula_sobrevive(self):
        antes = CourseEnrollment.objects.filter(curso_id=self.course_id).count()
        retire(HOST, self.course_id)
        self.assertEqual(CourseEnrollment.objects.filter(curso_id=self.course_id).count(), antes)

    def test_ac05_el_progreso_sobrevive_exacto(self):
        retire(HOST, self.course_id)
        self.assertEqual(course_progress(self.course_id, JUAN)["porcentaje"], self.antes)

    def test_ac06_las_filas_de_progreso_no_se_tocan(self):
        antes = LessonProgress.objects.filter(curso_id=self.course_id).count()
        retire(HOST, self.course_id)
        self.assertEqual(LessonProgress.objects.filter(curso_id=self.course_id).count(), antes)

    def test_el_curso_no_se_borra_ni_cambia_de_estado(self):
        curso = Course.objects.get(pk=self.course_id)
        estado = curso.estado
        retire(HOST, self.course_id)
        curso.refresh_from_db()
        self.assertEqual(curso.estado, estado)

    def test_el_endpoint_de_uninstall_reporta_lo_conservado(self):
        r = self.client.post(
            reverse("course-uninstall", args=[self.course_id]),
            {"host_id": HOST}, content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["preserved"]["intact"])
        self.assertEqual(r.json()["uninstalled_versions"], 1)

    def test_no_existe_delete_de_curso_en_la_api_del_spec(self):
        """§19: «No debe hacer DELETE /api/courses/{id}/»."""
        from django.urls import get_resolver

        nombres = {
            v.name for v in get_resolver().url_patterns
            for v in getattr(v, "url_patterns", [v])
            if getattr(v, "name", None)
        }
        self.assertIn("course-uninstall", nombres)


class AC07y08OcultamientoEHistorial(TestCase):
    def setUp(self):
        self.resumen, _ = instalar(zip_scorm())
        self.course_id = self.resumen["course_id"]
        CourseEnrollment.objects.create(curso_id=self.course_id, persona_id=JUAN)
        avance = course_progress(self.course_id, JUAN)
        record_lesson_progress(
            self.course_id, JUAN, avance["detalle"][0]["leccion_codigo"], 100
        )
        retire(HOST, self.course_id)

    def test_ac07_no_aparece_en_disponibles(self):
        r = self.client.get(reverse("courses-available"), {"host_id": HOST})
        ids = [c["course_id"] for c in r.json()["courses"]]
        self.assertNotIn(self.course_id, ids)

    def test_ac08_si_aparece_en_el_historial(self):
        r = self.client.get(reverse("courses-history"), {"host_id": HOST})
        fila = next(c for c in r.json()["courses"] if c["course_id"] == self.course_id)
        self.assertFalse(fila["installed"])
        self.assertEqual(fila["host_state"], "desinstalado")
        self.assertEqual(fila["students"], 1)
        self.assertEqual(fila["students_with_progress"], 1)

    def test_el_estudiante_lo_ve_como_no_disponible(self):
        r = self.client.get(
            reverse("student-courses", args=[JUAN]), {"host_id": HOST}
        )
        cuerpo = r.json()
        self.assertEqual(len(cuerpo["unavailable"]), 1)
        curso = cuerpo["unavailable"][0]
        self.assertGreater(curso["progress"], 0)
        self.assertFalse(curso["installed"])
        self.assertFalse(curso["available"])


class AC09y10Reinstalacion(TestCase):
    """AC-09 recupera la relación histórica · AC-10 no duplica nada."""

    def setUp(self):
        self.datos = zip_scorm()
        self.resumen, _ = instalar(self.datos)
        self.course_id = self.resumen["course_id"]
        CourseEnrollment.objects.create(curso_id=self.course_id, persona_id=JUAN)
        avance = course_progress(self.course_id, JUAN)
        record_lesson_progress(
            self.course_id, JUAN, avance["detalle"][0]["leccion_codigo"], 100
        )
        record_lesson_progress(
            self.course_id, JUAN, avance["detalle"][1]["leccion_codigo"], 50
        )
        self.antes = course_progress(self.course_id, JUAN)["porcentaje"]
        retire(HOST, self.course_id)

    def test_ac09_al_reinstalar_vuelve_el_progreso(self):
        instalar(self.datos, course_id=self.course_id)
        self.assertEqual(course_progress(self.course_id, JUAN)["porcentaje"], self.antes)
        fila = CourseHost.objects.get(host_id=HOST, curso_id=self.course_id)
        self.assertTrue(fila.presente_local)
        self.assertTrue(fila.disponible_estudiante)
        self.assertIsNone(fila.retirado_en)

    def test_ac10_no_duplica_curso_matricula_ni_progreso(self):
        cursos = Course.objects.count()
        matriculas = CourseEnrollment.objects.count()
        progreso = LessonProgress.objects.count()
        hosts = CourseHost.objects.count()

        instalar(self.datos, course_id=self.course_id)

        self.assertEqual(Course.objects.count(), cursos)
        self.assertEqual(CourseEnrollment.objects.count(), matriculas)
        self.assertEqual(LessonProgress.objects.count(), progreso)
        self.assertEqual(CourseHost.objects.count(), hosts)

    def test_reinstalar_es_idempotente_en_el_instalador(self):
        leido = read_package(self.datos)
        paquete = to_course_package(leido, self.course_id, 1)
        resumen = install_package(paquete, titulo="Matematicas 6")
        self.assertTrue(resumen["idempotente"])
        self.assertEqual(resumen["creados"]["items"], 0)


class AC11IndependenciaDeFormato(TestCase):
    """La lógica de m05_curso_host no cambia entre SCORM y CMI5."""

    def test_el_ciclo_completo_es_identico_en_los_dos_formatos(self):
        resultados = {}
        for etiqueta, datos, cid in [
            ("scorm", zip_scorm(), "CURSO-AC11-SCORM"),
            ("cmi5", zip_cmi5(), "CURSO-AC11-CMI5"),
        ]:
            resumen, leido = instalar(datos, course_id=cid, titulo=f"Curso {etiqueta}")
            course_id = resumen["course_id"]
            CourseEnrollment.objects.create(curso_id=course_id, persona_id=JUAN)
            avance = course_progress(course_id, JUAN)
            record_lesson_progress(course_id, JUAN, avance["detalle"][0]["leccion_codigo"], 100)
            antes = course_progress(course_id, JUAN)["porcentaje"]

            retire(HOST, course_id)
            tras_retiro = course_progress(course_id, JUAN)["porcentaje"]
            fila_retirada = CourseHost.objects.get(host_id=HOST, curso_id=course_id)

            instalar(datos, course_id=course_id, titulo=f"Curso {etiqueta}")
            tras_reinstalar = course_progress(course_id, JUAN)["porcentaje"]
            fila_viva = CourseHost.objects.get(host_id=HOST, curso_id=course_id)

            resultados[etiqueta] = {
                "formato": leido["formato_contenido"],
                "progreso": (antes, tras_retiro, tras_reinstalar),
                "banderas_retirado": (fila_retirada.presente_local, fila_retirada.disponible_estudiante),
                "banderas_vivo": (fila_viva.presente_local, fila_viva.disponible_estudiante),
            }

        # Los formatos son distintos...
        self.assertNotEqual(resultados["scorm"]["formato"], resultados["cmi5"]["formato"])
        # ...pero el comportamiento es idéntico.
        self.assertEqual(resultados["scorm"]["progreso"], resultados["cmi5"]["progreso"])
        self.assertEqual(
            resultados["scorm"]["banderas_retirado"], resultados["cmi5"]["banderas_retirado"]
        )
        self.assertEqual(resultados["scorm"]["banderas_vivo"], resultados["cmi5"]["banderas_vivo"])
        self.assertEqual(resultados["scorm"]["banderas_retirado"], (False, False))
        self.assertEqual(resultados["scorm"]["banderas_vivo"], (True, True))


class AC12SinInternet(TestCase):
    """
    El flujo no toca la red. La prueba lo comprueba de la única forma honesta:
    rompiendo las sockets salientes durante la instalación completa.
    """

    def test_instalar_usar_y_desinstalar_sin_red(self):
        import socket

        original = socket.socket

        class SocketProhibido(original):
            def connect(self, *args, **kwargs):
                raise AssertionError(
                    "El flujo intentó abrir una conexión de red. Debe funcionar offline."
                )

        socket.socket = SocketProhibido
        try:
            resumen, _ = instalar(zip_scorm(), course_id="CURSO-OFFLINE")
            course_id = resumen["course_id"]
            CourseEnrollment.objects.create(curso_id=course_id, persona_id=JUAN)
            avance = course_progress(course_id, JUAN)
            record_lesson_progress(course_id, JUAN, avance["detalle"][0]["leccion_codigo"], 100)
            retire(HOST, course_id)
            instalar(zip_scorm(), course_id=course_id)
            self.assertEqual(course_progress(course_id, JUAN)["porcentaje"], 50.0)
        finally:
            socket.socket = original


class ProgresoTests(TestCase):
    """El cálculo del progreso y la razón de indexarlo por código lógico."""

    def setUp(self):
        self.resumen, _ = instalar(zip_scorm())
        self.course_id = self.resumen["course_id"]

    def test_el_progreso_no_baja_solo(self):
        avance = course_progress(self.course_id, JUAN)
        codigo = avance["detalle"][0]["leccion_codigo"]
        record_lesson_progress(self.course_id, JUAN, codigo, 80)
        fila, cambio = record_lesson_progress(self.course_id, JUAN, codigo, 30)
        self.assertFalse(cambio, "un estado viejo que llega tarde no debe borrar avance")
        self.assertEqual(float(fila.porcentaje), 80.0)

    def test_completar_sella_la_fecha(self):
        avance = course_progress(self.course_id, JUAN)
        fila, _ = record_lesson_progress(
            self.course_id, JUAN, avance["detalle"][0]["leccion_codigo"], 100
        )
        self.assertEqual(fila.estado, LessonProgress.ESTADO_COMPLETADA)
        self.assertIsNotNone(fila.completado_en)

    def test_un_porcentaje_fuera_de_rango_se_rechaza(self):
        from exams.progress import ProgressError

        with self.assertRaises(ProgressError):
            record_lesson_progress(self.course_id, JUAN, "lesson.x", 140)

    def test_el_progreso_se_indexa_por_codigo_no_por_fila_fisica(self):
        """
        Es la decisión que hace que sobreviva a un cambio de versión: la V2 tiene
        filas m05_leccion nuevas, pero el mismo `codigo`.
        """
        avance = course_progress(self.course_id, JUAN)
        codigo = avance["detalle"][0]["leccion_codigo"]
        record_lesson_progress(self.course_id, JUAN, codigo, 100)

        fila = LessonProgress.objects.get(curso_id=self.course_id, persona_id=JUAN)
        campos = {f.name for f in LessonProgress._meta.get_fields()}
        self.assertIn("leccion_codigo", campos)
        self.assertNotIn("leccion", campos, "no debe apuntar a la fila física")
        self.assertEqual(fila.leccion_codigo, codigo)

    def test_la_nota_del_quiz_alimenta_el_progreso(self):
        """El puntaje del intento se convierte en el avance de su lección."""
        curso, actividad = make_course(title="Con quiz", questions=4)
        from exams.models import Lesson

        leccion = Lesson.objects.get(seccion__curso_version=curso.version_activa)

        r = self.client.post(
            reverse("quiz-start"),
            {"actividad_id": actividad.id, "nombre_estudiante": "Juan",
             "persona_id": JUAN, "device_id": "t1"},
            content_type="application/json",
        )
        intento = r.json()["id"]
        preguntas = list(actividad.preguntas.order_by("orden"))
        for pregunta in preguntas[:3]:
            self.client.post(
                reverse("quiz-answer"),
                {"intento_id": intento, "pregunta_id": pregunta.id,
                 "opcion_id": correct_option(pregunta).id},
                content_type="application/json",
            )
        self.client.post(
            reverse("quiz-finish"), {"intento_id": intento}, content_type="application/json"
        )

        avance = course_progress(curso.id, JUAN)
        fila = next(d for d in avance["detalle"] if d["leccion_codigo"] == leccion.codigo)
        self.assertEqual(fila["porcentaje"], 75.0, "3 de 4 correctas")
        self.assertIsNotNone(fila["nota"])
        self.assertEqual(
            QuizAttempt.objects.get(pk=intento).estado, QuizAttempt.ESTADO_FINALIZADO
        )

    def test_student_courses_tiene_la_forma_del_spec(self):
        CourseEnrollment.objects.create(curso_id=self.course_id, persona_id=JUAN)
        filas = student_courses(JUAN, HOST)
        self.assertEqual(len(filas), 1)
        for clave in ("course_id", "name", "progress", "installed", "available"):
            self.assertIn(clave, filas[0])
        self.assertTrue(0 <= filas[0]["progress"] <= 1, "progress es una fracción")


class TransporteDelZipTests(TestCase):
    """
    La vista, no las funciones: cómo entra el .zip por HTTP.

    Las pruebas de arriba llaman a read_package e install_package en directo, así
    que pasaban aun cuando POST /api/course-packages/install/ rechazaba el
    multipart con 415 (DEFAULT_PARSER_CLASSES es JSONParser a secas y la vista no
    declaraba los suyos). El Master sube el archivo por multipart —un SCORM real
    pesa megas y base64 le agrega un tercio—, así que ese camino necesita su
    propia prueba.
    """

    def setUp(self):
        from exams.models import CurriculumFramework

        # La base de pruebas arranca vacía: el marco lo crea el seed, no las
        # migraciones. Por HTTP el docente lo elige, así que hay que sembrarlo.
        CurriculumFramework.objects.get_or_create(
            clave="MEN_CO", defaults={"nombre": "MEN Colombia", "pais": "CO", "orden": 1}
        )
        self.url = reverse("package-zip-install")

    def test_multipart_es_el_camino_del_master(self):
        archivo = SimpleUploadedFile(
            "matematicas6.zip", zip_scorm(), content_type="application/zip"
        )
        respuesta = self.client.post(f"{self.url}?preview=1", {"package": archivo})

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        detectado = respuesta.json()["detected"]
        self.assertEqual(detectado["content_format"], "scorm_2004")
        self.assertEqual(detectado["manifest_type"], "imsmanifest")
        self.assertEqual(detectado["package_name"], "matematicas6.zip")

    def test_multipart_instala_y_registra_la_presencia(self):
        archivo = SimpleUploadedFile(
            "matematicas6.zip", zip_scorm(), content_type="application/zip"
        )
        respuesta = self.client.post(self.url, {
            "package": archivo,
            "host_id": HOST,
            "titulo": "Matematicas 6 por multipart",
            "curriculum_framework": "MEN_CO",
            "actor": "docente-ops",
        })

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        fila = respuesta.json()["host"]
        self.assertEqual(fila["host_id"], HOST)
        self.assertEqual(fila["formato_contenido"], "scorm_2004")
        self.assertTrue(fila["presente_local"])
        self.assertTrue(fila["disponible_estudiante"])
        self.assertEqual(
            Course.objects.get(pk=fila["curso"]).titulo, "Matematicas 6 por multipart"
        )

    def test_cmi5_por_multipart_llega_como_cmi5(self):
        archivo = SimpleUploadedFile(
            "matematicas6_cmi5.zip", zip_cmi5(), content_type="application/zip"
        )
        respuesta = self.client.post(self.url, {
            "package": archivo,
            "host_id": HOST,
            "titulo": "Matematicas 6 CMI5",
            "curriculum_framework": "MEN_CO",
        })

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertEqual(respuesta.json()["host"]["formato_contenido"], "cmi5")

    def test_base64_sigue_sirviendo(self):
        """El camino JSON no se rompe al aceptar multipart: conviven."""
        respuesta = self.client.post(
            self.url,
            {
                "package_base64": base64.b64encode(zip_scorm()).decode(),
                "package_name": "matematicas6.zip",
                "host_id": HOST,
                "titulo": "Matematicas 6 por base64",
                "curriculum_framework": "MEN_CO",
            },
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertEqual(respuesta.json()["host"]["formato_contenido"], "scorm_2004")

    def test_un_zip_roto_se_rechaza_con_400(self):
        archivo = SimpleUploadedFile("roto.zip", b"", content_type="application/zip")
        respuesta = self.client.post(f"{self.url}?preview=1", {"package": archivo})
        self.assertEqual(respuesta.status_code, 400)

    def test_instalar_sin_host_id_se_rechaza(self):
        """Instalar es registrar presencia EN una OPS: sin host_id no hay dónde."""
        archivo = SimpleUploadedFile("m.zip", zip_scorm(), content_type="application/zip")
        respuesta = self.client.post(self.url, {"package": archivo, "titulo": "x"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(CourseHost.objects.count(), 0)


class EliminarCursoTests(TestCase):
    """
    La pantalla «Eliminar curso» del OPS Master.

    Cubre el listado que alimenta las tarjetas y el ciclo completo del escenario
    de demostración: instalar, avanzar, eliminar, comprobar que el estudiante ya
    no lo ve, y reimportar para que reaparezca con su progreso.
    """

    def setUp(self):
        self.instalado_url = reverse("host-installed", args=[HOST])

    def tarjetas(self, host=HOST):
        respuesta = self.client.get(reverse("host-installed", args=[host]))
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return respuesta.json()

    # ── el listado que dibuja las tarjetas ───────────────────────────────────
    def test_una_tarjeta_por_curso_no_una_por_fila(self):
        """m05_curso_host lleva una fila por versión; la pantalla razona por curso."""
        resumen, leido = instalar(zip_scorm(), course_id="CURSO-UNA")
        # Segunda versión del mismo curso: dos filas, un solo curso.
        paquete = to_course_package(leido, "CURSO-UNA", 2, activate_after_install=True)
        segunda = install_package(
            paquete, titulo="Matematicas 6", curriculum_framework="MEN_CO",
            docente_id="profesor", actor="profesor",
        )
        register_install(
            HOST, "CURSO-UNA", segunda["version_id"],
            formato_contenido=leido["formato_contenido"],
            package_identifier=leido["package_identifier"],
            actor="profesor",
        )
        self.assertEqual(
            CourseHost.objects.filter(host_id=HOST, curso_id="CURSO-UNA").count(), 2
        )

        datos = self.tarjetas()
        self.assertEqual(datos["cursos"], 1)
        self.assertEqual(len(datos["courses"]), 1)
        # La tarjeta muestra la versión más alta, que es la que ve el estudiante.
        self.assertEqual(datos["courses"][0]["version"], 2)

    def test_solo_lista_lo_presente(self):
        instalar(zip_scorm(), course_id="CURSO-PRESENTE")
        self.assertEqual(self.tarjetas()["cursos"], 1)

        retire(HOST, "CURSO-PRESENTE", actor="profesor")
        self.assertEqual(self.tarjetas()["cursos"], 0)

    def test_la_tarjeta_dice_cuanto_se_conservaria(self):
        """Sin estos números la advertencia sería una promesa y no un dato."""
        instalar(zip_scorm(), course_id="CURSO-CUENTAS")
        CourseEnrollment.objects.create(
            curso_id="CURSO-CUENTAS", persona_id=JUAN, estado="activa", creado_por="profesor"
        )
        record_lesson_progress("CURSO-CUENTAS", JUAN, "lec-1", 100, actor=JUAN)
        record_lesson_progress("CURSO-CUENTAS", JUAN, "lec-2", 40, actor=JUAN)

        tarjeta = self.tarjetas()["courses"][0]
        self.assertEqual(tarjeta["preserved"]["students"], 1)
        self.assertEqual(tarjeta["preserved"]["progress_rows"], 2)

    def test_un_host_no_ve_lo_del_otro(self):
        instalar(zip_scorm(), host="OPS-A", course_id="CURSO-AJENO")
        self.assertEqual(self.tarjetas("OPS-A")["cursos"], 1)
        self.assertEqual(self.tarjetas("OPS-B")["cursos"], 0)

    # ── el escenario de demostración, de punta a punta ───────────────────────
    def test_eliminar_conserva_el_progreso_y_reimportar_lo_devuelve(self):
        # Paso 1 · un curso importado, con un estudiante que ya avanzó
        instalar(zip_scorm(), course_id="CURSO-DEMO")
        CourseEnrollment.objects.create(
            curso_id="CURSO-DEMO", persona_id=JUAN, estado="activa", creado_por="profesor"
        )
        record_lesson_progress("CURSO-DEMO", JUAN, "lec-1", 100, actor=JUAN)
        record_lesson_progress("CURSO-DEMO", JUAN, "lec-2", 50, actor=JUAN)
        antes = course_progress("CURSO-DEMO", JUAN)["porcentaje"]

        # Paso 2 y 3 · la pantalla lo lista y la tarjeta trae lo que se conserva
        tarjeta = self.tarjetas()["courses"][0]
        self.assertEqual(tarjeta["course_id"], "CURSO-DEMO")
        self.assertTrue(tarjeta["available"])
        self.assertEqual(tarjeta["preserved"]["progress_rows"], 2)

        # Paso 4 y 5 · confirmar: se retira y el backend prueba lo conservado
        respuesta = self.client.post(
            reverse("course-uninstall", args=["CURSO-DEMO"]),
            {"host_id": HOST, "actor": "docente-ops"},
            content_type="application/json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertTrue(cuerpo["preserved"]["intact"])
        self.assertTrue(all(not f["presente_local"] for f in cuerpo["hosts"]))
        self.assertTrue(all(not f["disponible_estudiante"] for f in cuerpo["hosts"]))

        # Ya no está en las tarjetas
        self.assertEqual(self.tarjetas()["cursos"], 0)

        # Paso 6 · el estudiante ya no puede abrirlo, pero SIGUE viéndolo con su avance
        disponibles = self.client.get(reverse("courses-available"), {"host_id": HOST}).json()
        self.assertNotIn(
            "CURSO-DEMO", [c["course_id"] for c in disponibles.get("courses", disponibles)]
        )

        mios = self.client.get(reverse("student-courses", args=[JUAN]), {"host_id": HOST}).json()
        suyo = next(c for c in mios["courses"] if c["course_id"] == "CURSO-DEMO")
        self.assertFalse(suyo["installed"])
        self.assertFalse(suyo["available"])
        self.assertEqual(suyo["progress_pct"], antes)

        # Paso 7 · reimportar: vuelve a estar disponible y el progreso reaparece
        instalar(zip_scorm(), course_id="CURSO-DEMO")
        tarjeta = self.tarjetas()["courses"][0]
        self.assertEqual(tarjeta["course_id"], "CURSO-DEMO")
        self.assertTrue(tarjeta["available"])

        despues = course_progress("CURSO-DEMO", JUAN)["porcentaje"]
        self.assertEqual(despues, antes)
        self.assertEqual(
            LessonProgress.objects.filter(curso_id="CURSO-DEMO", persona_id=JUAN).count(), 2
        )

    def test_eliminar_dos_veces_no_revienta(self):
        """Un segundo clic sobre algo ya retirado no debe romper la pantalla."""
        instalar(zip_scorm(), course_id="CURSO-DOSVECES")
        url = reverse("course-uninstall", args=["CURSO-DOSVECES"])
        primera = self.client.post(url, {"host_id": HOST}, content_type="application/json")
        self.assertEqual(primera.status_code, 200, primera.content)

        segunda = self.client.post(url, {"host_id": HOST}, content_type="application/json")
        self.assertIn(segunda.status_code, (200, 400), segunda.content)
        self.assertEqual(
            LessonProgress.objects.filter(curso_id="CURSO-DOSVECES").count(), 0
        )


class CatalogoDelEstudianteTests(TestCase):
    """
    Lo que la tableta ve en /api/courses/?student=1.

    Es el paso 6 del escenario: al eliminar el curso en el Master, el estudiante
    debe dejar de poder abrirlo. Antes esta vista filtraba solo por
    m05_curso.estado —que desinstalar no toca a propósito—, así que el curso
    eliminado seguía apareciendo en el Student.
    """

    def catalogo(self, host=HOST):
        respuesta = self.client.get(reverse("courses"), {"student": "1", "host_id": host})
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return [c["id"] for c in respuesta.json()]

    def test_un_curso_instalado_y_habilitado_se_ve(self):
        instalar(zip_scorm(), course_id="CURSO-VISIBLE")
        self.assertIn("CURSO-VISIBLE", self.catalogo())

    def test_al_eliminarlo_desaparece_del_catalogo(self):
        instalar(zip_scorm(), course_id="CURSO-SEVA")
        self.assertIn("CURSO-SEVA", self.catalogo())

        retire(HOST, "CURSO-SEVA", actor="docente-ops")
        self.assertNotIn("CURSO-SEVA", self.catalogo())

    def test_al_reimportarlo_vuelve_a_verse(self):
        instalar(zip_scorm(), course_id="CURSO-VUELVE")
        retire(HOST, "CURSO-VUELVE", actor="docente-ops")
        self.assertNotIn("CURSO-VUELVE", self.catalogo())

        instalar(zip_scorm(), course_id="CURSO-VUELVE")
        self.assertIn("CURSO-VUELVE", self.catalogo())

    def test_instalado_pero_sin_habilitar_no_se_ve(self):
        """Las dos banderas son independientes: presente no es lo mismo que abierto."""
        instalar(zip_scorm(), course_id="CURSO-CERRADO")
        set_availability(HOST, "CURSO-CERRADO", False, actor="docente-ops")
        self.assertNotIn("CURSO-CERRADO", self.catalogo())

    def test_un_curso_hecho_a_mano_sigue_visible(self):
        """
        La no-regresión que importa: los cursos creados en el asistente del Master
        no tienen fila en m05_curso_host. Filtrarlos por presencia los borraría de
        la tableta sin que nadie los haya eliminado.
        """
        curso, _ = make_course(title="Álgebra a mano")
        self.assertEqual(CourseHost.objects.filter(curso=curso).count(), 0)
        self.assertIn(curso.pk, self.catalogo())

        # Y sigue visible aunque OTRO curso sí tenga presencia y se elimine.
        instalar(zip_scorm(), course_id="CURSO-IMPORTADO")
        retire(HOST, "CURSO-IMPORTADO", actor="docente-ops")
        catalogo = self.catalogo()
        self.assertIn(curso.pk, catalogo)
        self.assertNotIn("CURSO-IMPORTADO", catalogo)

    def test_la_presencia_es_por_OPS(self):
        """Eliminarlo en una sede no lo quita de la otra."""
        instalar(zip_scorm(), host="OPS-A", course_id="CURSO-DOSSEDES")
        register_install(
            "OPS-B", "CURSO-DOSSEDES", None,
            formato_contenido="scorm_2004", package_identifier="SPEC-MAT6", actor="profesor",
        )
        set_availability("OPS-B", "CURSO-DOSSEDES", True, actor="profesor")

        self.assertIn("CURSO-DOSSEDES", self.catalogo("OPS-A"))
        self.assertIn("CURSO-DOSSEDES", self.catalogo("OPS-B"))

        retire("OPS-A", "CURSO-DOSSEDES", actor="profesor")
        self.assertNotIn("CURSO-DOSSEDES", self.catalogo("OPS-A"))
        self.assertIn("CURSO-DOSSEDES", self.catalogo("OPS-B"))

    def test_sin_host_id_usa_la_identidad_de_esta_OPS(self):
        from django.test import override_settings

        instalar(zip_scorm(), host="OPS-CONFIGURADA", course_id="CURSO-PROPIO")
        with override_settings(AVACOM_HOST_ID="OPS-CONFIGURADA"):
            respuesta = self.client.get(reverse("courses"), {"student": "1"})
            self.assertIn("CURSO-PROPIO", [c["id"] for c in respuesta.json()])
