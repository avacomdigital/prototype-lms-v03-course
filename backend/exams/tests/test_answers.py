from django.test import TestCase
from rest_framework.test import APIClient

from exams.models import QuizAnswer, QuizAttempt
from .factories import correct_option, make_course


class QuizAnswerTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        _, self.activity = make_course(questions=2)
        start = self.api.post(
            "/api/quiz-attempts/start/",
            {"actividad_id": self.activity.id, "nombre_estudiante": "Ada Lovelace", "device_id": "tablet-1"},
            format="json",
        )
        self.attempt_id = start.json()["id"]

    def test_answers_are_upserted_and_finish_calculates_grade(self):
        questions = list(self.activity.preguntas.all())
        for question in questions:
            response = self.api.post(
                "/api/quiz-attempts/answer/",
                {"intento_id": self.attempt_id, "pregunta_id": question.id, "opcion_id": correct_option(question).id},
                format="json",
            )
            self.assertEqual(response.status_code, 201)

        finish = self.api.post("/api/quiz-attempts/finish/", {"intento_id": self.attempt_id}, format="json")

        self.assertEqual(finish.status_code, 200)
        self.assertEqual(finish.json()["puntaje"], 100.0)
        self.assertEqual(QuizAttempt.objects.get(pk=self.attempt_id).estado, "finalizado")
        self.assertEqual(QuizAnswer.objects.filter(intento_id=self.attempt_id).count(), 2)
