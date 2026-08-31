"""
Presencia física de un curso en un host, neutral al estándar.

Dos reglas se prueban una y otra vez aquí:
    DESINSTALAR CONTENIDO  ≠  BORRAR ENTIDADES ACADÉMICAS
    SCORM y CMI5 son formatos de ENTRADA, no modelos distintos de curso
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from exams.hosts import (
    HostError,
    courses_for_student,
    mark_verified,
    register_install,
    retire,
    set_availability,
)
from exams.models import (
    AuditLog,
    Course,
    CourseEnrollment,
    CourseHost,
    QuizAttempt,
)
from .factories import make_course, make_course_version

HOST = "OPS-001"
OTRO_HOST = "OPS-002"

SCORM = {
    "formato_contenido": "scorm_2004",
    "manifest_tipo": "imsmanifest",
    "manifest_ref": "imsmanifest.xml",
    "package_identifier": "AVACOM-MAT-001",
}
CMI5 = {
    "formato_contenido": "cmi5",
    "manifest_tipo": "cmi5",
    "manifest_ref": "cmi5.xml",
    "package_identifier": "https://avacom.edu/courses/math-001",
}


class FormatosTests(TestCase):
    """La tabla queda agnóstica: SCORM y CMI5 se distinguen por dos columnas."""

    def setUp(self):
        self.course, _ = make_course(title="Matemáticas 6")

    def test_instalar_un_paquete_scorm(self):
        fila, _ = register_install(HOST, self.course.id, **SCORM)
        self.assertEqual(fila.formato_contenido, "scorm_2004")
        self.assertEqual(fila.manifest_tipo, "imsmanifest")
        self.assertEqual(fila.manifest_ref, "imsmanifest.xml")
        self.assertEqual(fila.package_identifier, "AVACOM-MAT-001")

    def test_instalar_un_paquete_cmi5(self):
        fila, _ = register_install(HOST, self.course.id, **CMI5)
        self.assertEqual(fila.formato_contenido, "cmi5")
        self.assertEqual(fila.manifest_tipo, "cmi5")
        self.assertEqual(fila.manifest_ref, "cmi5.xml")
        self.assertEqual(fila.package_identifier, "https://avacom.edu/courses/math-001")

    def test_el_formato_nativo_es_el_valor_por_omision(self):
        """
        El único formato que el prototipo instala hoy. Sin él en las opciones,
        formato_contenido NOT NULL con CHECK a los tres estándares dejaría fuera
        el camino que ya funciona.
        """
        fila, _ = register_install(HOST, self.course.id)
        self.assertEqual(fila.formato_contenido, "avacom_v1")

    def test_un_formato_desconocido_se_rechaza(self):
        with self.assertRaises(HostError):
            register_install(HOST, self.course.id, formato_contenido="tin_can")

    def test_no_hay_columnas_atadas_a_un_estandar(self):
        columnas = {c.name for c in CourseHost._meta.get_fields()}
        for prohibida in (
            "scorm_manifest_id", "scorm_organization_id", "scorm_version",
            "cmi5_au_id", "cmi5_move_on", "cmi5_mastery_score", "cmi5_launch_method",
        ):
            self.assertNotIn(prohibida, columnas)

    def test_dos_cursos_con_formatos_distintos_conviven(self):
        otro, _ = make_course(title="Ciencias 6")
        register_install(HOST, self.course.id, **SCORM)
        register_install(HOST, otro.id, **CMI5)
        formatos = set(
            CourseHost.objects.filter(host_id=HOST).values_list("formato_contenido", flat=True)
        )
        self.assertEqual(formatos, {"scorm_2004", "cmi5"})


class InstalacionTests(TestCase):
    def setUp(self):
        self.course, self.activity = make_course(title="Matemáticas 6")

    def test_instalar_registra_la_presencia(self):
        fila, creada = register_install(HOST, self.course.id, self.course.version_activa_id)

        self.assertTrue(creada)
        self.assertTrue(fila.presente_local)
        # Recién instalado NO se ofrece a los estudiantes: primero se valida.
        self.assertFalse(fila.disponible_estudiante)
        self.assertEqual(fila.estado_legible, "instalado")
        self.assertIsNone(fila.retirado_en)

    def test_reinstalar_la_misma_version_no_crea_otro_registro(self):
        fila1, creada1 = register_install(HOST, self.course.id, self.course.version_activa_id)
        fila2, creada2 = register_install(HOST, self.course.id, self.course.version_activa_id)

        self.assertTrue(creada1)
        self.assertFalse(creada2)
        self.assertEqual(fila1.pk, fila2.pk)
        self.assertEqual(CourseHost.objects.filter(host_id=HOST, curso=self.course).count(), 1)

    def test_instalar_otra_version_si_crea_una_fila_y_conserva_el_historial(self):
        """
        Lo que gana la clave por (host, curso, versión): antes, instalar V2 sobre
        V1 sobrescribía curso_version_id y se perdía el rastro de V1.
        """
        v1 = self.course.version_activa
        v2 = make_course_version(self.course, version=2, activate=False)

        register_install(HOST, self.course.id, v1.pk)
        register_install(HOST, self.course.id, v2.pk)

        filas = CourseHost.objects.filter(host_id=HOST, curso=self.course)
        self.assertEqual(filas.count(), 2)
        self.assertEqual(
            set(filas.values_list("curso_version_id", flat=True)), {v1.pk, v2.pk}
        )

    def test_sin_version_no_se_puede_registrar_dos_veces(self):
        """
        El hueco de los NULL: un UNIQUE los trata como distintos, así que sin el
        índice parcial ux_m05_ch_sin_version esto crearía dos filas.
        """
        register_install(HOST, self.course.id)
        register_install(HOST, self.course.id)
        self.assertEqual(CourseHost.objects.filter(host_id=HOST, curso=self.course).count(), 1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CourseHost.objects.create(host_id=HOST, curso=self.course, curso_version=None)

    def test_el_mismo_curso_puede_estar_en_dos_hosts(self):
        register_install(HOST, self.course.id)
        register_install(OTRO_HOST, self.course.id)
        self.assertEqual(CourseHost.objects.filter(curso=self.course).count(), 2)

    def test_no_se_puede_instalar_una_version_de_otro_curso(self):
        otro, _ = make_course(title="Ciencias 6")
        with self.assertRaises(HostError):
            register_install(HOST, self.course.id, otro.version_activa_id)

    def test_curso_inexistente_se_rechaza(self):
        with self.assertRaises(HostError):
            register_install(HOST, "no-existe")


class UnaSolaVersionOfrecidaTests(TestCase):
    """
    Con filas por versión aparece un riesgo nuevo: dos versiones del mismo curso
    ofrecidas a la vez, y el estudiante viendo el curso duplicado.
    """

    def setUp(self):
        self.course, _ = make_course(title="Matemáticas 6")
        self.v1 = self.course.version_activa
        self.v2 = make_course_version(self.course, version=2, activate=False)
        register_install(HOST, self.course.id, self.v1.pk)
        register_install(HOST, self.course.id, self.v2.pk)

    def test_abrir_una_version_cierra_la_otra(self):
        set_availability(HOST, self.course.id, True, version_id=self.v1.pk)
        set_availability(HOST, self.course.id, True, version_id=self.v2.pk)

        ofrecidas = CourseHost.objects.filter(
            host_id=HOST, curso=self.course, disponible_estudiante=True
        )
        self.assertEqual(ofrecidas.count(), 1)
        self.assertEqual(ofrecidas.first().curso_version_id, self.v2.pk)

    def test_el_motor_impide_dos_ofrecidas(self):
        set_availability(HOST, self.course.id, True, version_id=self.v1.pk)
        otra = CourseHost.objects.get(host_id=HOST, curso=self.course, curso_version=self.v2)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                otra.disponible_estudiante = True
                otra.save(update_fields=["disponible_estudiante"])

    def test_con_varias_versiones_hay_que_decir_cual(self):
        with self.assertRaises(HostError):
            set_availability(HOST, self.course.id, True)


class DesinstalacionTests(TestCase):
    def setUp(self):
        self.course, self.activity = make_course(title="Matemáticas 6")
        register_install(HOST, self.course.id, self.course.version_activa_id, **SCORM)
        set_availability(HOST, self.course.id, True)
        for persona in ("juan", "pedro", "laura"):
            CourseEnrollment.objects.create(curso=self.course, persona_id=persona)

    def test_desinstalar_no_borra_nada_academico(self):
        cursos_antes = Course.objects.count()
        inscripciones_antes = CourseEnrollment.objects.count()
        intentos_antes = QuizAttempt.objects.count()

        filas, afectadas = retire(HOST, self.course.id)

        self.assertEqual(len(afectadas), 1)
        fila = afectadas[0]
        self.assertFalse(fila.presente_local)
        self.assertFalse(fila.disponible_estudiante)
        self.assertIsNotNone(fila.retirado_en)
        self.assertEqual(fila.estado_legible, "desinstalado")

        self.assertEqual(Course.objects.count(), cursos_antes)
        self.assertEqual(CourseEnrollment.objects.count(), inscripciones_antes)
        self.assertEqual(QuizAttempt.objects.count(), intentos_antes)
        self.assertTrue(CourseHost.objects.filter(pk=fila.pk).exists())
        # El formato del paquete se conserva: sigue sabiéndose qué se instaló.
        self.assertEqual(fila.formato_contenido, "scorm_2004")

    def test_desinstalar_no_toca_el_estado_del_curso(self):
        estado_antes = self.course.estado
        version_antes = self.course.version_activa_id
        retire(HOST, self.course.id)
        self.course.refresh_from_db()
        self.assertEqual(self.course.estado, estado_antes)
        self.assertEqual(self.course.version_activa_id, version_antes)

    def test_desinstalar_sin_version_quita_todas_las_del_host(self):
        v2 = make_course_version(self.course, version=2, activate=False)
        register_install(HOST, self.course.id, v2.pk)

        filas, afectadas = retire(HOST, self.course.id)
        self.assertEqual(len(afectadas), 2, "quitar el curso del host quita sus versiones")
        self.assertEqual(
            CourseHost.objects.filter(
                host_id=HOST, curso=self.course, presente_local=True
            ).count(),
            0,
        )

    def test_desinstalar_una_version_deja_la_otra(self):
        v2 = make_course_version(self.course, version=2, activate=False)
        register_install(HOST, self.course.id, v2.pk)

        filas, afectadas = retire(HOST, self.course.id, version_id=v2.pk)
        self.assertEqual(len(afectadas), 1)
        viva = CourseHost.objects.get(
            host_id=HOST, curso=self.course, curso_version=self.course.version_activa
        )
        self.assertTrue(viva.presente_local)

    def test_desinstalar_en_un_host_no_afecta_al_otro(self):
        register_install(OTRO_HOST, self.course.id, self.course.version_activa_id)
        set_availability(OTRO_HOST, self.course.id, True)
        retire(HOST, self.course.id)

        aqui = CourseHost.objects.get(host_id=HOST, curso=self.course)
        alla = CourseHost.objects.get(host_id=OTRO_HOST, curso=self.course)
        self.assertFalse(aqui.presente_local)
        self.assertTrue(alla.presente_local)
        self.assertTrue(alla.disponible_estudiante)

    def test_desinstalar_dos_veces_es_inofensivo(self):
        retire(HOST, self.course.id)
        filas, afectadas = retire(HOST, self.course.id)
        self.assertEqual(afectadas, [], "repetir la operación no es un error")

    def test_reinstalar_reconoce_el_mismo_curso(self):
        retire(HOST, self.course.id)
        fila, creada = register_install(HOST, self.course.id, self.course.version_activa_id)
        self.assertFalse(creada, "es el mismo curso y la misma versión")
        self.assertTrue(fila.presente_local)
        self.assertIsNone(fila.retirado_en)
        self.assertEqual(CourseEnrollment.objects.filter(curso=self.course).count(), 3)

    def test_desinstalar_un_curso_ausente_del_host_se_rechaza(self):
        with self.assertRaises(HostError):
            retire(OTRO_HOST, self.course.id)


class InvariantesEnElMotorTests(TestCase):
    def setUp(self):
        self.course, _ = make_course(title="Matemáticas 6")

    def test_no_se_puede_ofrecer_lo_que_no_esta_en_el_disco(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CourseHost.objects.create(
                    host_id=HOST, curso=self.course,
                    presente_local=False, disponible_estudiante=True, retirado_en=1,
                )

    def test_si_no_esta_presente_se_sabe_cuando_dejo_de_estarlo(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CourseHost.objects.create(
                    host_id=HOST, curso=self.course,
                    presente_local=False, disponible_estudiante=False, retirado_en=None,
                )

    def test_habilitar_un_curso_ausente_se_rechaza_con_mensaje(self):
        register_install(HOST, self.course.id)
        retire(HOST, self.course.id)
        with self.assertRaises(HostError):
            set_availability(HOST, self.course.id, True)

    def test_borrar_un_curso_con_presencia_registrada_falla(self):
        register_install(HOST, self.course.id)
        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.course.delete()


class VerificacionTests(TestCase):
    def setUp(self):
        self.course, _ = make_course(title="Matemáticas 6")
        register_install(HOST, self.course.id, package_huella="a" * 64, **CMI5)
        set_availability(HOST, self.course.id, True)

    def test_verificar_sella_la_fecha(self):
        fila = mark_verified(HOST, self.course.id, package_huella="a" * 64)
        self.assertIsNotNone(fila.verificado_en)
        self.assertTrue(fila.disponible_estudiante)

    def test_una_huella_distinta_cierra_el_curso(self):
        with self.assertRaises(HostError):
            mark_verified(HOST, self.course.id, package_huella="b" * 64)
        fila = CourseHost.objects.get(host_id=HOST, curso=self.course)
        self.assertFalse(fila.disponible_estudiante)
        self.assertTrue(fila.presente_local, "sigue en el disco, pero no se ofrece")
        self.assertTrue(
            AuditLog.objects.filter(
                objeto_tabla="m05_curso_host", resultado="error"
            ).exists()
        )


class AuditoriaTests(TestCase):
    def test_cada_transicion_queda_registrada(self):
        course, _ = make_course(title="Matemáticas 6")
        register_install(HOST, course.id, actor="docente-demo", **CMI5)
        set_availability(HOST, course.id, True, actor="docente-demo")
        retire(HOST, course.id, actor="docente-demo")

        acciones = list(
            AuditLog.objects.filter(objeto_tabla="m05_curso_host")
            .order_by("secuencia")
            .values_list("accion", flat=True)
        )
        self.assertIn("curso.host.instalado", acciones)
        self.assertIn("curso.host.habilitado", acciones)
        self.assertIn("curso.host.desinstalado", acciones)

    def test_la_auditoria_registra_el_formato(self):
        course, _ = make_course(title="Matemáticas 6")
        register_install(HOST, course.id, **CMI5)
        traza = AuditLog.objects.filter(objeto_tabla="m05_curso_host").first()
        self.assertIn("formato=cmi5", traza.valor_nuevo)


class CatalogoDelEstudianteTests(TestCase):
    def test_un_curso_desinstalado_sigue_apareciendo_con_su_estado(self):
        mates, _ = make_course(title="Matemáticas 6")
        ciencias, _ = make_course(title="Ciencias 6")
        CourseEnrollment.objects.create(curso=mates, persona_id="juan")
        CourseEnrollment.objects.create(curso=ciencias, persona_id="juan")

        register_install(HOST, mates.id, mates.version_activa_id, **SCORM)
        set_availability(HOST, mates.id, True)
        register_install(HOST, ciencias.id, ciencias.version_activa_id, **CMI5)
        set_availability(HOST, ciencias.id, True)
        retire(HOST, ciencias.id)

        filas = {f["titulo"]: f for f in courses_for_student("juan", HOST)}
        self.assertEqual(len(filas), 2, "los dos cursos siguen en la lista")

        self.assertTrue(filas["Matemáticas 6"]["disponible_estudiante"])
        self.assertEqual(filas["Matemáticas 6"]["estado_host"], "disponible")
        self.assertEqual(filas["Matemáticas 6"]["formato_contenido"], "scorm_2004")

        self.assertFalse(filas["Ciencias 6"]["presente_local"])
        self.assertEqual(filas["Ciencias 6"]["estado_host"], "desinstalado")
        self.assertEqual(filas["Ciencias 6"]["matricula"], "activa")
        self.assertEqual(filas["Ciencias 6"]["formato_contenido"], "cmi5")
        self.assertIsNotNone(filas["Ciencias 6"]["retirado_en"])

    def test_con_dos_versiones_se_reporta_la_ofrecida(self):
        curso, _ = make_course(title="Matemáticas 6")
        v1 = curso.version_activa
        v2 = make_course_version(curso, version=2, activate=False)
        CourseEnrollment.objects.create(curso=curso, persona_id="juan")
        register_install(HOST, curso.id, v1.pk)
        register_install(HOST, curso.id, v2.pk)
        set_availability(HOST, curso.id, True, version_id=v2.pk)

        fila = courses_for_student("juan", HOST)[0]
        self.assertEqual(fila["estado_host"], "disponible")
        self.assertEqual(fila["versiones_en_host"], 2)

    def test_un_curso_nunca_instalado_se_reporta_como_tal(self):
        curso, _ = make_course(title="Inglés 6")
        CourseEnrollment.objects.create(curso=curso, persona_id="juan")
        fila = courses_for_student("juan", HOST)[0]
        self.assertEqual(fila["estado_host"], "no instalado")
        self.assertIsNone(fila["formato_contenido"])


class ApiTests(TestCase):
    def setUp(self):
        self.course, _ = make_course(title="Matemáticas 6")

    def test_los_formatos_se_publican(self):
        r = self.client.get(reverse("course-host-formats"))
        self.assertEqual(r.status_code, 200)
        claves = {f["clave"] for f in r.json()}
        self.assertEqual(claves, {"scorm_12", "scorm_2004", "cmi5", "avacom_v1"})
        cmi5 = next(f for f in r.json() if f["clave"] == "cmi5")
        self.assertEqual(cmi5["manifest_ref_habitual"], "cmi5.xml")

    def test_instalar_scorm_y_cmi5_por_http(self):
        otro, _ = make_course(title="Ciencias 6")

        r = self.client.post(
            reverse("course-host-install"),
            {"host_id": HOST, "curso_id": self.course.id, **SCORM},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["host"]["formato_contenido"], "scorm_2004")

        r = self.client.post(
            reverse("course-host-install"),
            {"host_id": HOST, "curso_id": otro.id, **CMI5},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["host"]["formato_contenido"], "cmi5")
        self.assertEqual(r.json()["host"]["formato_legible"], "cmi5")

        r = self.client.get(reverse("course-hosts"), {"formato_contenido": "cmi5"})
        self.assertEqual(len(r.json()), 1)

        r = self.client.get(reverse("host-courses", args=[HOST]))
        self.assertEqual(r.json()["por_formato"], {"scorm_2004": 1, "cmi5": 1})

    def test_un_formato_invalido_da_400(self):
        r = self.client.post(
            reverse("course-host-install"),
            {"host_id": HOST, "curso_id": self.course.id, "formato_contenido": "tin_can"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400, r.content)

    def test_ciclo_completo_por_http(self):
        r = self.client.post(
            reverse("course-host-install"),
            {"host_id": HOST, "curso_id": self.course.id,
             "curso_version_id": self.course.version_activa_id, **CMI5},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        fila_id = r.json()["host"]["id"]

        # reinstalar la misma version -> 200
        r = self.client.post(
            reverse("course-host-install"),
            {"host_id": HOST, "curso_id": self.course.id,
             "curso_version_id": self.course.version_activa_id},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["creada"])

        r = self.client.post(
            reverse("course-host-availability"),
            {"host_id": HOST, "curso_id": self.course.id, "disponible_estudiante": True},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["host"]["disponible_estudiante"])

        r = self.client.get(reverse("course-host-detail", args=[fila_id]))
        self.assertEqual(r.json()["curso_titulo"], "Matemáticas 6")
        self.assertEqual(r.json()["estado_host"], "disponible")

        r = self.client.post(
            reverse("course-host-retire"),
            {"host_id": HOST, "curso_id": self.course.id},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["desinstaladas"], 1)
        self.assertFalse(r.json()["hosts"][0]["presente_local"])

        r = self.client.get(reverse("host-courses", args=[HOST]))
        self.assertEqual(r.json()["desinstalados"], 1)
        self.assertEqual(r.json()["instalados"], 0)

    def test_patch_no_puede_dejar_la_fila_incoherente(self):
        fila, _ = register_install(HOST, self.course.id)
        r = self.client.patch(
            reverse("course-host-detail", args=[fila.pk]),
            {"presente_local": False, "disponible_estudiante": True},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400, r.content)

    def test_patch_no_puede_ofrecer_dos_versiones(self):
        v2 = make_course_version(self.course, version=2, activate=False)
        register_install(HOST, self.course.id, self.course.version_activa_id)
        otra, _ = register_install(HOST, self.course.id, v2.pk)
        set_availability(HOST, self.course.id, True, version_id=self.course.version_activa_id)

        r = self.client.patch(
            reverse("course-host-detail", args=[otra.pk]),
            {"disponible_estudiante": True},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400, r.content)

    def test_catalogo_del_estudiante_exige_host(self):
        r = self.client.get(reverse("student-host-catalog", args=["juan"]))
        self.assertEqual(r.status_code, 400)
        r = self.client.get(
            reverse("student-host-catalog", args=["juan"]), {"host_id": HOST}
        )
        self.assertEqual(r.status_code, 200)

    def test_verificar_con_huella_distinta_responde_409(self):
        register_install(HOST, self.course.id, package_huella="a" * 64)
        r = self.client.post(
            reverse("course-host-verify"),
            {"host_id": HOST, "curso_id": self.course.id, "package_huella": "b" * 64},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 409, r.content)
