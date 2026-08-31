from django.test import TestCase
from rest_framework.test import APIClient

from exams.models import QuizAttempt
from .factories import make_course


class QuizResultTests(TestCase):
    def test_results_can_be_filtered_by_activity(self):
        _, activity = make_course()
        QuizAttempt.objects.create(
            actividad=activity,
            persona_id="ada",
            nombre_estudiante="Ada",
            total_preguntas=2,
            puntaje=50,
            estado=QuizAttempt.ESTADO_FINALIZADO,
        )

        response = APIClient().get(f"/api/quiz-results/?actividad_id={activity.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["nombre_estudiante"], "Ada")
        self.assertEqual(response.json()[0]["porcentaje"], 50)
