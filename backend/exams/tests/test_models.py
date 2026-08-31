from django.test import TestCase

from exams.models import Course, CourseVersion, QuizAttempt
from .factories import make_course


class CourseModelTests(TestCase):
    def test_course_hierarchy_matches_reference_model(self):
        """
        La jerarquía del modelo versionado:
            m05_curso -> m05_curso_version -> m05_seccion -> m05_leccion -> m05_leccion_item

        Lo que antes se leía como `curso.secciones` ahora pasa por la versión.
        El curso no tiene secciones: tiene VERSIONES, y cada versión las suyas.
        """
        course, activity = make_course(questions=5)

        # El curso ya no conoce secciones directamente.
        self.assertFalse(hasattr(course, "secciones"))
        self.assertEqual(course.versiones.count(), 1)

        version = course.version_activa
        self.assertIsNotNone(version, "activar la primera versión debe dejar el puntero puesto")
        self.assertEqual(version.estado, CourseVersion.ESTADO_ACTIVA)
        self.assertEqual(course.estado, Course.ESTADO_HABILITADO)

        self.assertEqual(version.secciones.count(), 1)
        seccion = version.secciones.first()
        self.assertEqual(seccion.lecciones.count(), 1)
        leccion = seccion.lecciones.first()
        self.assertEqual(leccion.items.first().actividad, activity)
        self.assertEqual(activity.preguntas.count(), 5)

        # Identidad LÓGICA aparte de la FÍSICA (cambio 4).
        self.assertTrue(seccion.codigo.startswith("section."))
        self.assertTrue(leccion.codigo.startswith("lesson."))
        # Identidad lógica de la actividad (cambio 6).
        self.assertTrue(activity.activity_ref.startswith("avacom:"))

        self.assertEqual(Course._meta.db_table, "m05_curso")
        self.assertEqual(CourseVersion._meta.db_table, "m05_curso_version")
        self.assertEqual(QuizAttempt._meta.db_table, "m10_quiz_intento")

    def test_course_no_longer_has_a_version_integer(self):
        """
        CAMBIO 2 · el entero desapareció. Un contador se desincroniza del
        contenido; el puntero no puede.
        """
        columnas = {campo.name for campo in Course._meta.get_fields()}
        self.assertNotIn("version", columnas)
        self.assertIn("version_activa", columnas)
