from django.test import TestCase
from rest_framework.test import APIClient

from exams.models import CourseEnrollment
from .factories import make_course


class EnrollmentTests(TestCase):
    def test_assign_student_to_course(self):
        course, _ = make_course()

        response = APIClient().post(
            "/api/enrollments/",
            {"curso": course.id, "persona_id": "Sofía Ramírez", "estado": "activa"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["persona_id"], "sofía-ramírez")
        self.assertTrue(CourseEnrollment.objects.filter(curso=course, persona_id="sofía-ramírez").exists())
