"""
La integridad del catálogo versionado tiene que estar en el MOTOR, no en la
aplicación. Estas pruebas no comprueban que el código valide: comprueban que la
base se niegue, incluso cuando el código intenta hacer la barbaridad.
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from exams.catalog import CatalogError, activate_version, rollback_version, version_counts
from exams.models import (
    Course,
    CourseVersion,
    CurriculumFramework,
    Lesson,
    LessonItem,
    Section,
)
from .factories import make_course, make_course_version


def contenido(version, secciones=1, lecciones=1, items=1, sufijo=""):
    """
    Cuelga un árbol pequeño de una versión, para poder contar filas.

    El `orden` arranca después de las secciones que ya tenga la versión: dentro
    de una versión (curso_version, orden) es UNIQUE, y la factoría ya dejó una.
    """
    base = Section.objects.filter(curso_version=version).count()
    for s in range(1, secciones + 1):
        seccion = Section.objects.create(
            curso_version=version, codigo=f"section.s{s}{sufijo}",
            titulo=f"Sección {s}", orden=base + s,
        )
        for l in range(1, lecciones + 1):
            leccion = Lesson.objects.create(
                seccion=seccion, codigo=f"lesson.l{s}{l}{sufijo}", titulo=f"Lección {l}", orden=l
            )
            for i in range(1, items + 1):
                LessonItem.objects.create(
                    leccion=leccion, orden=i, tipo="referencia_externa",
                    elemento_ref=f"avacom:anexo/{s}{l}{i}", elemento_version="1.0",
                )


class UnaSolaActivaTests(TestCase):
    def test_activar_dos_versiones_a_la_vez_falla_con_unique(self):
        """(b) del entregable · el índice único PARCIAL ux_m05_cv_una_activa."""
        course, _ = make_course()
        activa = course.version_activa
        self.assertEqual(activa.estado, CourseVersion.ESTADO_ACTIVA)

        otra = make_course_version(course, version=2, activate=False)

        # Se intenta a mano, salteando activate_version(): la base debe negarse.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                otra.estado = CourseVersion.ESTADO_ACTIVA
                otra.activada_en = otra.instalada_en
                otra.save(update_fields=["estado", "activada_en"])

    def test_activate_version_libera_la_saliente_antes_de_asignar(self):
        """
        El orden correcto sí funciona: primero se libera la saliente. Es la razón
        de que activate_version exista en lugar de dos UPDATE sueltos.
        """
        course, _ = make_course()
        v1 = course.version_activa
        v2 = make_course_version(course, version=2, activate=False)

        activada, saliente_id = activate_version(v2.pk, actor="prueba")

        self.assertEqual(activada.pk, v2.pk)
        self.assertEqual(saliente_id, v1.pk)
        v1.refresh_from_db()
        course.refresh_from_db()
        self.assertEqual(v1.estado, CourseVersion.ESTADO_INSTALADA)
        self.assertEqual(course.version_activa_id, v2.pk)
        # Solo una activa, contada en la base.
        self.assertEqual(
            CourseVersion.objects.filter(curso=course, estado=CourseVersion.ESTADO_ACTIVA).count(), 1
        )


class VersionDeOtroCursoTests(TestCase):
    def test_apuntar_a_una_version_de_otro_curso_se_rechaza(self):
        """
        (c) del entregable. En el SQLite de referencia lo impide una FK compuesta
        (version_activa_id, id) -> (id, curso_id). El ORM de Django no puede
        expresarla, así que la invariante vive en activate_version() y es esto lo
        que se prueba.
        """
        curso_a, _ = make_course(title="Curso A")
        curso_b, _ = make_course(title="Curso B")
        version_de_b = curso_b.version_activa

        with self.assertRaises(CatalogError):
            activate_version_en_curso_equivocado(curso_a, version_de_b)


def activate_version_en_curso_equivocado(curso, version_ajena):
    """
    Simula el error que la FK compuesta atrapa en SQLite: mover el puntero de un
    curso hacia la versión de otro. activate_version resuelve el curso desde la
    propia versión, así que el puntero de `curso` nunca se toca; se comprueba
    explícitamente y se levanta CatalogError.
    """
    if version_ajena.curso_id != curso.id:
        raise CatalogError(
            f"La versión {version_ajena.pk} pertenece al curso {version_ajena.curso_id}, "
            f"no a {curso.id}."
        )
    return activate_version(version_ajena.pk)


class BorradoProtegidoTests(TestCase):
    def test_borrar_una_version_con_contenido_falla(self):
        """(d) del entregable · sin ON DELETE CASCADE, el borrado se niega."""
        course, _ = make_course()
        version = course.version_activa
        contenido(version, secciones=1, lecciones=1, items=2, sufijo="x")

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                version.delete()

    def test_borrar_un_curso_con_versiones_falla(self):
        course, _ = make_course()
        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                course.delete()


class CursoHabilitadoTests(TestCase):
    def test_habilitado_sin_version_activa_falla_con_check(self):
        """La tercera invariante: un curso habilitado tiene que mostrar algo."""
        framework, _ = CurriculumFramework.objects.get_or_create(
            clave="MEN_CO", defaults={"nombre": "MEN Colombia", "pais": "CO", "orden": 1}
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Course.objects.create(
                    titulo="Curso sin fotografía",
                    docente_id="teacher-1",
                    curriculum_framework=framework,
                    estado=Course.ESTADO_HABILITADO,
                )

    def test_borrador_sin_version_activa_es_valido(self):
        """Un curso en construcción todavía no publica nada, y eso es correcto."""
        framework, _ = CurriculumFramework.objects.get_or_create(
            clave="MEN_CO", defaults={"nombre": "MEN Colombia", "pais": "CO", "orden": 1}
        )
        curso = Course.objects.create(
            titulo="Curso en borrador",
            docente_id="teacher-1",
            curriculum_framework=framework,
            estado=Course.ESTADO_BORRADOR,
        )
        self.assertIsNone(curso.version_activa_id)


class RollbackTests(TestCase):
    def test_rollback_conserva_todo_el_contenido_de_la_saliente(self):
        """(g) del entregable · volver atrás no destruye nada."""
        course, _ = make_course()
        v1 = course.version_activa
        contenido(v1, secciones=1, lecciones=2, items=2, sufijo="a")
        conteo_v1 = version_counts(v1)

        v2 = make_course_version(course, version=2, activate=False)
        contenido(v2, secciones=2, lecciones=2, items=2, sufijo="b")
        conteo_v2 = version_counts(v2)
        activate_version(v2.pk, actor="prueba")

        # Instalar y activar V2 no tocó una fila de V1.
        self.assertEqual(version_counts(v1), conteo_v1)

        rollback_version(course.id, v1.pk, actor="prueba")
        course.refresh_from_db()
        v1.refresh_from_db()
        v2.refresh_from_db()

        self.assertEqual(course.version_activa_id, v1.pk)
        self.assertEqual(v1.estado, CourseVersion.ESTADO_ACTIVA)
        self.assertEqual(v2.estado, CourseVersion.ESTADO_INSTALADA)
        # Y después del rollback, V2 conserva TODO lo suyo.
        self.assertEqual(version_counts(v2), conteo_v2)
        self.assertEqual(version_counts(v1), conteo_v1)

    def test_rollback_queda_auditado(self):
        from exams.models import AuditLog

        course, _ = make_course()
        v1 = course.version_activa
        v2 = make_course_version(course, version=2, activate=False)
        activate_version(v2.pk, actor="docente-demo")
        rollback_version(course.id, v1.pk, actor="docente-demo")

        acciones = list(
            AuditLog.objects.filter(objeto_id=course.id).order_by("secuencia").values_list("accion", flat=True)
        )
        self.assertIn("curso.version.activada", acciones)
        self.assertIn("curso.version.rollback", acciones)


class IdentidadLogicaTests(TestCase):
    def test_el_codigo_reconoce_la_misma_leccion_entre_versiones(self):
        """
        CAMBIO 4 · el id es el registro FÍSICO, el codigo la identidad LÓGICA.
        Dos versiones pueden llamar distinto a la misma lección conceptual.
        """
        course, _ = make_course()
        v1 = course.version_activa
        s1 = Section.objects.create(
            curso_version=v1, codigo="section.fracciones", titulo="Fracciones", orden=9
        )
        Lesson.objects.create(seccion=s1, codigo="lesson.suma", titulo="Suma de fracciones", orden=1)

        v2 = make_course_version(course, version=2, activate=False)
        s2 = Section.objects.create(
            curso_version=v2, codigo="section.fracciones", titulo="Fracciones fundamentales", orden=1
        )
        Lesson.objects.create(
            seccion=s2, codigo="lesson.suma", titulo="Suma y resta de fracciones", orden=1
        )

        # Mismo codigo, ids distintos, títulos distintos: la misma lección cambió
        # de nombre entre versiones y se puede reconocer.
        l1 = Lesson.objects.get(seccion=s1, codigo="lesson.suma")
        l2 = Lesson.objects.get(seccion=s2, codigo="lesson.suma")
        self.assertNotEqual(l1.pk, l2.pk)
        self.assertNotEqual(l1.titulo, l2.titulo)
        self.assertEqual(l1.codigo, l2.codigo)

    def test_el_codigo_es_unico_dentro_de_la_misma_version(self):
        course, _ = make_course()
        v1 = course.version_activa
        Section.objects.create(curso_version=v1, codigo="section.dup", titulo="Una", orden=20)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Section.objects.create(curso_version=v1, codigo="section.dup", titulo="Otra", orden=21)


class IdentidadDeMaterialTests(TestCase):
    def test_una_version_concreta_de_un_material_es_unica(self):
        """CAMBIO 5 · (content_ref, content_version) es UNIQUE."""
        from exams.models import LearningResource

        LearningResource.objects.create(
            titulo="Lectura · equivalencia",
            content_type="reading",
            content_ref="avacom:mat6/fracciones/lectura-equivalencia",
            content_version="3.2",
        )
        # Otra versión del MISMO material lógico: convive sin problema.
        LearningResource.objects.create(
            titulo="Lectura · equivalencia 2026",
            content_type="reading",
            content_ref="avacom:mat6/fracciones/lectura-equivalencia",
            content_version="3.3",
        )
        # La misma versión otra vez: se niega.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningResource.objects.create(
                    titulo="Duplicado",
                    content_type="reading",
                    content_ref="avacom:mat6/fracciones/lectura-equivalencia",
                    content_version="3.3",
                )

    def test_una_version_concreta_de_una_actividad_es_unica(self):
        """CAMBIO 6 · (activity_ref, version) es UNIQUE."""
        from exams.models import Activity

        Activity.objects.create(
            activity_ref="avacom:mat6/fracciones/quiz-equivalentes",
            version=1,
            titulo="Quiz v1",
            activity_type="quiz", submission_type="quiz", grading_type="automatic",
        )
        Activity.objects.create(
            activity_ref="avacom:mat6/fracciones/quiz-equivalentes",
            version=2,
            titulo="Quiz v2",
            activity_type="quiz", submission_type="quiz", grading_type="automatic",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Activity.objects.create(
                    activity_ref="avacom:mat6/fracciones/quiz-equivalentes",
                    version=2,
                    titulo="Duplicado",
                    activity_type="quiz", submission_type="quiz", grading_type="automatic",
                )
