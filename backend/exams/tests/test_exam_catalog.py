from django.test import TestCase
from rest_framework.test import APIClient

from .factories import make_course


class CourseCatalogTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.course, self.activity = make_course(questions=2)

    def test_student_catalog_contains_sections_lessons_items_and_quiz(self):
        response = self.api.get("/api/courses/?student=1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()[0]
        self.assertEqual(payload["titulo"], self.course.titulo)
        item = payload["secciones"][0]["lecciones"][0]["items"][0]
        self.assertEqual(item["actividad"]["preguntas"][0]["opciones"][0]["texto"], "Opción 1")
        self.assertNotIn("es_correcta", item["actividad"]["preguntas"][0]["opciones"][0])

    def test_course_crud_uses_native_apiview(self):
        response = self.api.patch(
            f"/api/courses/{self.course.id}/", {"estado": "pruebas"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["estado"], "pruebas")
